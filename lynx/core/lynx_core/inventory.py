import json
import sqlite3
from datetime import datetime, timezone

CALIBRATION_KEYS = ("flow_ratio", "pressure_advance", "max_volumetric_speed", "retraction_length", "nozzle_temp")

SCHEMA = """
CREATE TABLE IF NOT EXISTS filament(
  id INTEGER PRIMARY KEY, vendor TEXT, material TEXT NOT NULL, name TEXT, color_hex TEXT,
  diameter_mm REAL NOT NULL DEFAULT 1.75, density_g_cm3 REAL, nozzle_temp_min REAL, nozzle_temp_max REAL,
  bed_temp REAL, drying_temp REAL, drying_hours REAL, price_per_kg REAL, spool_tare_g REAL, notes TEXT);
CREATE TABLE IF NOT EXISTS printer(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, driver TEXT NOT NULL CHECK(driver IN ('bambu','prusalink')),
  host TEXT, serial TEXT, model TEXT);
CREATE TABLE IF NOT EXISTS calibration(
  id INTEGER PRIMARY KEY, filament_id INTEGER NOT NULL REFERENCES filament(id),
  printer_id INTEGER NOT NULL REFERENCES printer(id), nozzle_mm REAL NOT NULL, key TEXT NOT NULL,
  value REAL NOT NULL, source TEXT NOT NULL CHECK(source IN ('vendor','calibrated','lidar','default')),
  updated_at TEXT, UNIQUE(filament_id, printer_id, nozzle_mm, key));
CREATE TABLE IF NOT EXISTS spool(
  id INTEGER PRIMARY KEY, filament_id INTEGER NOT NULL REFERENCES filament(id), initial_g REAL NOT NULL,
  printer_id INTEGER REFERENCES printer(id), slot TEXT, opened_at TEXT, archived INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS spool_slot ON spool(printer_id, slot) WHERE slot IS NOT NULL;
CREATE TABLE IF NOT EXISTS job(
  id INTEGER PRIMARY KEY, printer_id INTEGER NOT NULL REFERENCES printer(id), name TEXT,
  state TEXT NOT NULL CHECK(state IN ('running','finished','failed','cancelled')),
  started_at TEXT, ended_at TEXT, plan_json TEXT);
CREATE TABLE IF NOT EXISTS usage(
  id INTEGER PRIMARY KEY, spool_id INTEGER NOT NULL REFERENCES spool(id), job_id INTEGER REFERENCES job(id),
  grams REAL NOT NULL, source TEXT NOT NULL CHECK(source IN ('slicer','estimate','manual','weighed')),
  note TEXT, created_at TEXT);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def _insert(conn, table, fields):
    """Insert without committing; the caller owns the transaction."""
    valid = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    bad = set(fields) - valid
    if bad:
        raise ValueError(f"unknown column(s) for {table}: {sorted(bad)}")
    cols = ", ".join(fields)
    cur = conn.execute(f"INSERT INTO {table}({cols}) VALUES ({', '.join('?' * len(fields))})", list(fields.values()))
    return cur.lastrowid


def _add(conn, table, fields):
    with conn:
        return _insert(conn, table, fields)


def _get(conn, table, id_):
    return conn.execute(f"SELECT * FROM {table} WHERE id = ?", (id_,)).fetchone()


def add_filament(conn, **fields):
    return _add(conn, "filament", fields)


def get_filament(conn, id_):
    return _get(conn, "filament", id_)


def list_filaments(conn):
    return conn.execute("SELECT * FROM filament ORDER BY id").fetchall()


def add_printer(conn, **fields):
    return _add(conn, "printer", fields)


def get_printer(conn, id_):
    return _get(conn, "printer", id_)


def list_printers(conn):
    return conn.execute("SELECT * FROM printer ORDER BY id").fetchall()


def add_spool(conn, **fields):
    fields.setdefault("opened_at", _now())
    with conn:
        if fields.get("slot") is not None:
            _evict(conn, fields.get("printer_id"), fields["slot"], None)
        return _insert(conn, "spool", fields)


def get_spool(conn, id_):
    return _get(conn, "spool", id_)


def list_spools(conn, include_archived=False):
    where = "" if include_archived else "WHERE archived = 0"
    return conn.execute(f"SELECT * FROM spool {where} ORDER BY id").fetchall()


def set_calibration(conn, filament_id, printer_id, nozzle_mm, key, value, source):
    if key not in CALIBRATION_KEYS:
        raise ValueError(f"unknown calibration key {key!r}")
    conn.execute(
        "INSERT INTO calibration(filament_id, printer_id, nozzle_mm, key, value, source, updated_at)"
        " VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(filament_id, printer_id, nozzle_mm, key)"
        " DO UPDATE SET value = excluded.value, source = excluded.source, updated_at = excluded.updated_at",
        (filament_id, printer_id, nozzle_mm, key, value, source, _now()))
    conn.commit()


def get_calibrations(conn, filament_id, printer_id, nozzle_mm):
    rows = conn.execute(
        "SELECT key, value, source FROM calibration WHERE filament_id = ? AND printer_id = ? AND nozzle_mm = ?",
        (filament_id, printer_id, nozzle_mm))
    return {r["key"]: (r["value"], r["source"]) for r in rows}


def _evict(conn, printer_id, slot, keep_id):
    conn.execute("UPDATE spool SET printer_id = NULL, slot = NULL WHERE printer_id = ? AND slot = ? AND id IS NOT ?",
                 (printer_id, slot, keep_id))


def assign_spool(conn, spool_id, printer_id, slot):
    with conn:
        _evict(conn, printer_id, slot, spool_id)
        conn.execute("UPDATE spool SET printer_id = ?, slot = ? WHERE id = ?", (printer_id, slot, spool_id))


def remaining_g(conn, spool_id):
    row = conn.execute(
        "SELECT s.initial_g - COALESCE((SELECT SUM(grams) FROM usage WHERE spool_id = s.id), 0) AS r"
        " FROM spool s WHERE s.id = ?", (spool_id,)).fetchone()
    return row["r"]


def log_usage(conn, spool_id, grams, source, job_id=None, note=None):
    return _add(conn, "usage", dict(spool_id=spool_id, job_id=job_id, grams=grams, source=source,
                                    note=note, created_at=_now()))


def undo_usage(conn, usage_id):
    conn.execute("DELETE FROM usage WHERE id = ?", (usage_id,))
    conn.commit()


def weigh_spool(conn, spool_id, gross_g):
    tare = conn.execute("SELECT f.spool_tare_g FROM spool s JOIN filament f ON f.id = s.filament_id WHERE s.id = ?",
                        (spool_id,)).fetchone()["spool_tare_g"]
    if tare is None:
        raise ValueError("filament has no spool_tare_g; cannot weigh")
    delta = remaining_g(conn, spool_id) - (gross_g - tare)
    return log_usage(conn, spool_id, delta, "weighed", note=f"gross {gross_g} g")


def start_job(conn, printer_id, name, plan):
    # Pin each slot to the spool loaded now, so a later swap does not get the usage.
    plan = {**plan, "slots": {slot: {**info, "spool_id": _slot_spool(conn, printer_id, slot)}
                              for slot, info in plan["slots"].items()}}
    return _add(conn, "job", dict(printer_id=printer_id, name=name, state="running",
                                  started_at=_now(), plan_json=json.dumps(plan)))


def estimate_partial_g(by_layer_g, last_layer):
    if last_layer <= 0:
        return 0.0
    if last_layer > len(by_layer_g):
        return float(by_layer_g[-1]) if by_layer_g else 0.0
    before = by_layer_g[last_layer - 2] if last_layer >= 2 else 0.0
    return before + (by_layer_g[last_layer - 1] - before) / 2


def _slot_spool(conn, printer_id, slot):
    row = conn.execute("SELECT id FROM spool WHERE printer_id = ? AND slot = ? AND archived = 0",
                       (printer_id, slot)).fetchone()
    return row["id"] if row else None


def finish_job(conn, job_id, state, last_layer=None):
    """Log usage for a job. Returns the slots that had no assigned spool (the UI should ask)."""
    if state not in ("finished", "failed", "cancelled"):
        raise ValueError(f"invalid end state {state!r}")
    with conn:  # all-or-nothing: claim + usage rows commit together
        claimed = conn.execute("UPDATE job SET state = ?, ended_at = ? WHERE id = ? AND state = 'running'",
                               (state, _now(), job_id))
        if claimed.rowcount == 0:
            return []  # already ended: never log twice
        plan = json.loads(conn.execute("SELECT plan_json FROM job WHERE id = ?", (job_id,)).fetchone()[0]
                          or '{"slots": {}}')
        unassigned = []
        for slot, info in plan["slots"].items():
            spool_id = info.get("spool_id")
            if spool_id is None:
                unassigned.append(slot)
                continue
            if state == "finished":
                grams, source = info["total_g"], "slicer"
            elif last_layer is not None:
                grams, source = estimate_partial_g(info["by_layer_g"], last_layer), "estimate"
            else:
                continue
            _insert(conn, "usage", dict(spool_id=spool_id, job_id=job_id, grams=grams, source=source,
                                        note=None, created_at=_now()))
    return unassigned


def check_enough(conn, printer_id, plan):
    short = []
    for slot, info in plan["slots"].items():
        spool_id = _slot_spool(conn, printer_id, slot)
        if spool_id is None:
            continue
        left = remaining_g(conn, spool_id)
        if left < info["total_g"]:
            short.append((slot, spool_id, info["total_g"], left))
    return short
