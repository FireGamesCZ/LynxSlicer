"""Run the Spools page in a normal browser, without OrcaSlicer.

    cd lynx/core && uv run python ../plugin/dev_server.py [--port 8765] [--db /path/spools.sqlite3]

Binds to 127.0.0.1 only. Without --db it uses a temporary database that is deleted on exit.
"""
import argparse
import json
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
from lynx_core import inventory, spools_page, ui_api  # noqa: E402

# Replies to orca.postMessage arrive through the handlers given to orca.onMessage, like in OrcaSlicer.
SHIM = """<script>
window.orca = (function () {
  var handlers = [];
  return {
    onMessage: function (cb) { handlers.push(cb); },
    postMessage: function (data) {
      fetch("/api", { method: "POST", body: JSON.stringify(data) })
        .then(function (r) { return r.json(); })
        .then(function (reply) { handlers.forEach(function (h) { h(reply); }); });
    }
  };
})();
</script>"""


def make_server(db_path, port=0):
    class Handler(BaseHTTPRequestHandler):
        db = inventory.connect(db_path)  # single-threaded HTTPServer: one connection, one thread

        def _send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/":
                return self._send(404, "text/plain", b"not found")
            html = spools_page.PAGE.replace("<body>", "<body>" + SHIM, 1)
            self._send(200, "text/html; charset=utf-8", html.encode())

        def do_POST(self):
            if self.path != "/api":
                return self._send(404, "text/plain", b"not found")
            try:
                message = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
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
