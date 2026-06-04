"""Script de pornire pentru Render.com — rulează backend + proxy într-un singur proces."""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "5000"))
BACKEND_PORT = 8000


def main():
    # Pornește backend-ul FastAPI
    backend = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", str(BACKEND_PORT),
        ],
        cwd=str(ROOT / "backend"),
    )

    # Așteaptă să pornească backend-ul
    time.sleep(4)

    if backend.poll() is not None:
        print("Backend-ul nu a pornit. Opresc.", file=sys.stderr)
        sys.exit(1)

    # Pornește proxy-ul pe portul dat de Render
    proxy = subprocess.Popen(
        [sys.executable, "proxy_server.py", "--port", str(PORT)],
        cwd=str(ROOT),
        env={**os.environ, "BACKEND_PORT": str(BACKEND_PORT)},
    )

    print(f"App disponibilă pe portul {PORT}")

    try:
        proxy.wait()
    finally:
        backend.terminate()
        backend.wait()


if __name__ == "__main__":
    main()
