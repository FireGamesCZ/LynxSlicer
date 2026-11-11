# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Spools"
# description = "Spool inventory: filaments, spools, remaining grams, manual usage and weighing."
# author = "LynxSlicer"
# version = "0.1.0"
# ///
"""Spools tab. Needs the lynx_core package in the same folder as this file (see README.md).

Everything touching SQLite or the page runs on the UI thread: the page's messages arrive there and each request is
a handful of tiny SQLite statements, so no worker thread (and no `threading` permission) is used. The one
sqlite3 connection is opened lazily on that same thread. No permissions are requested.

Prints are tracked through OrcaSlicer's own events (no MQTT, no access code): slicing result, job sent, printer
state. That needs orca.host.device_status and orca.host.slice_statistics; without them the plug-in is an inventory.
"""
import json
import logging
import os

import orca

from lynx_core import inventory, spools_page, tracker, ui_api

log = logging.getLogger(__name__)
NO_TRACKING = ("Print tracking is off: this OrcaSlicer build does not provide device_status and slice_statistics. "
               "Spools are not deducted automatically; log usage by hand.")


def _name(member):
    # enum members print as "LifecycleEvent.X" or "X" depending on the binding; .name is the stable part
    return getattr(member, "name", str(member)).rsplit(".", 1)[-1]


class SpoolsPage(orca.pages.PagesPluginCapabilityBase):
    conn = None
    tracker = None

    def get_name(self):
        return "Spools"

    def get_ui(self):
        return spools_page.PAGE

    def on_message(self, message):
        # The host parses the page's JSON first, so this is normally a dict (a str only if it was not valid JSON).
        request = message
        try:
            if isinstance(message, str):
                request = json.loads(message)
            if isinstance(request, dict) and request.get("op") == "tracking_status" and not self._can_track():
                reply = {"id": request.get("id"), "ok": True, "result": {"note": NO_TRACKING}}
            else:
                reply = ui_api.handle(self._db(), request)
        except Exception as error:  # the page must always get an answer
            rid = request.get("id") if isinstance(request, dict) else None
            reply = {"id": rid, "ok": False, "error": f"Spools could not handle the request: {error}"}
        self.post_message(reply)

    def _db(self):
        if self.conn is None:  # storage() only works inside a plug-in callback, so not at import time
            self.conn = inventory.connect(os.path.join(orca.host.plugin.storage(), "spools.sqlite3"))
        return self.conn

    @staticmethod
    def _can_track():
        return all(getattr(orca.host, f, None) for f in ("device_status", "slice_statistics"))

    def on_lifecycle_event(self, event, ctx):
        try:
            self._lifecycle(_name(event), ctx)
        except Exception:  # an event handler must never raise into the host
            log.exception("Spools: could not handle %s", _name(event))

    def _lifecycle(self, event, ctx):
        if event in ("NewProject", "ProjectOpened", "ProjectClosed"):
            if self.tracker is not None:
                self.tracker.clear()  # the old project's plans must not be attached to a print of the new one
            return
        if event == "PrintJobStarted":  # not SendJobStarted: an upload alone is not a print
            # worker thread: memory only, and only if a plate was sliced (so the tracker exists)
            if self.tracker is not None:
                # slot_mapping: JSON {filament id: slot name}, "" when none; older hosts lack the attribute
                mapping = json.loads(getattr(ctx, "slot_mapping", "") or "{}")
                self.tracker.job_sent(ctx.device_id, ctx.name, getattr(ctx, "index", -1), mapping)
            return
        if event not in ("SlicingJobComplete", "PrintStateChanged") or not self._can_track():
            return
        if self.tracker is None:
            self.tracker = tracker.Tracker(self._db())
        if event == "SlicingJobComplete":
            if _name(ctx.code) != "Ok":
                return
            plate = max(getattr(ctx, "index", -1), -1)  # below 0: unknown, the host then means "all plates"
            stats = orca.host.slice_statistics(plate)
            result = self.tracker.sliced(json.loads(stats), plate) if stats else None
            if result is not None:
                self.post_message(ui_api.plan_push(result))
            return
        events = self.tracker.state_changed(ctx.name, orca.host.device_status(ctx.name), ctx.msg)
        if events:
            self.post_message(ui_api.activity_push(events))


@orca.plugin
class SpoolsPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(SpoolsPage)
