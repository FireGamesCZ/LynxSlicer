"""Read-only listener for Bambu Lab printers in LAN mode (MQTT over TLS).

Field names follow what OrcaSlicer's own parser reads from the "print" object
(src/slic3r/GUI/DeviceManager.cpp, DeviceCore/DevFilaSystem.cpp). Never publishes
anything except the pushall status request.
"""
import copy
import json
import logging

log = logging.getLogger(__name__)

ACTIVE = {"RUNNING", "PAUSE"}
TERMINAL = {"FINISH", "FAILED"}
# print_error of a user cancel; "The task was canceled." is ecode 0300400C in resources/hms.
CANCEL_ERROR = 0x0300400C
VIR_SLOTS = {"255": "vt_tray", "254": "vt_tray2"}  # VIRTUAL_TRAY_MAIN_ID / _DEPUTY_ID in DevDefs.h


def _tray(tray: dict) -> dict:
    """DevFilaSystem.cpp: a reported tray is complete; no type+idx pair means no filament."""
    if "tray_type" in tray and "tray_info_idx" in tray:
        return dict(tray)
    return {k: v for k, v in tray.items() if k not in ("tray_type", "tray_info_idx")}


def merge_report(state: dict, message: dict) -> dict:
    """Return a new state: `state` plus the "print" object of `message`."""
    new = copy.deepcopy(state)
    pr = message.get("print")
    # Orca only parses command == push_status; other replies are command echoes.
    if not isinstance(pr, dict) or pr.get("command") != "push_status":
        return new
    for key, val in pr.items():
        if key == "ams" and isinstance(val, dict):
            for ams in val.get("ams") or []:
                if "id" not in ams:
                    continue
                trays = new.setdefault("ams", {}).setdefault(str(ams["id"]), {})
                for tray in ams.get("tray") or []:
                    if "id" in tray:
                        trays[str(tray["id"])] = _tray(tray)
        elif key == "vt_tray" and isinstance(val, dict):
            new["vt_tray"] = _tray(val)  # id is ignored: always the main slot (255)
        elif key == "vir_slot" and isinstance(val, list):
            for slot in val:
                if str(slot.get("id")) in VIR_SLOTS:
                    new[VIR_SLOTS[str(slot["id"])]] = _tray(slot)
        elif key not in ("command", "sequence_id"):
            new[key] = val
    return new


def _job(state: dict) -> dict:
    # Identity as in DeviceManager.cpp: job_id, else subtask_id / task_id (absent on some firmware).
    ident = next((state[k] for k in ("job_id", "subtask_id", "task_id") if state.get(k)), None)
    job = {
        "name": state.get("subtask_name") or state.get("gcode_file") or None,
        "layer": state.get("layer_num"),
        "total_layers": state.get("total_layer_num"),
        "percent": state.get("mc_percent"),
    }
    return {**job, "job_id": ident} if ident is not None else job


def events(prev: dict, new: dict) -> list[dict]:
    """Events for the transition prev -> new. A late attach gets "late": True on the end event."""
    ps, ns = prev.get("gcode_state"), new.get("gcode_state")
    job, old = _job(new), _job(prev)
    out = []
    if ps in ACTIVE and (ns not in ACTIVE and ns not in TERMINAL
                         or ns in ACTIVE and None not in (old.get("job_id"), job.get("job_id"))
                         and old["job_id"] != job["job_id"]):
        out.append({"type": "job_lost", **old})  # the end of that job was never reported
    if ns in ACTIVE:
        if ps not in ACTIVE or out:
            out.append({"type": "job_started", "name": job["name"], "total_layers": job["total_layers"],
                        **({"job_id": job["job_id"]} if "job_id" in job else {})})
        elif (job["layer"], job["percent"]) != (prev.get("layer_num"), prev.get("mc_percent")):
            out.append({"type": "progress", "layer": job["layer"], "percent": job["percent"]})
        return out
    if ns in TERMINAL:
        err = new.get("print_error") or None
        # FAILED first, the real cause (e.g. a cancel) in a later partial update: correct it.
        corrected = ps == ns == "FAILED" and err and not prev.get("print_error")
        if ps != ns or corrected:
            if ns == "FINISH":
                ev = {"type": "job_finished", **job}
            elif err == CANCEL_ERROR:
                ev = {"type": "job_cancelled", **job}
            else:
                ev = {"type": "job_failed", **job, "error": err}
            if corrected:
                ev["corrects"] = "job_failed"
            elif ps not in ACTIVE:
                ev["late"] = True
            out.append(ev)
    return out


def spools(state: dict) -> list[dict]:
    def norm(slot, tray):
        # An emptied slot keeps its id but has an empty tray_type.
        if not tray.get("tray_type"):
            return None
        colour = tray.get("tray_color")
        remain = tray.get("remain")
        return {
            "slot": slot,
            "type": tray["tray_type"],
            "colour": "#" + colour[:6].upper() if colour else None,  # RRGGBBAA on the wire
            "filament_id": tray.get("tray_info_idx") or None,
            "remain": remain if isinstance(remain, int) and remain >= 0 else None,
        }

    out = []
    for a in sorted(state.get("ams", {}), key=int):
        for t in sorted(state["ams"][a], key=int):
            out.append(norm(f"ams{a}-{t}", state["ams"][a][t]))
    out.append(norm("ext", state.get("vt_tray", {})))
    out.append(norm("ext2", state.get("vt_tray2", {})))
    return [s for s in out if s]


def step(state: dict, message: dict) -> tuple[dict, list[dict]]:
    new = merge_report(state, message)
    return new, events(state, new)


def fetch_cert(host, port=8883):
    """The printer's certificate as PEM, for trust-on-first-use pinning (storing it is the caller's job)."""
    import ssl
    return ssl.get_server_certificate((host, port))


def pinned_context(pem):
    """TLS context that trusts exactly this certificate (printers are addressed by IP: no hostname check)."""
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cadata=pem)
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = False
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN  # a self-issued or leaf cert may be the anchor
    return ctx


def make_client(serial, access_code, on_report, pinned_cert_pem=None):
    """Build the MQTT client (not connected). on_report(dict) gets every report."""
    import ssl
    import paho.mqtt.client as mqtt  # lazy: the rest of this module is stdlib only

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set("bblp", access_code)
    if pinned_cert_pem:
        client.tls_set_context(pinned_context(pinned_cert_pem))
    else:
        log.warning("no pinned printer certificate: TLS is unauthenticated, the access code can be intercepted on the LAN")
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)

    def on_connect(c, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            log.warning("MQTT connect refused: %s", reason_code)
            return
        c.subscribe(f"device/{serial}/report")
        # The only message this module ever publishes.
        c.publish(f"device/{serial}/request",
                  json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))

    def on_message(c, userdata, msg):
        try:
            on_report(json.loads(msg.payload))
        except Exception:  # a bad message or callback must not kill the loop; no secret is in this path
            log.exception("report handling failed")

    client.on_connect, client.on_message = on_connect, on_message
    client.reconnect_delay_set(1, 30)
    return client


def run(host, serial, access_code, on_report, pinned_cert_pem=None):
    """Blocking; reconnects on drop."""
    client = make_client(serial, access_code, on_report, pinned_cert_pem)
    client.connect_async(host, 8883)
    client.loop_forever(retry_first_connection=True)


def listen(host, serial, access_code, on_event, on_state=None, pinned_cert_pem=None):
    """Blocking. on_event(event: dict) per event, on_state(state: dict) after each report."""
    holder = {"state": {}}

    def on_report(message):
        holder["state"], evs = step(holder["state"], message)
        if on_state:
            on_state(holder["state"])
        for ev in evs:
            try:
                on_event(ev)
            except Exception:  # the state is already advanced: keep the rest of the batch
                log.exception("on_event failed for %s", ev.get("type"))

    run(host, serial, access_code, on_report, pinned_cert_pem)
