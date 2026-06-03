from __future__ import annotations

import argparse
import http.client
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlsplit
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "frontend" / "dist"
BACKEND_HOST = os.environ.get("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))


class ProxyHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST_DIR), **kwargs)

    def _proxy_backend(self):
        parsed = urlsplit(self.path)
        upstream_path = parsed.path[len("/api") :] or "/"
        if parsed.query:
            upstream_path += f"?{parsed.query}"

        content_length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(content_length) if content_length else None

        connection = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=60)
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "accept-encoding", "connection"}
        }
        try:
            connection.request(self.command, upstream_path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read()

            self.send_response(response.status, response.reason)
            for header, value in response.getheaders():
                header_lower = header.lower()
                if header_lower in {"transfer-encoding", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade"}:
                    continue
                self.send_header(header, value)
            self.end_headers()
            self.wfile.write(response_body)
        finally:
            connection.close()

    def do_GET(self):
        if self.path.startswith("/api/") or self.path == "/api":
            return self._proxy_backend()
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/") or self.path == "/api":
            return self._proxy_backend()
        return super().do_POST()

    def do_PUT(self):
        if self.path.startswith("/api/") or self.path == "/api":
            return self._proxy_backend()
        return super().do_PUT()

    def do_PATCH(self):
        if self.path.startswith("/api/") or self.path == "/api":
            return self._proxy_backend()
        return super().do_PATCH()

    def do_DELETE(self):
        if self.path.startswith("/api/") or self.path == "/api":
            return self._proxy_backend()
        return super().do_DELETE()

    def do_OPTIONS(self):
        if self.path.startswith("/api/") or self.path == "/api":
            return self._proxy_backend()
        return super().do_OPTIONS()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_head(self):
        # SPA fallback: serve index.html for app routes.
        if not self.path.startswith("/api/") and not self.path.startswith("/api"):
            requested = (DIST_DIR / self.path.lstrip("/")).resolve()
            if requested.is_file():
                return super().send_head()
            index_file = DIST_DIR / "index.html"
            if index_file.exists():
                self.path = "/index.html"
                return super().send_head()
        return super().send_head()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve frontend dist and proxy /api to backend")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    if not DIST_DIR.exists():
        raise SystemExit(f"Frontend build not found: {DIST_DIR}. Run `npm run build` in frontend first.")

    server = ThreadingHTTPServer((args.host, args.port), ProxyHandler)
    print(f"Serving frontend from {DIST_DIR}")
    print(f"Proxying /api -> http://{BACKEND_HOST}:{BACKEND_PORT}")
    print(f"Listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
