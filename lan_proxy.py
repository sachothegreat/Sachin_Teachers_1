#!/usr/bin/python3
"""Firewall-friendly proxy: listens on 8080, forwards to Flask on 5001."""
import http.server
import socketserver
import urllib.error
import urllib.request

LISTEN_PORT = 8080
BACKEND = "http://127.0.0.1:5001"


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[proxy] {self.address_string()} {fmt % args}")

    def _forward(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None
        url = BACKEND + self.path
        req = urllib.request.Request(url, data=body, method=self.command)
        for key, value in self.headers.items():
            if key.lower() != "host":
                req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    if key.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(key, value)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as exc:
            self.send_response(exc.code)
            self.end_headers()
            self.wfile.write(exc.read())
        except Exception as exc:
            self.send_error(502, str(exc))

    def do_GET(self):
        self._forward()

    def do_POST(self):
        self._forward()

    def do_PUT(self):
        self._forward()

    def do_DELETE(self):
        self._forward()

    def do_OPTIONS(self):
        self._forward()


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("0.0.0.0", LISTEN_PORT), ProxyHandler) as httpd:
        print(f"Proxy listening on 0.0.0.0:{LISTEN_PORT} -> {BACKEND}")
        httpd.serve_forever()
