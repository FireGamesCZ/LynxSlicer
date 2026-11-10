import unittest

from lynx_core import inventory as inv
from lynx_core.ui_api import handle


class Base(unittest.TestCase):
    def setUp(self):
        self.c = inv.connect(":memory:")
        self.n = 0

    def call(self, op, **args):
        self.n += 1
        r = handle(self.c, {"id": self.n, "op": op, "args": args})
        self.assertEqual(r["id"], self.n)
        return r

    def ok(self, op, **args):
        r = self.call(op, **args)
        self.assertTrue(r["ok"], r)
        return r["result"]

    def err(self, op, fragment, **args):
        r = self.call(op, **args)
        self.assertFalse(r["ok"], r)
        self.assertIn(fragment, r["error"])


class TestFlow(Base):
    def test_full_flow(self):
        f = self.ok("add_filament", vendor="Prusament", material="PLA", name="Galaxy <b>Black</b>",
                    color_hex="#1a1a1a", spool_tare_g=200)["id"]
        p = self.ok("add_printer", name="P1P", driver="bambu")["id"]
        s = self.ok("add_spool", filament_id=f, initial_g=1000, printer_id=p, slot="ext")["id"]
        self.ok("log_manual_usage", spool_id=s, grams=100, note="benchy")
        spool, = self.ok("list_spools")
        self.assertEqual((spool["remaining_g"], spool["percent"], spool["location"]), (900, 90.0, "P1P / ext"))
        self.assertEqual((spool["vendor"], spool["color_hex"], spool["name"]), ("Prusament", "#1A1A1A", "Galaxy <b>Black</b>"))
        w = self.ok("weigh_spool", spool_id=s, gross_g=1000)["usage_id"]  # 800 g of filament left
        self.assertEqual(self.ok("list_spools")[0]["remaining_g"], 800)
        self.assertEqual([u["source"] for u in self.ok("list_usage", spool_id=s)], ["weighed", "manual"])
        self.ok("undo_usage", usage_id=w)
        self.assertEqual(self.ok("list_spools")[0]["remaining_g"], 900)
        self.ok("assign_spool", spool_id=s)  # unload
        self.assertEqual(self.ok("list_spools")[0]["location"], "Not loaded")
        self.ok("archive_spool", spool_id=s)
        self.assertEqual(self.ok("list_spools"), [])
        self.assertEqual(len(self.ok("list_spools", include_archived=True)), 1)
        self.assertEqual(len(self.ok("list_usage", spool_id=s)), 1)
        self.err("log_manual_usage", "archived", spool_id=s, grams=1)

    def test_slot_is_taken_over(self):
        f = self.ok("add_filament", material="PETG")["id"]
        p = self.ok("add_printer", name="X", driver="prusalink", host="10.0.0.2")["id"]
        a = self.ok("add_spool", filament_id=f, initial_g=500)["id"]
        b = self.ok("add_spool", filament_id=f, initial_g=500, printer_id=p, slot="t1")["id"]
        self.ok("assign_spool", spool_id=a, printer_id=p, slot="t1")
        by_id = {s["id"]: s["location"] for s in self.ok("list_spools")}
        self.assertEqual(by_id, {a: "X / t1", b: "Not loaded"})


class TestBadInput(Base):
    def setUp(self):
        super().setUp()
        self.f = self.ok("add_filament", material="PLA", spool_tare_g=200)["id"]
        self.s = self.ok("add_spool", filament_id=self.f, initial_g=1000)["id"]

    def test_envelope(self):
        for msg in (None, [], "x", 5, {}, {"id": 1}, {"id": 1, "op": 7}, {"id": 1, "op": "nope"},
                    {"id": 1, "op": "list_spools", "args": []}, {"id": 1, "op": "list_spools", "args": "x"}):
            r = handle(self.c, msg)
            self.assertFalse(r["ok"], msg)
            self.assertIsInstance(r["error"], str)
        self.assertEqual(handle(self.c, {"id": 9, "op": "nope"})["id"], 9)
        self.assertTrue(handle(self.c, {"id": 1, "op": "list_spools", "args": None})["ok"])

    def test_args(self):
        self.err("list_filaments", "unexpected argument", bogus=1)
        self.err("add_spool", "missing argument", filament_id=self.f)
        self.err("add_spool", "missing argument", filament_id=self.f, initial_g=None)
        self.err("add_spool", "initial_g must be greater than 0", filament_id=self.f, initial_g=0)
        self.err("add_spool", "initial_g must be a number", filament_id=self.f, initial_g="100")
        self.err("add_spool", "initial_g must be a number", filament_id=self.f, initial_g=True)
        self.err("add_spool", "initial_g must be a number", filament_id=self.f, initial_g=float("nan"))
        self.err("add_spool", "filament_id must be a whole number", filament_id="1", initial_g=5)
        self.err("add_spool", "filament 99 does not exist", filament_id=99, initial_g=5)
        self.err("add_spool", "printer 99 does not exist", filament_id=self.f, initial_g=5, printer_id=99, slot="a")
        self.err("add_spool", "both a printer and a slot", filament_id=self.f, initial_g=5, slot="a")

    def test_huge_numbers_and_ids(self):
        for big in (1e300, 10 ** 400, 1e7 + 1):
            self.err("add_spool", "too large", filament_id=self.f, initial_g=big)
            self.err("log_manual_usage", "too large", spool_id=self.s, grams=big)
        self.err("add_filament", "too large", material="PLA", price_per_kg=1e8)
        self.err("add_filament", "too large", material="PLA", spool_tare_g=10 ** 400)
        self.ok("add_spool", filament_id=self.f, initial_g=1e7)
        for bad in (0, -1, 2 ** 63, 10 ** 30):
            self.err("log_manual_usage", "between 1 and", spool_id=bad, grams=1)
            self.err("undo_usage", "between 1 and", usage_id=bad)

    def test_filament_printer(self):
        self.err("add_filament", "material is required", material="  ")
        self.err("add_filament", "#RRGGBB", material="PLA", color_hex="red")
        self.err("add_filament", "#RRGGBB", material="PLA", color_hex="#12345")
        self.err("add_filament", "diameter_mm", material="PLA", diameter_mm=-1)
        self.err("add_filament", "spool_tare_g must not be negative", material="PLA", spool_tare_g=-5)
        self.err("add_filament", "too long", material="x" * 201)
        self.err("add_printer", "one of: bambu, prusalink", name="p", driver="octoprint")
        self.err("add_printer", "missing argument", name="p")

    def test_spool_ops(self):
        self.err("log_manual_usage", "grams must be greater than 0", spool_id=self.s, grams=0)
        self.err("log_manual_usage", "grams must be greater than 0", spool_id=self.s, grams=-3)
        self.err("log_manual_usage", "spool 99 does not exist", spool_id=99, grams=3)
        self.err("weigh_spool", "gross_g must be greater than 0", spool_id=self.s, gross_g=0)
        self.err("weigh_spool", "below the empty spool weight", spool_id=self.s, gross_g=150)
        self.err("weigh_spool", "spool 99", spool_id=99, gross_g=500)
        self.err("list_usage", "spool 99", spool_id=99)
        self.err("undo_usage", "usage entry 99", usage_id=99)
        self.err("archive_spool", "spool 99", spool_id=99)
        self.err("assign_spool", "printer 99", spool_id=self.s, printer_id=99, slot="a")
        self.assertEqual(self.ok("list_spools")[0]["remaining_g"], 1000)

    def test_weigh_without_tare(self):
        f = self.ok("add_filament", material="ABS")["id"]
        s = self.ok("add_spool", filament_id=f, initial_g=800)["id"]
        self.err("weigh_spool", "empty spool weight", spool_id=s, gross_g=900)


if __name__ == "__main__":
    unittest.main()
