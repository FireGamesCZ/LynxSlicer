"""lynx_spools.py with a stub `orca` module: the host hands on_message a dict (or a str if it was not JSON)."""
import importlib.util
import os
import sys
import tempfile
import types
import unittest
import enum
import json

PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin", "lynx_spools.py")


class Base:
    def post_message(self, data):
        self.posted.append(data)


class Ev(enum.Enum):
    SlicingJobComplete = 1
    SendJobStarted = 2
    PrintJobStarted = 5
    ProjectClosed = 6
    PrintStateChanged = 3
    DeviceOnline = 4


def ctx(**kw):
    return types.SimpleNamespace(**{"name": "", "code": Ev.DeviceOnline, "msg": "", "device_id": "", "index": 0, **kw})


STATS = json.dumps({"summary": {"filaments": [{"id": 0, "weight": 10.0}]}, "layers": [{"weight": 10.0}]})


class TestPlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        orca = types.SimpleNamespace(
            pages=types.SimpleNamespace(PagesPluginCapabilityBase=Base),
            host=types.SimpleNamespace(plugin=types.SimpleNamespace(storage=lambda: self.tmp.name)),
            plugin=lambda c: c, base=object, register_capability=lambda c: None)
        old = sys.modules.get("orca")
        sys.modules["orca"] = orca
        self.addCleanup(lambda: sys.modules.__setitem__("orca", old) if old else sys.modules.pop("orca", None))
        spec = importlib.util.spec_from_file_location("lynx_spools_under_test", PLUGIN)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.page = mod.SpoolsPage()
        self.page.posted = []
        self.addCleanup(lambda: self.page.conn and self.page.conn.close())
        self.addCleanup(self.tmp.cleanup)

    def host(self, **fns):
        sys.modules["orca"].host.__dict__.update(fns)

    def tracking_host(self):
        self.host(slice_statistics=lambda plate=-1: STATS,
                  device_status=lambda dev: {"state": "RUNNING", "percent": 0, "layer": 1, "total_layers": None,
                                             "job_name": "cube", "job_id": "1", "gcode_file": "", "print_error": 0,
                                             "trays": []})
        self.page.on_message({"id": 1, "op": "add_printer", "args": {"name": "P1", "driver": "bambu", "serial": "SN"}})
        self.page.posted.clear()

    def test_wiring_slice_send_run_finish(self):
        self.tracking_host()
        self.page.on_lifecycle_event(Ev.SlicingJobComplete, ctx(code=types.SimpleNamespace(name="Ok")))
        self.assertEqual(self.page.posted.pop()["push"], "plan_check")
        self.page.on_lifecycle_event(Ev.PrintJobStarted, ctx(device_id="SN", name="cube"))
        self.page.on_lifecycle_event(Ev.PrintStateChanged, ctx(name="SN", msg="RUNNING"))
        self.page.on_lifecycle_event(Ev.PrintStateChanged, ctx(name="SN", msg="FINISH"))
        started, finished = (m["events"][0]["event"] for m in self.page.posted)
        self.assertEqual((started, finished), ("job_started", "job_finished"))

    def run_print(self, send_event):
        self.tracking_host()
        self.page.on_lifecycle_event(Ev.SlicingJobComplete, ctx(code=types.SimpleNamespace(name="Ok")))
        self.page.on_lifecycle_event(send_event, ctx(device_id="SN", name="cube"))
        self.page.posted.clear()
        self.page.on_lifecycle_event(Ev.PrintStateChanged, ctx(name="SN", msg="RUNNING"))
        return self.page.posted[0]["events"][0]

    def test_upload_only_creates_no_pending_plan(self):
        self.assertTrue(self.run_print(Ev.SendJobStarted)["manual"])

    def test_plate_index_is_passed_and_project_close_clears(self):
        seen = []
        self.tracking_host()
        self.host(slice_statistics=lambda plate=-1: seen.append(plate) or STATS)
        self.page.on_lifecycle_event(Ev.SlicingJobComplete, ctx(code=types.SimpleNamespace(name="Ok"), index=2))
        self.page.on_lifecycle_event(Ev.SlicingJobComplete, ctx(code=types.SimpleNamespace(name="Ok"), index=-5))
        self.assertEqual(seen, [2, -1])
        self.page.on_lifecycle_event(Ev.ProjectClosed, ctx())
        self.assertEqual(self.page.tracker.plans, {})

    def test_failed_slice_and_unrelated_events_push_nothing(self):
        self.tracking_host()
        self.page.on_lifecycle_event(Ev.SlicingJobComplete, ctx(code=types.SimpleNamespace(name="Error")))
        self.page.on_lifecycle_event(Ev.DeviceOnline, ctx(name="SN"))
        self.page.on_lifecycle_event(Ev.SendJobStarted, ctx(device_id="SN", name="x"))  # nothing sliced yet
        self.assertEqual(self.page.posted, [])

    def test_handler_never_raises(self):
        self.host(slice_statistics=lambda: "not json", device_status=lambda d: 1 / 0)
        self.page.on_lifecycle_event(Ev.SlicingJobComplete, ctx(code=types.SimpleNamespace(name="Ok")))
        self.page.on_lifecycle_event(Ev.PrintStateChanged, ctx(name="SN", msg="RUNNING"))
        self.page.on_lifecycle_event(None, None)

    def test_missing_host_functions_degrade(self):
        self.page.on_lifecycle_event(Ev.SlicingJobComplete, ctx(code=types.SimpleNamespace(name="Ok")))
        self.page.on_lifecycle_event(Ev.PrintStateChanged, ctx(name="SN", msg="RUNNING"))
        self.assertEqual(self.page.posted, [])
        self.page.on_message({"id": 2, "op": "tracking_status"})
        self.assertIn("Print tracking is off", self.page.posted[0]["result"]["note"])
        self.tracking_host()
        self.page.on_message({"id": 3, "op": "tracking_status"})
        self.assertIsNone(self.page.posted[-1]["result"]["note"])

    def test_dict_request(self):
        self.page.on_message({"id": 7, "op": "add_printer", "args": {"name": "P1", "driver": "bambu"}})
        self.page.on_message({"id": 8, "op": "list_printers"})
        first, second = self.page.posted
        self.assertTrue(first["ok"] and first["id"] == 7, first)
        self.assertEqual((second["id"], second["ok"], second["result"][0]["name"]), (8, True, "P1"))

    def test_str_request(self):
        self.page.on_message('{"id": 3, "op": "list_spools"}')
        self.assertEqual(self.page.posted, [{"id": 3, "ok": True, "result": []}])

    def test_garbage_gets_error_reply(self):
        for msg in (None, [], 5, "not json", {}, {"id": 4}, {"id": 5, "op": "nope"}):
            self.page.posted.clear()
            self.page.on_message(msg)
            reply, = self.page.posted
            self.assertFalse(reply["ok"], msg)
            self.assertIsInstance(reply["error"], str)
            if isinstance(msg, dict):
                self.assertEqual(reply["id"], msg.get("id"))

    def test_error_keeps_id_when_storage_fails(self):
        sys.modules["orca"].host.plugin.storage = lambda: (_ for _ in ()).throw(RuntimeError("no storage"))
        self.page.on_message({"id": 11, "op": "list_spools"})
        reply, = self.page.posted
        self.assertEqual((reply["id"], reply["ok"]), (11, False))


if __name__ == "__main__":
    unittest.main()
