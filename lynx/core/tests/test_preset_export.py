import json
import tempfile
import unittest
from pathlib import Path

from lynx_core import inventory as inv
from lynx_core.preset_export import filament_preset, write_preset


class TestPreset(unittest.TestCase):
    def setUp(self):
        self.c = inv.connect(":memory:")
        self.f = inv.add_filament(self.c, vendor="Acme", material="PLA", name="Red", color_hex="#FF0000",
                                  density_g_cm3=1.24, nozzle_temp_min=190, nozzle_temp_max=230, bed_temp=60)
        self.p = inv.add_printer(self.c, name="p1p", driver="bambu")
        self.s = inv.add_spool(self.c, filament_id=self.f, initial_g=1000)
        inv.set_calibration(self.c, self.f, self.p, 0.4, "flow_ratio", 0.93, "calibrated")
        inv.set_calibration(self.c, self.f, self.p, 0.4, "nozzle_temp", 212, "calibrated")
        inv.set_calibration(self.c, self.f, self.p, 0.4, "pressure_advance", 0.04, "calibrated")

    def test_shape_and_values(self):
        d = filament_preset(self.c, self.s, self.p, 0.4, "Generic PLA @base")
        self.assertEqual((d["from"], d["inherits"], d["type"]), ("User", "Generic PLA @base", "filament"))
        self.assertEqual(d["filament_flow_ratio"], ["0.93"])
        self.assertEqual(d["nozzle_temperature"], ["212"])
        self.assertEqual(d["enable_pressure_advance"], ["1"])
        self.assertEqual(d["hot_plate_temp_initial_layer"], ["60"])
        self.assertEqual(d["default_filament_colour"], ["#FF0000"])
        self.assertNotIn("filament_cost", d)  # NULL -> inherit
        self.assertNotIn("filament_max_volumetric_speed", d)
        for k, v in d.items():
            if k not in ("type", "name", "inherits", "from", "version"):
                self.assertTrue(isinstance(v, list) and all(isinstance(x, str) for x in v), k)
        json.dumps(d)

    def test_name_per_printer_and_nozzle(self):
        p2 = inv.add_printer(self.c, name="x1c", driver="bambu")
        inv.set_calibration(self.c, self.f, p2, 0.6, "flow_ratio", 1.02, "calibrated")
        a = filament_preset(self.c, self.s, self.p, 0.4, "Generic PLA @base")
        b = filament_preset(self.c, self.s, p2, 0.6, "Generic PLA @base")
        self.assertNotEqual(a["name"], b["name"])
        with tempfile.TemporaryDirectory() as t:
            pa, pb = write_preset(a, t), write_preset(b, t)
            self.assertNotEqual(pa, pb)
            self.assertEqual(json.loads(pa.read_text())["filament_flow_ratio"], ["0.93"])
            self.assertEqual(json.loads(pb.read_text())["filament_flow_ratio"], ["1.02"])

    def test_write(self):
        d = filament_preset(self.c, self.s, self.p, 0.4, "Generic PLA @base")
        with tempfile.TemporaryDirectory() as t:
            path = write_preset(d, t)
            self.assertEqual(json.loads(path.read_text()), d)
            self.assertTrue(Path(t, path.stem + ".info").exists())


if __name__ == "__main__":
    unittest.main()
