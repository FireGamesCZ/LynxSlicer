"""Fixtures in tests/fixtures are SYNTHETIC (hand-built), not recorded from a printer."""
import json
import os
import pathlib
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest

from lynx_core import bambu

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name):
    with open(os.path.join(FIX, name + ".json")) as f:
        return json.load(f)["reports"]


def replay(reports, state=None):
    state, out = state or {}, []
    for r in reports:
        state, evs = bambu.step(state, r)
        out += evs
    return state, out


STARTED = {"type": "job_started", "name": "cube", "total_layers": 100}


class Events(unittest.TestCase):
    def test_x1_full_print(self):
        state, evs = replay(load("x1_full"))
        self.assertEqual(evs, [
            STARTED,
            {"type": "progress", "layer": 50, "percent": 50},
            {"type": "job_finished", "name": "cube", "layer": 100, "total_layers": 100, "percent": 100},
        ])

    def test_p1_partial_updates(self):
        _, evs = replay(load("p1_partial"))
        self.assertEqual(evs, [
            STARTED,
            {"type": "progress", "layer": 1, "percent": 1},
            {"type": "progress", "layer": 2, "percent": 1},
            {"type": "progress", "layer": 2, "percent": 2},
            {"type": "job_finished", "name": "cube", "layer": 2, "total_layers": 100, "percent": 100},
        ])

    def test_cancel(self):
        _, evs = replay(load("x1_cancelled"))
        self.assertEqual(evs[1:], [
            {"type": "job_cancelled", "name": "cube", "layer": 10, "total_layers": 100, "percent": 10}])

    def test_failure_with_error_code(self):
        _, evs = replay(load("x1_failed"))
        self.assertEqual(evs[1:], [
            {"type": "job_failed", "name": "cube", "layer": 10, "total_layers": 100, "percent": 10,
             "error": 117473283}])

    def test_attach_mid_print(self):
        # Listener starts at the 50% report; first state is full, started once, not twice.
        _, evs = replay(load("x1_full")[2:3])
        self.assertEqual(evs, [STARTED])
        _, evs = replay(load("x1_full")[2:])
        self.assertEqual(evs[0], STARTED)
        self.assertEqual(sum(e["type"] == "job_started" for e in evs), 1)

    def test_attach_after_print_ended(self):
        state, evs = replay(load("x1_full")[3:])
        self.assertEqual(evs, [
            {"type": "job_finished", "name": "cube", "layer": 100, "total_layers": 100,
             "percent": 100, "late": True}])

    def test_idle_attach_is_silent(self):
        self.assertEqual(replay(load("x1_full")[:1])[1], [])

    def test_non_status_reply_ignored(self):
        state, evs = bambu.step({"gcode_state": "RUNNING"}, {"print": {"command": "gcode_line", "gcode_state": "FINISH"}})
        self.assertEqual((state, evs), ({"gcode_state": "RUNNING"}, []))


def push(**fields):
    return {"print": {"command": "push_status", **fields}}


def run_msgs(msgs):
    state, out = {}, []
    for m in msgs:
        state, evs = bambu.step(state, push(**m))
        out += evs
    return out


class JobIdentity(unittest.TestCase):
    def test_new_job_without_terminal_state(self):
        evs = run_msgs([
            {"gcode_state": "RUNNING", "subtask_name": "A", "layer_num": 50, "mc_percent": 50, "job_id": "1"},
            {"gcode_state": "RUNNING", "subtask_name": "B", "layer_num": 1, "job_id": "2"}])
        self.assertEqual([e["type"] for e in evs], ["job_started", "job_lost", "job_started"])
        self.assertEqual((evs[1]["name"], evs[1]["layer"], evs[1]["percent"], evs[1]["job_id"]), ("A", 50, 50, "1"))
        self.assertEqual((evs[2]["name"], evs[2]["job_id"]), ("B", "2"))

    def test_running_then_idle_is_lost(self):
        evs = run_msgs([{"gcode_state": "RUNNING", "layer_num": 7, "job_id": "1"}, {"gcode_state": "IDLE"}])
        self.assertEqual([e["type"] for e in evs], ["job_started", "job_lost"])
        self.assertEqual((evs[1]["layer"], evs[1]["job_id"]), (7, "1"))

    def test_pause_and_same_id_progress_are_not_lost(self):
        evs = run_msgs([{"gcode_state": "RUNNING", "job_id": "1", "layer_num": 1},
                        {"gcode_state": "PAUSE"}, {"gcode_state": "RUNNING", "layer_num": 2}])
        self.assertEqual([e["type"] for e in evs], ["job_started", "progress"])

    def test_late_cancel_code_corrects_failure(self):
        evs = run_msgs([{"gcode_state": "RUNNING", "print_error": 0, "layer_num": 5, "job_id": "9"},
                        {"gcode_state": "FAILED"}, {"print_error": bambu.CANCEL_ERROR}, {"print_error": bambu.CANCEL_ERROR}])
        self.assertEqual([e["type"] for e in evs], ["job_started", "job_failed", "job_cancelled"])
        self.assertEqual(evs[1]["job_id"], "9")
        self.assertEqual((evs[2]["job_id"], evs[2]["corrects"]), ("9", "job_failed"))

    def test_late_end_event_carries_identity(self):
        evs = run_msgs([{"gcode_state": "FINISH", "job_id": "4"}])
        self.assertEqual((evs[0]["late"], evs[0]["job_id"]), (True, "4"))


class Spools(unittest.TestCase):
    def test_rfid_and_third_party(self):
        state, _ = replay(load("x1_full")[:1])
        self.assertEqual(bambu.spools(state), [
            {"slot": "ams0-0", "type": "PLA", "colour": "#FF0000", "filament_id": "GFA00", "remain": 80},
            {"slot": "ams0-1", "type": "PETG", "colour": "#00FF00", "filament_id": "GFG00", "remain": None},
        ])  # tray 2 (empty) and empty ext are skipped

    def test_second_ams_and_resent_tray(self):
        state, _ = replay(load("ams"))
        self.assertEqual(
            [(s["slot"], s["type"], s["remain"]) for s in bambu.spools(state)],
            [("ams0-0", "PLA", 75), ("ams0-1", "PETG", None), ("ams1-3", "ABS", 100)])

    def test_removed_spool_is_not_merged_with_old_one(self):
        # DevFilaSystem.cpp resets type/colour when a reported tray lacks them.
        state, _ = replay(load("x1_full")[:1])
        state, _ = bambu.step(state, push(ams={"ams": [{"id": "0", "tray": [{"id": "0"}]}]}))
        self.assertEqual([s["slot"] for s in bambu.spools(state)], ["ams0-1"])
        # tray_type without tray_info_idx is also "no filament" in the C++
        state, _ = bambu.step(state, push(ams={"ams": [{"id": "0", "tray": [{"id": "1", "tray_type": "PETG"}]}]}))
        self.assertEqual(bambu.spools(state), [])

    def test_vir_slot_main_and_deputy(self):
        state, _ = bambu.step({}, push(vir_slot=[
            {"id": "255", "tray_type": "PETG", "tray_color": "00FF00FF", "tray_info_idx": "GFG00"},
            {"id": "254", "tray_type": "PLA", "tray_color": "FF0000FF", "tray_info_idx": "GFA00"}]))
        self.assertEqual([(s["slot"], s["type"]) for s in bambu.spools(state)], [("ext", "PETG"), ("ext2", "PLA")])
        state, _ = bambu.step(state, push(vir_slot=[{"id": "255"}]))  # main removed, deputy untouched
        self.assertEqual([s["slot"] for s in bambu.spools(state)], ["ext2"])

    def test_vt_tray_is_main_whatever_its_id(self):
        state, _ = replay(load("ext_only"))  # fixture reports id "254"; C++ forces 255 (main)
        self.assertEqual([s["slot"] for s in bambu.spools(state)], ["ext"])

    def test_external_only(self):
        state, _ = replay(load("ext_only"))
        self.assertEqual(bambu.spools(state), [
            {"slot": "ext", "type": "PLA", "colour": "#FFFFFF", "filament_id": "GFA00", "remain": None}])


class Listen(unittest.TestCase):
    def test_client_constructs_without_connecting(self):
        try:
            import paho.mqtt.client  # noqa: F401
        except ImportError:
            self.skipTest("paho-mqtt not installed")
        c = bambu.make_client("SN", "code", lambda m: None)
        self.assertFalse(c.is_connected())

    def test_failing_callback_does_not_drop_batch_or_stop(self):
        seen = []

        def on_event(e):
            seen.append(e["type"])
            raise RuntimeError("boom")

        # drive listen()'s per-report handler without a network
        orig = bambu.run
        bambu.run = lambda h, s, c, on_report, pinned_cert_pem=None: [
            on_report(push(gcode_state="RUNNING", job_id="1")),
            on_report(push(gcode_state="RUNNING", job_id="2"))]
        try:
            with self.assertLogs("lynx_core.bambu", "ERROR"):
                bambu.listen("h", "SN", "code", on_event)
        finally:
            bambu.run = orig
        self.assertEqual(seen, ["job_started", "job_lost", "job_started"])


def make_cert(d, name):
    key, crt = os.path.join(d, name + ".key"), os.path.join(d, name + ".pem")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=" + name,
                    "-days", "1", "-keyout", key, "-out", crt], check=True, capture_output=True)
    return key, crt


@unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
class Pinning(unittest.TestCase):
    def test_pinned_context_accepts_only_the_pinned_cert(self):
        with tempfile.TemporaryDirectory() as d:
            ka, ca = make_cert(d, "a")
            _, cb = make_cert(d, "b")
            sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            sctx.load_cert_chain(ca, ka)
            srv = socket.socket()
            srv.bind(("127.0.0.1", 0))
            srv.listen(5)
            port = srv.getsockname()[1]

            def serve():
                for _ in range(3):
                    conn, _ = srv.accept()
                    try:
                        with sctx.wrap_socket(conn, server_side=True) as t:
                            t.recv(1)
                    except (ssl.SSLError, OSError):
                        conn.close()

            th = threading.Thread(target=serve, daemon=True)
            th.start()

            def connect(pem):
                with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                    with bambu.pinned_context(pem).wrap_socket(raw, server_hostname="127.0.0.1") as t:
                        t.send(b"x")

            pem_a, pem_b = pathlib.Path(ca).read_text(), pathlib.Path(cb).read_text()
            self.assertEqual(bambu.fetch_cert("127.0.0.1", port).strip(), pem_a.strip())
            connect(pem_a)
            with self.assertRaises(ssl.SSLError):
                connect(pem_b)
            th.join(5)
            srv.close()


if __name__ == "__main__":
    unittest.main()
