"""Minimal Stooq-shaped CSV HTTP server for offline / CI verification."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
MOCK = ROOT / "data" / "mock_stooq"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/q/d/l"):
            self.send_error(404)
            return
        qs = parse_qs(parsed.query)
        symbol = (qs.get("s") or [""])[0].lower()
        path = MOCK / f"{symbol}.csv"
        if not path.exists():
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print("[mock-stooq]", fmt % args)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    httpd = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"mock Stooq listening on http://127.0.0.1:{args.port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
