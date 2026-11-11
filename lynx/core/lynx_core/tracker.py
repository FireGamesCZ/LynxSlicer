"""Print tracking from OrcaSlicer's own events: no MQTT here, no access code. Pure logic, no `orca` import.

The plug-in feeds it three things: the statistics of the plate just sliced (sliced), the fact that a job was
sent to a device (job_sent, any thread) and the printer's state string plus status (state_changed, UI thread).
Every deduction goes through inventory.finish_job, which claims the job row first, so one print is never
deducted twice. The printer-side job id is kept in the job's plan_json ("printer_job_id"): no schema change,
old databases open as before.

State rules (same as bambu.events): RUNNING/PAUSE are active. PREPARE/SLICING are heating or preparing, nothing
is extruded yet and the printer still reports no layer, so they neither start nor end a job; the job starts
when RUNNING arrives (cancelling during PREPARE costs no filament).
"""
import json
import threading
import time

from . import inventory as inv, plan as planmod, ui_api
from .bambu import ACTIVE, CANCEL_ERROR

# A sent plan belongs to the print that starts within this long after sending: upload plus heating.
PENDING_TTL_S = 30 * 60
KINDS = {"finished": "job_finished", "failed": "job_failed", "cancelled": "job_cancelled"}


def _base(name):
    name = (name or "").lower()
    for ext in (".gcode", ".3mf"):
        name = name.removesuffix(ext)
    return name.strip()


def _same_name(a, b):
    a, b = _base(a), _base(b)
    return not a or not b or a in b or b in a


def _slot_plan(plan, trays, mapping=None):
    if mapping:  # filament id -> slot name, from the print dialog
        names = [mapping.get(k) for k in plan["slots"]]
        # A filament without a slot, or two on one slot, keeps its id: unassigned, the user is asked.
        return planmod.remap_plan(plan, {k: n if n and names.count(n) == 1 else k for k, n in zip(plan["slots"], names)})
    # shortcut: one filament and no AMS -> the external spool; with no mapping every other plate stays keyed by
    # filament id, so its slots come back unassigned and the user is asked.
    if len(plan["slots"]) == 1 and not any(t["slot"].startswith("ams") and t.get("exists", True) for t in trays):
        return planmod.remap_plan(plan, planmod.default_mapping(plan))
    return plan


class Tracker:
    def __init__(self, conn, clock=time.time):
        self.conn, self.clock = conn, clock
        self.plans = {}  # plate index -> sliced plan, keyed by filament id
        self._pending = {}  # device id -> (plan, project name, time sent, slot mapping or None)
        self._lock = threading.Lock()  # guards plans and _pending: job_sent runs on a worker thread

    def clear(self):
        with self._lock:
            self.plans.clear()  # a new or closed project: no plan of the old one may be sent

    def sliced(self, stats, plate_index=-1):
        with self._lock:
            self.plans.pop(plate_index, None)  # a failed parse must not leave the previous plan behind
        plan = planmod.plan_from_statistics(stats)
        with self._lock:
            self.plans[plate_index] = plan
        printers = inv.list_printers(self.conn)
        if len(printers) != 1:
            return None  # which printer it is for is not known before sending
        return ui_api.check_plan(self.conn, printers[0]["id"], _slot_plan(plan, []))

    def job_sent(self, dev_id, name, plate_index=-1, mapping=None):
        with self._lock:
            plan = self.plans.get(plate_index) if plate_index >= 0 else None  # unknown plate: do not guess
            if plan:
                self._pending[dev_id] = (plan, name, self.clock(), mapping)
            else:
                self._pending.pop(dev_id, None)  # an older plan must not be taken by this print

    def _take_pending(self, dev_id, job_name):
        with self._lock:
            item = self._pending.get(dev_id)
            if item and self.clock() - item[2] > PENDING_TTL_S:
                del self._pending[dev_id]
                return None
            if item and _same_name(item[1], job_name):
                del self._pending[dev_id]
                return item
        return None

    def state_changed(self, dev_id, status, state):
        printer = next((p for p in inv.list_printers(self.conn) if p["serial"] == dev_id), None)
        if printer is None:
            return []
        status = status or {}
        cur = status.get("job_id") or None
        cur = None if cur == "0" else cur
        layer = status.get("layer")
        layer = layer if isinstance(layer, int) and layer > 0 else None  # 0 or negative: unknown
        row = self.conn.execute("SELECT id, name, plan_json FROM job WHERE printer_id = ? AND state = 'running'"
                                " ORDER BY id DESC LIMIT 1", (printer["id"],)).fetchone()
        stored = json.loads(row["plan_json"] or "{}").get("printer_job_id") if row else None
        other_job = bool(stored and cur and stored != cur)  # the layer then belongs to the new job
        # State events arrive only at transitions, so an older layer would be far too low: unknown means ask.
        last = None if other_job else layer
        out = []
        if row:
            end = None
            if state == "IDLE" or other_job:
                end = ("failed", True)  # the end of that job was never reported
            elif state == "FINISH":
                end = ("finished", False)
            elif state == "FAILED":
                end = ("cancelled" if status.get("print_error") == CANCEL_ERROR else "failed", False)
            if end:
                out.append(self._end(printer, row, end[0], last, end[1]))
                row = None
        if row is None and state in ACTIVE:
            out.append(self._start(printer, dev_id, status, cur))
        return out

    def _start(self, printer, dev_id, status, cur):
        pend = self._take_pending(dev_id, status.get("job_name"))
        plan = _slot_plan(pend[0], status.get("trays") or [], pend[3]) if pend else {"slots": {}, "no_plan": True}
        if pend and pend[3]:
            plan = {**plan, "slot_mapping": pend[3]}  # kept with the job: how its slots were chosen
        if cur:
            plan = {**plan, "printer_job_id": cur}
        # Recorded so a real print shows whether the sent project name and the printer's job name ever match.
        plan = {**plan, "printer_job_name": status.get("job_name") or "", **({"sent_name": pend[1]} if pend else {})}
        name = status.get("job_name") or (pend[1] if pend else None) or "Unknown print"
        job_id = inv.start_job(self.conn, printer["id"], name, plan)
        slots = json.loads(self.conn.execute("SELECT plan_json FROM job WHERE id = ?", (job_id,)).fetchone()[0])["slots"]
        unassigned = [s for s, i in slots.items() if i["spool_id"] is None]
        note = ("Tracking this print." if pend else
                "No slice result for this print, so its usage is unknown: enter it manually when it ends.")
        if unassigned:
            note += " No spool is assigned to: " + ", ".join(unassigned) + "."
        return {"event": "job_started", "printer": printer["name"], "printer_id": printer["id"], "job": name,
                "deducted": [], "unassigned": unassigned, "manual": not pend, "note": note}

    def _end(self, printer, row, state, last, lost):
        unassigned = inv.finish_job(self.conn, row["id"], state, last)
        deducted = [dict(r) for r in self.conn.execute(
            "SELECT spool_id, grams, source FROM usage WHERE job_id = ? ORDER BY id", (row["id"],))]
        plan = json.loads(row["plan_json"] or "{}")
        # Nothing to deduct from: no slice result, or a stopped print whose layer is unknown.
        manual = bool(plan.get("no_plan")) or (state != "finished" and last is None and bool(plan.get("slots")))
        note = "Usage unknown, enter it manually." if manual else ""
        if manual and not plan.get("no_plan"):
            note = "Usage unknown (the printer reported no layer), enter it manually."
        if lost and not manual:
            note = f"The end of this print was not reported; usage estimated up to layer {last}."
        elif lost:
            note = "The end of this print was not reported. " + note
        elif state != "finished" and not manual:
            note = f"Estimated from layer {last}, about one layer either way."
        if unassigned:
            note = (note + " " if note else "") + "No spool was assigned to: " + ", ".join(unassigned) + "."
        return {"event": "job_lost" if lost else KINDS[state], "printer": printer["name"],
                "printer_id": printer["id"], "job": row["name"], "deducted": deducted, "unassigned": unassigned,
                "manual": manual, "note": note}
