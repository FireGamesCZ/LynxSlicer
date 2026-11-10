import json
import re
from pathlib import Path

from .inventory import get_calibrations, get_filament, get_spool

BED_KEYS = ("hot_plate_temp", "cool_plate_temp", "eng_plate_temp", "textured_plate_temp")


def _s(v):
    # Orca writes every value as a string; whole numbers without ".0".
    return str(int(v)) if float(v) == int(v) else str(v)


def filament_preset(conn, spool_id, printer_id, nozzle_mm, inherits):
    spool = get_spool(conn, spool_id)
    f = get_filament(conn, spool["filament_id"])
    cal = {k: v for k, (v, _src) in get_calibrations(conn, f["id"], printer_id, nozzle_mm).items()}
    printer = conn.execute("SELECT name FROM printer WHERE id = ?", (printer_id,)).fetchone()["name"]
    name = " ".join(x for x in (f["vendor"], f["material"], f["name"]) if x) + f" @lynx {spool_id} {printer} {_s(nozzle_mm)}"

    vec = {}  # key -> single string value; wrapped in a list below
    def put(key, value, fmt=_s):
        if value is not None:
            vec[key] = fmt(value)

    put("filament_vendor", f["vendor"], str)
    put("filament_type", f["material"], str)
    put("default_filament_colour", f["color_hex"], str)
    put("filament_diameter", f["diameter_mm"])
    put("filament_density", f["density_g_cm3"])
    if f["price_per_kg"] is not None:
        put("filament_cost", f["price_per_kg"])
    put("nozzle_temperature_range_low", f["nozzle_temp_min"])
    put("nozzle_temperature_range_high", f["nozzle_temp_max"])
    if f["bed_temp"] is not None:
        for k in BED_KEYS:
            put(k, f["bed_temp"])
            put(k + "_initial_layer", f["bed_temp"])
    put("filament_flow_ratio", cal.get("flow_ratio"))
    if "pressure_advance" in cal:
        put("enable_pressure_advance", 1)
        put("pressure_advance", cal["pressure_advance"])
    put("filament_max_volumetric_speed", cal.get("max_volumetric_speed"))
    put("filament_retraction_length", cal.get("retraction_length"))
    if "nozzle_temp" in cal:
        put("nozzle_temperature", cal["nozzle_temp"])
        put("nozzle_temperature_initial_layer", cal["nozzle_temp"])

    out = {"type": "filament", "name": name, "inherits": inherits, "from": "User", "version": "2.5.0.0"}
    out.update({k: [v] for k, v in vec.items()})
    return out


def write_preset(preset, directory):
    """Write <name>.json plus the .info sidecar Orca writes next to every user preset."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r'[\\/:*?"<>|]', "_", preset["name"])
    path = d / f"{stem}.json"
    path.write_text(json.dumps(preset, indent=4), encoding="utf-8")
    # Without the .info an unsynced user preset is treated as a cloud deletion request (Preset.cpp:862).
    (d / f"{stem}.info").write_text("sync_info = \nuser_id = \nsetting_id = \nbase_id = \nupdated_time = 0\n")
    return path
