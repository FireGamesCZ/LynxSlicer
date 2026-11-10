import json
import os
import sqlite3
import tempfile
import unittest

from lynx_core import inventory as inv

PLAN = {"slots": {"ams0-0": {"total_g": 10.0, "by_layer_g": [2.0, 6.0, 10.0]},
                  "ext": {"total_g": 5.0, "by_layer_g": [5.0]}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.c = inv.connect(":memory:")
        self.f = inv.add_filament(self.c, vendor="V", material="PLA", spool_tare_g=200.0)
        self.p = inv.add_printer(self.c, name="p1p", driver="bambu")
        self.s = inv.add_spool(self.c, filament_id=self.f, initial_g=1000.0)


class TestInventory(Base):
    def test_remaining_undo(self):
        inv.log_usage(self.c, self.s, 100, "slicer")
        u = inv.log_usage(self.c, self.s, 50, "manual")
        inv.log_usage(self.c, self.s, -10, "manual")
        self.assertEqual(inv.remaining_g(self.c, self.s), 860)
        inv.undo_usage(self.c, u)
        self.assertEqual(inv.remaining_g(self.c, self.s), 910)

    def test_weigh(self):
        inv.log_usage(self.c, self.s, 100, "slicer")
        inv.weigh_spool(self.c, self.s, 700.0)
        self.assertEqual(inv.remaining_g(self.c, self.s), 500.0)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM usage WHERE source='weighed'").fetchone()[0], 1)

    def test_weigh_needs_tare(self):
        f = inv.add_filament(self.c, material="PETG")
        s = inv.add_spool(self.c, filament_id=f, initial_g=1000)
        with self.assertRaises(ValueError):
            inv.weigh_spool(self.c, s, 500)

    def test_reassign_slot(self):
        s2 = inv.add_spool(self.c, filament_id=self.f, initial_g=500)
        inv.assign_spool(self.c, self.s, self.p, "ext")
        inv.assign_spool(self.c, s2, self.p, "ext")
        self.assertIsNone(inv.get_spool(self.c, self.s)["slot"])
        self.assertEqual(inv.get_spool(self.c, s2)["slot"], "ext")

    def test_calibration(self):
        inv.set_calibration(self.c, self.f, self.p, 0.4, "flow_ratio", 0.95, "default")
        inv.set_calibration(self.c, self.f, self.p, 0.4, "flow_ratio", 0.97, "calibrated")
        self.assertEqual(inv.get_calibrations(self.c, self.f, self.p, 0.4), {"flow_ratio": (0.97, "calibrated")})
        with self.assertRaises(ValueError):
            inv.set_calibration(self.c, self.f, self.p, 0.4, "bogus", 1, "default")

    def test_estimate_partial(self):
        e = inv.estimate_partial_g
        self.assertEqual(e([2, 6, 10], 0), 0.0)
        self.assertEqual(e([2, 6, 10], -3), 0.0)
        self.assertEqual(e([2, 6, 10], 1), 1.0)
        self.assertEqual(e([2, 6, 10], 2), 4.0)
        self.assertEqual(e([2, 6, 10], 3), 8.0)
        self.assertEqual(e([2, 6, 10], 9), 10)
        self.assertEqual(e([], 2), 0.0)


class TestJobs(Base):
    def setUp(self):
        super().setUp()
        inv.assign_spool(self.c, self.s, self.p, "ams0-0")  # "ext" stays unassigned

    def test_finished_and_idempotent(self):
        j = inv.start_job(self.c, self.p, "cube", PLAN)
        self.assertEqual(inv.finish_job(self.c, j, "finished"), ["ext"])
        self.assertEqual(inv.remaining_g(self.c, self.s), 990)
        inv.finish_job(self.c, j, "finished")
        inv.finish_job(self.c, j, "failed", last_layer=2)
        self.assertEqual(inv.remaining_g(self.c, self.s), 990)

    def test_failed(self):
        j = inv.start_job(self.c, self.p, "cube", PLAN)
        inv.finish_job(self.c, j, "failed", last_layer=2)
        self.assertEqual(inv.remaining_g(self.c, self.s), 996)
        self.assertEqual(self.c.execute("SELECT source FROM usage").fetchone()[0], "estimate")

    def test_failed_without_layer_logs_nothing(self):
        j = inv.start_job(self.c, self.p, "cube", PLAN)
        inv.finish_job(self.c, j, "cancelled")
        self.assertEqual(inv.remaining_g(self.c, self.s), 1000)
        self.assertEqual(self.c.execute("SELECT state FROM job").fetchone()[0], "cancelled")

    def test_invalid_state_rejected(self):
        j = inv.start_job(self.c, self.p, "cube", PLAN)
        for st in ("FINISH", "running"):
            with self.assertRaises(ValueError):
                inv.finish_job(self.c, j, st, last_layer=2)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 0)
        self.assertEqual(self.c.execute("SELECT state FROM job").fetchone()[0], "running")
        inv.finish_job(self.c, j, "finished")
        self.assertEqual(inv.remaining_g(self.c, self.s), 990)

    def test_failure_midway_rolls_back(self):
        s2 = inv.add_spool(self.c, filament_id=self.f, initial_g=1000)
        inv.assign_spool(self.c, s2, self.p, "ext")
        j = inv.start_job(self.c, self.p, "cube", PLAN)
        orig, n = inv._insert, [0]

        def flaky(conn, table, fields):
            n[0] += 1
            if n[0] == 2:
                raise OSError("disk")
            return orig(conn, table, fields)
        inv._insert = flaky
        try:
            with self.assertRaises(OSError):
                inv.finish_job(self.c, j, "finished")
        finally:
            inv._insert = orig
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 0)
        self.assertEqual(self.c.execute("SELECT state FROM job").fetchone()[0], "running")
        inv.finish_job(self.c, j, "finished")
        self.assertEqual(inv.remaining_g(self.c, self.s), 990)
        self.assertEqual(inv.remaining_g(self.c, s2), 995)

    def test_two_connections_finish_once(self):
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, "x.db")
            c1 = inv.connect(path)
            f = inv.add_filament(c1, material="PLA")
            p = inv.add_printer(c1, name="p", driver="bambu")
            s = inv.add_spool(c1, filament_id=f, initial_g=1000.0)
            inv.assign_spool(c1, s, p, "ams0-0")
            j = inv.start_job(c1, p, "x", PLAN)
            c2 = inv.connect(path)
            inv.finish_job(c1, j, "finished")
            inv.finish_job(c2, j, "finished")
            self.assertEqual(inv.remaining_g(c1, s), 990)
            c1.close()
            c2.close()

    def test_swapped_spool_not_charged(self):
        s2 = inv.add_spool(self.c, filament_id=self.f, initial_g=1000)
        j = inv.start_job(self.c, self.p, "cube", PLAN)
        inv.assign_spool(self.c, s2, self.p, "ams0-0")
        self.assertEqual(inv.finish_job(self.c, j, "finished"), ["ext"])
        self.assertEqual(inv.remaining_g(self.c, self.s), 990)
        self.assertEqual(inv.remaining_g(self.c, s2), 1000)

    def test_add_spool_with_slot_evicts(self):
        s2 = inv.add_spool(self.c, filament_id=self.f, initial_g=500, printer_id=self.p, slot="ams0-0")
        self.assertIsNone(inv.get_spool(self.c, self.s)["slot"])
        self.assertEqual(inv.get_spool(self.c, s2)["slot"], "ams0-0")

    def test_unique_slot_index(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("UPDATE spool SET printer_id = ?, slot = 'ext'", (self.p,))
            self.c.execute("INSERT INTO spool(filament_id, initial_g, printer_id, slot) VALUES (?, 1, ?, 'ext')",
                           (self.f, self.p))

    def test_bad_column_rejected(self):
        with self.assertRaises(ValueError):
            inv.add_filament(self.c, material="PLA", **{"notes) VALUES ('x'); DROP TABLE spool; --": 1})
        with self.assertRaises(ValueError):
            inv.add_spool(self.c, filament_id=self.f, initial_g=1, bogus=1)
        self.assertEqual(len(inv.list_spools(self.c)), 1)

    def test_check_enough(self):
        inv.log_usage(self.c, self.s, 995, "manual")
        self.assertEqual(inv.check_enough(self.c, self.p, PLAN), [("ams0-0", self.s, 10.0, 5.0)])
        self.assertEqual(inv.check_enough(self.c, self.p, {"slots": {}}), [])


if __name__ == "__main__":
    unittest.main()
