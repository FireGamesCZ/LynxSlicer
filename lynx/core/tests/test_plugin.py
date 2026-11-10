"""lynx_spools.py with a stub `orca` module: the host hands on_message a dict (or a str if it was not JSON)."""
import importlib.util
import os
import sys
import tempfile
import types
import unittest

PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin", "lynx_spools.py")


class Base:
    def post_message(self, data):
        self.posted.append(data)


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
