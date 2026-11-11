"""Run the Spools page in a normal browser, without OrcaSlicer.

    cd lynx/core && uv run python ../plugin/dev_server.py [--port 8765] [--db /path/spools.sqlite3]

Binds to 127.0.0.1 only; add ?theme=dark or ?theme=light to the URL to emulate the OrcaSlicer theme. Without --db it uses a temporary database that is deleted on exit.
"""
import argparse
import json
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
from lynx_core import inventory, spools_page, ui_api  # noqa: E402

# Replies to orca.postMessage arrive through the handlers given to orca.onMessage, like in OrcaSlicer.
SHIM = """<script>
window.orca = (function () {
  var handlers = [];
  return {
    onMessage: function (cb) { handlers.push(cb); },
    deliver: function (m) { handlers.forEach(function (h) { h(m); }); },
    postMessage: function (data) {
      fetch("/api", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) })
        .then(function (r) { return r.json(); })
        .then(function (reply) { handlers.forEach(function (h) { h(reply); }); });
    }
  };
})();
// ?activity=1 injects sample tracker events (spool ids 1 and 2 are looked up if they exist).
if (new URLSearchParams(location.search).get("activity")) fetch("/push?activity=1").then(function (r) { return r.json(); })
  .then(function (m) { window.addEventListener("load", function () { orca.deliver(m); }); });
// ?push=<printer id> asks /push for one plan_check push, like the plug-in sends after a slice.
var pushId = new URLSearchParams(location.search).get("push");
if (pushId) fetch("/push?printer=" + encodeURIComponent(pushId)).then(function (r) { return r.json(); })
  .then(function (m) { window.addEventListener("load", function () { orca.deliver(m); }); });
</script>"""


# What the OrcaSlicer host injects into every page (variables, data-orca-theme, color-scheme); see ?theme=dark|light.
THEMES = {
    "light": ("#ffffff", "#1f2429", "#6b7580", "#d9dee3", "#009688"),
    "dark": ("#2b2d30", "#e4e6e8", "#9aa0a6", "#3d4043", "#009688"),
}
MAX_BODY = 1 << 20


def theme_script(name):
    bg, fg, muted, border, accent = THEMES[name]
    css = (f":root{{--orca-bg:{bg};--orca-fg:{fg};--orca-muted:{muted};--orca-border:{border};"
           f"--orca-accent:{accent};--orca-accent-fg:#ffffff;color-scheme:{name};}}")
    return (f'<style id="orca-host-theme-vars">{css}</style>'
            f'<script>document.documentElement.setAttribute("data-orca-theme","{name}");</script>')


def make_server(db_path, port=0):
    class Handler(BaseHTTPRequestHandler):
        db = inventory.connect(db_path)  # single-threaded HTTPServer: one connection, one thread

        def _send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            # Blocks DNS rebinding: a page on another origin reaches us under its own Host name.
            port = self.server.server_port
            if self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}"):
                return True
            self._send(403, "text/plain", b"forbidden host")

        def do_GET(self):
            if not self._host_ok():
                return
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            if url.path == "/push" and "activity" in query:
                sample = [
                    {"event": "job_finished", "printer": "Sample", "printer_id": 1, "job": "benchy", "manual": False,
                     "deducted": [{"spool_id": 1, "grams": 12.3, "source": "slicer"}], "unassigned": [], "note": ""},
                    {"event": "job_cancelled", "printer": "Sample", "printer_id": 1, "job": "bracket", "manual": False,
                     "deducted": [{"spool_id": 1, "grams": 4.2, "source": "estimate"}], "unassigned": [],
                     "note": "Estimated from layer 31, about one layer either way."},
                    {"event": "job_finished", "printer": "Sample", "printer_id": 1, "job": "started elsewhere", "manual": True,
                     "deducted": [], "unassigned": ["ext"], "note": "Usage unknown, enter it manually."}]
                return self._send(200, "application/json", json.dumps(ui_api.activity_push(sample)).encode())
            if url.path == "/push":
                sample = {"slots": {"ext": {"total_g": 12.3}}}
                try:
                    reply = ui_api.handle(self.db, {"op": "check_plan", "args": {"printer_id": int(query["printer"][0]), "plan": sample}})
                except (KeyError, ValueError):
                    return self._send(400, "text/plain", b"printer=<id> required")
                return self._send(200, "application/json", json.dumps(ui_api.plan_push(reply.get("result"))).encode())
            if url.path != "/":
                return self._send(404, "text/plain", b"not found")
            theme = query.get("theme", [""])[0]
            html = spools_page.PAGE.replace("<head>", "<head>" + (theme_script(theme) if theme in THEMES else ""), 1)
            html = html.replace("<body>", "<body>" + SHIM, 1)
            self._send(200, "text/html; charset=utf-8", html.encode())

        def do_POST(self):
            if not self._host_ok():
                return
            if self.path != "/api":
                return self._send(404, "text/plain", b"not found")
            # A cross-site form or no-cors fetch can only send simple content types, so requiring JSON blocks it.
            if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
                return self._send(415, "text/plain", b"Content-Type must be application/json")
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY:
                return self._send(413, "text/plain", b"body too large")
            try:
                message = json.loads(self.rfile.read(length))
            except ValueError:
                message = None
            self._send(200, "application/json", json.dumps(ui_api.handle(self.db, message)).encode())

        def log_message(self, *args):
            pass

    return HTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--db")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        server = make_server(a.db or os.path.join(tmp, "spools.sqlite3"), a.port)
        print(f"Spools dev page: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
