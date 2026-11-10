import json
import os
import unittest

from lynx_core.plan import default_mapping, plan_from_statistics, remap_plan

REAL = ("/tmp/claude-1000/-home-jkosinka-Documents-Code-LynxSlicer/e653222d-6369-4bc8-9e13-25c516aac38a/"
        "scratchpad/stats2/out/plate_1.statistics.json")


def stats(filaments, layers):
    return {"summary": {"filaments": [{"id": i, "weight": w} for i, w in filaments]}, "layers": layers}


def layer(w, **by_id):
    return {"weight": w, "filaments": [{"id": int(i[1:]), "weight": g} for i, g in by_id.items()]}


class TestPlan(unittest.TestCase):
    def test_single_filament(self):
        p = plan_from_statistics(stats([(1, 3.0)], [layer(1, f1=1), layer(2, f1=2)]))
        self.assertEqual(p, {"slots": {"1": {"total_g": 3.0, "by_layer_g": [1, 3]}}})

    def test_absent_filament_carries_running_sum(self):
        p = plan_from_statistics(stats([(1, 3), (2, 2)], [layer(1, f1=1), layer(3, f1=1, f2=2), layer(1, f1=1)]))["slots"]
        self.assertEqual(p["1"]["by_layer_g"], [1, 2, 3])
        self.assertEqual(p["2"]["by_layer_g"], [0, 2, 2])

    def test_flush_gap_is_spread_by_extrusion(self):
        p = plan_from_statistics(stats([(1, 5.0)], [layer(1, f1=1), layer(3, f1=3)]))["slots"]["1"]
        self.assertEqual(p["by_layer_g"], [1.25, 5.0])
        self.assertEqual((p["total_g"], p["by_layer_g"][-1]), (5.0, 5.0))

    def test_flush_with_no_extrusion_lands_on_last_layer(self):
        p = plan_from_statistics(stats([(1, 1), (2, 2)], [layer(1, f1=1), layer(0)]))["slots"]["2"]
        self.assertEqual(p["by_layer_g"], [0, 2])

    def test_old_format(self):
        old = {"summary": {"filaments": [{"id": 1, "weight": 3}]}, "layers": [{"weight": 1}, {"weight": 2}]}
        self.assertEqual(plan_from_statistics(old)["slots"]["1"]["by_layer_g"], [1, 3])
        old["summary"]["filaments"].append({"id": 2, "weight": 1})
        with self.assertRaisesRegex(ValueError, "per-filament"):
            plan_from_statistics(old)

    @unittest.skipUnless(os.path.exists(REAL), "real statistics file not present")
    def test_real_file(self):
        with open(REAL) as f:
            d = json.load(f)
        slot = plan_from_statistics(d)["slots"]["1"]
        self.assertEqual(len(slot["by_layer_g"]), len(d["layers"]))
        self.assertEqual((slot["total_g"], slot["by_layer_g"][-1]), (d["summary"]["weight"],) * 2)


class TestRemap(unittest.TestCase):
    PLAN = {"slots": {"1": {"total_g": 2.0, "by_layer_g": [2.0]}, "2": {"total_g": 0, "by_layer_g": [0]}}}

    def test_remap(self):
        self.assertEqual(remap_plan(self.PLAN, {"1": "ext"})["slots"], {"ext": self.PLAN["slots"]["1"]})

    def test_unmapped_used_filament(self):
        with self.assertRaisesRegex(ValueError, "filament 1"):
            remap_plan(self.PLAN, {"2": "ams1"})

    def test_two_filaments_one_slot(self):
        plan = {"slots": {"1": {"total_g": 1}, "2": {"total_g": 1}}}
        with self.assertRaisesRegex(ValueError, "more than one"):
            remap_plan(plan, {"1": "ext", "2": "ext"})

    def test_default_mapping(self):
        one = {"slots": {"1": {"total_g": 2.0}}}
        self.assertEqual(default_mapping(one), {"1": "ext"})
        with self.assertRaises(ValueError):
            default_mapping(self.PLAN)


if __name__ == "__main__":
    unittest.main()
