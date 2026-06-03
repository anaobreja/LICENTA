#!/usr/bin/env python3
"""
Porneste backend + frontend (build static) intr-o singura comanda.

Utilizare (din radacina proiectului):
  python run.py

Optional: seteaza RUN_WEB_PORT (implicit 8765).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IS_WIN = sys.platform == "win32"


def venv_dir() -> Path:
    return ROOT / ".venv"


def venv_python() -> Path:
    return venv_dir() / ("Scripts" if IS_WIN else "bin") / ("python.exe" if IS_WIN else "python")


def venv_pip() -> Path:
    return venv_dir() / ("Scripts" if IS_WIN else "bin") / ("pip.exe" if IS_WIN else "pip")


def ensure_venv() -> None:
    vpy = venv_python()
    if vpy.exists():
        return
    print("Creez mediul virtual .venv ...", flush=True)
    subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir())], cwd=ROOT)
    if not venv_python().exists():
        raise SystemExit("Nu s-a putut crea mediul virtual (.venv). Verifica instalarea Python.")


def install_runtime_deps() -> None:
    req = ROOT / "requirements-run.txt"
    if not req.is_file():
        raise SystemExit(f"Lipseste {req.name} in radacina proiectului.")
    print("Instalez dependinte Python (prima rulare poate dura 1-2 minute) ...", flush=True)
    subprocess.check_call(
        [
            str(venv_pip()),
            "install",
            "--disable-pip-version-check",
            "-r",
            str(req),
        ],
        cwd=ROOT,
    )


def require_frontend_dist() -> None:
    index = ROOT / "frontend" / "dist" / "index.html"
    if not index.is_file():
        raise SystemExit(
            "Lipseste frontend/dist (build-ul React). In depozit trebuie sa existe folderul dist. "
            "Daca l-ai sters, ruleaza o data: cd frontend && npm install && npm run build"
        )


def main() -> None:
    os.chdir(ROOT)
    ensure_venv()
    install_runtime_deps()
    require_frontend_dist()

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    db_file = ROOT / "railway_demo.db"
    env.setdefault("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")

    web_port = env.get("RUN_WEB_PORT", "8765")

    print("Pornesc API (uvicorn) pe port 8000 ...", flush=True)
    backend = subprocess.Popen(
        [str(venv_python()), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT / "backend",
        env=env,
    )
    children: list[subprocess.Popen] = [backend]

    def stop_all() -> None:
        for p in reversed(children):
            if p.poll() is None:
                p.terminate()
        deadline = time.time() + 8
        for p in reversed(children):
            while p.poll() is None and time.time() < deadline:
                time.sleep(0.1)
        for p in reversed(children):
            if p.poll() is None:
                try:
                    p.kill()
                except OSError:
                    pass

    def handle_signal(_sig, _frame):
        stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    time.sleep(1.8)
    if backend.poll() is not None:
        stop_all()
        raise SystemExit("Backend-ul nu a pornit. Verifica mesajele de mai sus.")

    print(f"Pornesc serverul web + proxy API pe port {web_port} ...", flush=True)
    proxy = subprocess.Popen(
        [
            str(venv_python()),
            str(ROOT / "proxy_server.py"),
            "--host",
            "0.0.0.0",
            "--port",
            web_port,
        ],
        cwd=ROOT,
        env=env,
    )
    children.append(proxy)

    print(
        f"\n  Deschide: http://127.0.0.1:{web_port}\n",
        flush=True,
    )

    try:
        code = proxy.wait()
        sys.exit(code if code is not None else 0)
    finally:
        stop_all()


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"Comanda a esuat (cod {e.returncode}).") from e
