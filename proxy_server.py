from __future__ import annotations

import argparse
import http.client
import os
import socket
import ssl
from pathlib import Path
from urllib.parse import urlsplit
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "frontend" / "dist"
BACKEND_HOST = os.environ.get("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))


def _local_ips() -> list[str]:
    """Returnează toate IPv4 locale (non-loopback)."""
    seen: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                seen.add(ip)
    except Exception:
        pass
    return list(seen) or []


def _ensure_ssl_cert(ssl_dir: Path) -> tuple[Path, Path]:
    """Generează un certificat self-signed cu SAN pentru IP-urile locale."""
    cert_file = ssl_dir / "cert.pem"
    key_file = ssl_dir / "key.pem"

    if cert_file.exists() and key_file.exists():
        return cert_file, key_file

    ssl_dir.mkdir(exist_ok=True)

    try:
        import datetime
        import ipaddress

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        raise SystemExit(
            "Pachetul 'cryptography' lipseste. Instaleaza-l: pip install cryptography"
        )

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    local_ips = _local_ips()
    san: list[x509.GeneralName] = [x509.DNSName("localhost")]
    for ip_str in ["127.0.0.1"] + local_ips:
        try:
            san.append(x509.IPAddress(ipaddress.IPv4Address(ip_str)))
        except Exception:
            pass

    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Railway Local Dev")]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    )

    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )

    print(f"[SSL] Certificat generat: {cert_file}")
    print(f"[SSL] SAN: localhost, 127.0.0.1" + (f", {', '.join(local_ips)}" if local_ips else ""))
    return cert_file, key_file


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

        ocr_endpoint = "/documents/extract-id" in upstream_path
        connection = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=300 if ocr_endpoint else 60)
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
        except (ConnectionResetError, ConnectionRefusedError, OSError) as e:
            try:
                self.send_error(502, f"Backend unavailable: {e}")
            except Exception:
                pass
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
    parser.add_argument("--ssl", action="store_true", help="Porneste cu HTTPS (cert self-signed)")
    parser.add_argument("--ssl-dir", default=str(ROOT / "ssl"), help="Director pentru cert/key")
    args = parser.parse_args()

    if not DIST_DIR.exists():
        raise SystemExit(f"Frontend build not found: {DIST_DIR}. Run `npm run build` in frontend first.")

    server = ThreadingHTTPServer((args.host, args.port), ProxyHandler)
    scheme = "http"

    if args.ssl:
        cert_file, key_file = _ensure_ssl_cert(Path(args.ssl_dir))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert_file), str(key_file))
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        scheme = "https"

    print(f"Serving frontend from {DIST_DIR}")
    print(f"Proxying /api -> http://{BACKEND_HOST}:{BACKEND_PORT}")
    print(f"Listening on {scheme}://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
