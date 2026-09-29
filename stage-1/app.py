"""Tablekeeper — HTTP service, stage 1.

Standard library only, so the image needs no runtime network access.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

JSON_CONTENT_TYPE = "application/json; charset=utf-8"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "tablekeeper"
    sys_version = ""

    def log_message(self, fmt, *args):  # keep the container's stdout quiet
        pass

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        return self.rfile.read(length) if length > 0 else b""

    def _respond(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", JSON_CONTENT_TYPE)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, code, message):
        self._respond(status, {"error": {"code": code, "message": message}})

    def _dispatch(self, method):
        self._read_body()
        path = self.path.split("?", 1)[0]
        if method == "GET" and path == "/health":
            self._respond(200, {"status": "ok"})
            return
        self._error(404, "not_found", "no such resource")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")


def main():
    port = int(os.environ.get("PORT") or "8080")
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
