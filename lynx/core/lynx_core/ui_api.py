"""Message dispatcher between the Spools page and the inventory. No UI, no threads.

Request {"id": n, "op": "...", "args": {...}} -> reply {"id": n, "ok": true, "result": ...}
or {"id": n, "ok": false, "error": "message for the user"}. handle() never raises.
"""
import math
import re
import sqlite3

from . import inventory as inv

DRIVERS = ("bambu", "prusalink")


class Bad(ValueError):
    """A problem the user can fix; the message is shown as is."""


# --- argument validators: each takes (name, value) and returns the cleaned value ---

def _num(name, v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise Bad(f"{name} must be a number")
    return float(v)


def _pos(name, v):
    v = _num(name, v)
    if v <= 0:
        raise Bad(f"{name} must be greater than 0")
    return v


def _nonneg(name, v):
    v = _num(name, v)
    if v < 0:
        raise Bad(f"{name} must not be negative")
    return v


def _id(name, v):
    if isinstance(v, bool) or not isinstance(v, int):
        raise Bad(f"{name} must be a whole number")
    return v


def _text(name, v):
    if not isinstance(v, str):
        raise Bad(f"{name} must be text")
    if len(v) > 200:
        raise Bad(f"{name} is too long (max 200 characters)")
    return v.strip()


def _color(name, v):
    v = _text(name, v)
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
        raise Bad(f"{name} must look like #RRGGBB, for example #FF8800")
    return v.upper()


def _driver(name, v):
    if v not in DRIVERS:
        raise Bad(f"{name} must be one of: {', '.join(DRIVERS)}")
    return v


def _flag(name, v):
    if not isinstance(v, bool):
        raise Bad(f"{name} must be true or false")
    return v


# --- lookups ---

def _need(conn, getter, id_, what):
    row = getter(conn, id_)
    if row is None:
        raise Bad(f"{what} {id_} does not exist")
    return row


def _live_spool(conn, id_):
    row = _need(conn, inv.get_spool, id_, "spool")
    if row["archived"]:
        raise Bad(f"spool {id_} is archived")
    return row


def _row(r):
    return {k: r[k] for k in r.keys()}


# --- operations: func(conn, **cleaned_args) -> result ---

def list_filaments(conn):
    return [_row(r) for r in inv.list_filaments(conn)]


def add_filament(conn, material, vendor=None, name=None, color_hex=None, diameter_mm=None,
                 spool_tare_g=None, density_g_cm3=None, price_per_kg=None):
    if not material:
        raise Bad("material is required, for example PLA")
    fields = dict(material=material, vendor=vendor or None, name=name or None, color_hex=color_hex,
                  spool_tare_g=spool_tare_g, density_g_cm3=density_g_cm3, price_per_kg=price_per_kg)
    if diameter_mm is not None:
        fields["diameter_mm"] = diameter_mm
    return {"id": inv.add_filament(conn, **fields)}


def list_printers(conn):
    return [_row(r) for r in inv.list_printers(conn)]


def add_printer(conn, name, driver, host=None, serial=None, model=None):
    if not name:
        raise Bad("name is required")
    return {"id": inv.add_printer(conn, name=name, driver=driver, host=host or None,
                                  serial=serial or None, model=model or None)}


def list_spools(conn, include_archived=False):
    out = []
    for s in inv.list_spools(conn, include_archived):
        f = inv.get_filament(conn, s["filament_id"])
        p = inv.get_printer(conn, s["printer_id"]) if s["printer_id"] is not None else None
        left = inv.remaining_g(conn, s["id"])
        out.append(dict(
            id=s["id"], filament_id=f["id"], vendor=f["vendor"], material=f["material"], name=f["name"],
            color_hex=f["color_hex"], tare_g=f["spool_tare_g"], initial_g=s["initial_g"],
            remaining_g=round(left, 1), percent=round(100 * left / s["initial_g"], 1) if s["initial_g"] else 0.0,
            printer_id=s["printer_id"], slot=s["slot"], archived=bool(s["archived"]), opened_at=s["opened_at"],
            location=f"{p['name']} / {s['slot']}" if p else "Not loaded"))
    return out


def _check_location(conn, printer_id, slot):
    if (printer_id is None) != (not slot):
        raise Bad("give both a printer and a slot, or neither")
    if printer_id is not None:
        _need(conn, inv.get_printer, printer_id, "printer")


def add_spool(conn, filament_id, initial_g, printer_id=None, slot=None):
    _need(conn, inv.get_filament, filament_id, "filament")
    _check_location(conn, printer_id, slot)
    return {"id": inv.add_spool(conn, filament_id=filament_id, initial_g=initial_g,
                                printer_id=printer_id, slot=slot or None)}


def assign_spool(conn, spool_id, printer_id=None, slot=None):
    _live_spool(conn, spool_id)
    _check_location(conn, printer_id, slot)
    inv.assign_spool(conn, spool_id, printer_id, slot or None)
    return {"id": spool_id}


def weigh_spool(conn, spool_id, gross_g):
    _live_spool(conn, spool_id)
    tare = inv.get_filament(conn, inv.get_spool(conn, spool_id)["filament_id"])["spool_tare_g"]
    if tare is None:
        raise Bad("this filament has no empty spool weight; add one to the filament before weighing")
    if gross_g < tare:
        raise Bad(f"gross weight {gross_g:g} g is below the empty spool weight {tare:g} g")
    return {"usage_id": inv.weigh_spool(conn, spool_id, gross_g)}


def log_manual_usage(conn, spool_id, grams, note=None):
    _live_spool(conn, spool_id)
    return {"usage_id": inv.log_usage(conn, spool_id, grams, "manual", note=note or None)}


def list_usage(conn, spool_id):
    _need(conn, inv.get_spool, spool_id, "spool")
    rows = conn.execute("SELECT id, grams, source, note, created_at FROM usage WHERE spool_id = ? ORDER BY id DESC",
                        (spool_id,))
    return [_row(r) for r in rows]


def undo_usage(conn, usage_id):
    if conn.execute("SELECT 1 FROM usage WHERE id = ?", (usage_id,)).fetchone() is None:
        raise Bad(f"usage entry {usage_id} does not exist")
    inv.undo_usage(conn, usage_id)
    return {"id": usage_id}


def archive_spool(conn, spool_id):
    _live_spool(conn, spool_id)
    with conn:  # an archived spool must not keep holding its slot
        conn.execute("UPDATE spool SET archived = 1, printer_id = NULL, slot = NULL WHERE id = ?", (spool_id,))
    return {"id": spool_id}


# op -> (function, {arg: validator}, required args)
OPS = {
    "list_filaments": (list_filaments, {}, ()),
    "add_filament": (add_filament, dict(material=_text, vendor=_text, name=_text, color_hex=_color,
                                         diameter_mm=_pos, spool_tare_g=_nonneg, density_g_cm3=_pos,
                                         price_per_kg=_nonneg), ("material",)),
    "list_printers": (list_printers, {}, ()),
    "add_printer": (add_printer, dict(name=_text, driver=_driver, host=_text, serial=_text, model=_text),
                    ("name", "driver")),
    "list_spools": (list_spools, dict(include_archived=_flag), ()),
    "add_spool": (add_spool, dict(filament_id=_id, initial_g=_pos, printer_id=_id, slot=_text),
                  ("filament_id", "initial_g")),
    "assign_spool": (assign_spool, dict(spool_id=_id, printer_id=_id, slot=_text), ("spool_id",)),
    "weigh_spool": (weigh_spool, dict(spool_id=_id, gross_g=_pos), ("spool_id", "gross_g")),
    "log_manual_usage": (log_manual_usage, dict(spool_id=_id, grams=_pos, note=_text), ("spool_id", "grams")),
    "list_usage": (list_usage, dict(spool_id=_id), ("spool_id",)),
    "undo_usage": (undo_usage, dict(usage_id=_id), ("usage_id",)),
    "archive_spool": (archive_spool, dict(spool_id=_id), ("spool_id",)),
}


def _dispatch(conn, message):
    if not isinstance(message, dict):
        raise Bad("request must be an object")
    op, args = message.get("op"), message.get("args", {})
    if args is None:
        args = {}
    if not isinstance(op, str) or op not in OPS:
        raise Bad(f"unknown operation {op!r}")
    if not isinstance(args, dict):
        raise Bad("args must be an object")
    func, validators, required = OPS[op]
    extra = sorted(set(args) - set(validators))
    if extra:
        raise Bad(f"unexpected argument(s): {', '.join(map(str, extra))}")
    missing = [a for a in required if args.get(a) is None]
    if missing:
        raise Bad(f"missing argument(s): {', '.join(missing)}")
    # None means "not given" so the page can send empty optional fields as null
    clean = {k: validators[k](k, v) for k, v in args.items() if v is not None}
    return func(conn, **clean)


def handle(conn, message):
    rid = message.get("id") if isinstance(message, dict) else None
    try:
        return {"id": rid, "ok": True, "result": _dispatch(conn, message)}
    except Bad as e:
        return {"id": rid, "ok": False, "error": str(e)}
    except sqlite3.Error as e:
        return {"id": rid, "ok": False, "error": f"database error: {e}"}
    except Exception as e:  # shortcut: last-resort net so the page never hangs; narrow if real bugs hide here
        return {"id": rid, "ok": False, "error": f"unexpected error: {type(e).__name__}: {e}"}
