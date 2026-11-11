import threading
import unittest

from lynx_core import inventory as inv
from lynx_core.bambu import CANCEL_ERROR
from lynx_core.tracker import PENDING_TTL_S, Tracker

STATS = {"summary": {"filaments": [{"id": 0, "weight": 10.0}]},
         "layers": [{"weight": 2.0} for _ in range(5)]}
STATS2 = {"summary": {"filaments": [{"id": 0, "weight": 7.0}]}, "layers": [{"weight": 7.0}]}
AMS = [{"slot": "ams0-1", "exists": True}]


def status(**kw):
    """A full device_status dict as the host returns it; layer is None when unknown."""
    return {"state": "RUNNING", "percent": 0, "layer": None, "total_layers": None, "job_name": "cube",
            "job_id": "7", "gcode_file": "", "print_error": 0, "trays": [], **kw}


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


class TestTracker(unittest.TestCase):
    def setUp(self):
        self.conn = inv.connect(":memory:")
        self.pid = inv.add_printer(self.conn, name="P1", driver="bambu", serial="SN1")
        fil = inv.add_filament(self.conn, material="PLA")
        self.spool = inv.add_spool(self.conn, filament_id=fil, initial_g=1000, printer_id=self.pid, slot="ext")
        self.clock = Clock()
        self.t = Tracker(self.conn, self.clock)

    def sent(self, name="cube", dev="SN1", plate=0):
        self.t.sliced(STATS, plate)
        self.t.job_sent(dev, name, plate)

    def st(self, state, dev="SN1", **kw):
        return self.t.state_changed(dev, status(**kw), state)

    def used(self):
        return self.conn.execute("SELECT grams, source FROM usage").fetchall()

    def test_normal_print_deducts_once(self):
        self.sent()
        ev, = self.st("RUNNING")
        self.assertEqual(ev["event"], "job_started")
        self.assertEqual(self.st("PAUSE"), [])
        ev, = self.st("FINISH", layer=5)
        self.assertEqual(ev["event"], "job_finished")
        self.assertEqual(ev["deducted"], [{"spool_id": self.spool, "grams": 10.0, "source": "slicer"}])
        self.assertFalse(ev["manual"])
        self.assertEqual(self.st("FINISH"), [])
        self.assertEqual(len(self.used()), 1)

    def test_cancel_estimates_and_error_code_decides(self):
        self.sent()
        self.st("RUNNING")
        ev, = self.st("FAILED", layer=3, print_error=CANCEL_ERROR)
        self.assertEqual(ev["event"], "job_cancelled")
        self.assertEqual((ev["deducted"][0]["source"], ev["deducted"][0]["grams"]), ("estimate", 5.0))
        self.assertIn("Estimated", ev["note"])
        self.sent()
        self.st("RUNNING", job_id="8")
        ev, = self.st("FAILED", job_id="8", layer=2, print_error=0x12345)
        self.assertEqual(ev["event"], "job_failed")

    def test_restart_mid_print_then_finish(self):
        self.sent()
        self.st("RUNNING")
        t2 = Tracker(self.conn, self.clock)
        self.assertEqual(t2.state_changed("SN1", status(), "RUNNING"), [])
        ev, = t2.state_changed("SN1", status(layer=5), "FINISH")
        self.assertEqual(len(ev["deducted"]), 1)
        self.assertEqual(Tracker(self.conn).state_changed("SN1", status(), "FINISH"), [])
        self.assertEqual(len(self.used()), 1)

    def test_restart_after_print_ended(self):
        self.sent()
        self.st("RUNNING")
        self.st("FINISH")
        self.assertEqual(Tracker(self.conn).state_changed("SN1", status(), "FINISH"), [])
        self.assertEqual(len(self.used()), 1)

    def test_lost_job(self):
        self.sent()
        self.st("RUNNING", layer=4)
        ev, = self.st("IDLE", layer=4)
        self.assertEqual(ev["event"], "job_lost")
        self.assertEqual(ev["deducted"][0]["source"], "estimate")
        # the layer seen at RUNNING is not reused when the end reports none
        self.sent()
        self.st("RUNNING", layer=4)
        ev, = self.st("IDLE")
        self.assertTrue(ev["manual"])
        self.assertEqual(ev["deducted"], [])
        # a different printer job id while running: old one lost, new one started
        self.sent()
        self.st("RUNNING", job_id="8", layer=1)
        a, b = self.st("RUNNING", job_id="9")
        self.assertEqual((a["event"], b["event"]), ("job_lost", "job_started"))

    def test_lost_after_restart_has_no_layer(self):
        self.sent()
        self.st("RUNNING")
        ev, = Tracker(self.conn).state_changed("SN1", status(), "IDLE")
        self.assertEqual((ev["event"], ev["manual"], ev["deducted"]), ("job_lost", True, []))

    def test_finished_job_id_differs_means_lost(self):
        self.sent()
        self.st("RUNNING")
        ev, = Tracker(self.conn).state_changed("SN1", status(job_id="99"), "FINISH")
        self.assertEqual(ev["event"], "job_lost")

    def test_started_elsewhere_needs_manual_usage(self):
        ev, = self.st("RUNNING")
        self.assertTrue(ev["manual"])
        ev, = self.st("FINISH")
        self.assertEqual((ev["deducted"], ev["manual"]), ([], True))
        self.assertIn("manually", ev["note"])
        self.assertEqual(self.used(), [])

    def test_stale_or_foreign_plan_not_applied(self):
        self.sent()
        self.clock.t += PENDING_TTL_S + 1
        ev, = self.st("RUNNING")
        self.assertTrue(ev["manual"])
        self.st("FINISH")
        self.sent("other")
        ev, = self.st("RUNNING", job_id="8")  # job name "cube" does not match what was sent
        self.assertTrue(ev["manual"])

    def test_unknown_device_and_prepare_ignored(self):
        self.sent()
        self.assertEqual(self.st("RUNNING", dev="OTHER"), [])
        self.assertEqual(self.st("PREPARE"), [])
        self.assertEqual(self.st("SLICING"), [])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM job").fetchone()[0], 0)

    def test_no_status_path(self):
        self.sent()
        self.assertEqual(self.t.state_changed("SN1", None, "RUNNING")[0]["event"], "job_started")
        ev, = self.t.state_changed("SN1", None, "FINISH")
        self.assertEqual(len(ev["deducted"]), 1)
        self.sent()
        self.t.state_changed("SN1", None, "RUNNING")
        ev, = self.t.state_changed("SN1", None, "FAILED")
        self.assertEqual((ev["deducted"], ev["manual"]), ([], True))

    def test_job_sent_from_another_thread(self):
        self.t.sliced(STATS, 0)
        th = threading.Thread(target=self.t.job_sent, args=("SN1", "cube", 0))
        th.start()
        th.join()
        self.assertEqual(self.st("RUNNING")[0]["manual"], False)

    def test_ams_plan_is_left_unassigned(self):
        self.sent()
        ev, = self.st("RUNNING", trays=AMS)
        self.assertEqual(ev["unassigned"], ["0"])
        ev, = self.st("FINISH")
        self.assertEqual((ev["deducted"], ev["unassigned"]), ([], ["0"]))

    def test_sliced_returns_check_for_single_printer(self):
        r = self.t.sliced(STATS)
        self.assertEqual(r["slots"][0]["slot"], "ext")
        inv.add_printer(self.conn, name="P2", driver="bambu")
        self.assertIsNone(self.t.sliced(STATS))
        with self.assertRaises(ValueError):
            self.t.sliced({"summary": {"filaments": [{"id": 0, "weight": 1}, {"id": 1, "weight": 1}]},
                           "layers": [{"weight": 2}]})
        self.assertNotIn(-1, self.t.plans)

    def test_unknown_layer_is_manual_never_zero_grams(self):
        for state, extra in (("FAILED", {}), ("FAILED", {"print_error": CANCEL_ERROR}), ("IDLE", {})):
            for layer in (0, None, -1):
                self.sent()
                self.st("RUNNING", job_id="5")
                t2 = Tracker(self.conn)  # restarted: no remembered layer
                ev, = t2.state_changed("SN1", status(job_id="5", layer=layer, **extra), state)
                self.assertEqual((ev["manual"], ev["deducted"]), (True, []), (state, layer))
                self.assertIn("manually", ev["note"])
        self.assertEqual(self.used(), [])

    def test_plan_is_per_plate(self):
        self.t.sliced(STATS, 0)
        self.t.sliced(STATS2, 1)
        self.t.job_sent("SN1", "cube", 0)
        self.st("RUNNING")
        ev, = self.st("FINISH")
        self.assertEqual(ev["deducted"][0]["grams"], 10.0)
        self.t.job_sent("SN1", "cube", 1)
        self.st("RUNNING", job_id="8")
        ev, = self.st("FINISH", job_id="8")
        self.assertEqual(ev["deducted"][0]["grams"], 7.0)

    def test_unknown_or_unsliced_plate_gives_no_plan(self):
        self.t.sliced(STATS, 0)
        for plate in (-1, 3):
            self.t.job_sent("SN1", "cube", plate)
            self.assertTrue(self.st("RUNNING", job_id=str(10 + plate))[0]["manual"])
            self.st("FINISH", job_id=str(10 + plate))
        self.t.job_sent("SN1", "cube", 0)
        self.t.job_sent("SN1", "cube", 3)  # the older pending plan must not survive
        self.assertTrue(self.st("RUNNING", job_id="20")[0]["manual"])

    def test_reslice_replaces_and_clear_drops(self):
        self.t.sliced(STATS, 0)
        self.t.sliced(STATS2, 0)
        self.t.job_sent("SN1", "cube", 0)
        self.st("RUNNING")
        self.assertEqual(self.st("FINISH")[0]["deducted"][0]["grams"], 7.0)
        self.t.clear()
        self.t.job_sent("SN1", "cube", 0)
        self.assertTrue(self.st("RUNNING", job_id="8")[0]["manual"])

    def test_names_recorded_and_mismatch_needs_both(self):
        self.sent("cube")
        self.st("RUNNING", job_name="")  # printer name unknown: plan applies
        row = self.conn.execute("SELECT plan_json FROM job").fetchone()[0]
        self.assertIn('"sent_name": "cube"', row)
        self.st("FINISH")
        self.sent("cube")
        self.st("RUNNING", job_id="8", job_name="other")
        row = self.conn.execute("SELECT plan_json FROM job ORDER BY id DESC").fetchone()[0]
        self.assertIn('"printer_job_name": "other"', row)
        self.assertIn('"no_plan": true', row)

    def test_same_state_new_job_id_ends_old_as_lost_without_new_layer(self):
        self.sent()
        self.st("RUNNING", layer=4)
        self.sent()
        a, b = self.st("RUNNING", job_id="8", layer=2)  # layer 2 belongs to the new job
        self.assertEqual((a["event"], b["event"]), ("job_lost", "job_started"))
        self.assertEqual((a["manual"], a["deducted"]), (True, []))
        self.assertEqual(self.used(), [])

    def test_pause_then_running_does_not_restart(self):
        self.sent()
        self.assertEqual(len(self.st("RUNNING")), 1)
        self.assertEqual(self.st("PAUSE", layer=2), [])
        self.assertEqual(self.st("RUNNING", layer=2), [])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM job").fetchone()[0], 1)

    def test_two_printers_interleaved_and_pending_not_shared(self):
        inv.add_printer(self.conn, name="P2", driver="bambu", serial="SN2")
        self.sent(dev="SN1")
        ev, = self.st("RUNNING", dev="SN2", job_id="70")  # printer B: A's plan is not consumed
        self.assertTrue(ev["manual"])
        a, = self.st("RUNNING", dev="SN1")
        self.assertFalse(a["manual"])
        self.assertEqual(self.st("FINISH", dev="SN2", job_id="70")[0]["deducted"], [])
        ev, = self.st("FINISH", dev="SN1")
        self.assertEqual(len(ev["deducted"]), 1)


if __name__ == "__main__":
    unittest.main()
