#!/usr/bin/env python3
"""
Porneste intreaga platforma cu o singura comanda.

  python run.py

Ce face:
  1. Verifica si porneste PostgreSQL prin docker compose (daca nu ruleaza)
  2. Asteapta ca DB-ul sa fie healthy
  3. Verifica schema PostgreSQL (incarca daca lipseste)
  4. Importa datele oficiale CFR (daca trenurile lipsesc)
  5. Creeaza venv-ul Python si instaleaza dependintele runtime
  6. Porneste backend FastAPI pe :8000
  7. Porneste un server web cu proxy /api pe portul ales (RUN_WEB_PORT, implicit 8765)
  8. Deschide browserul automat

Variabile de mediu utile:
  RUN_WEB_PORT          portul pe care se serveste UI-ul (implicit 8765)
  RUN_SKIP_IMPORT_CFR   '1' = skipping import oficial CFR (util in CI sau cand ai deja datele)
  RUN_SKIP_BROWSER      '1' = nu deschide browserul automat
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IS_WIN = sys.platform == "win32"


# ============================================================================
# venv helpers
# ============================================================================
def venv_dir() -> Path:
    # Pe Windows folosim .venv_win (cel pe care l-am creat pentru sesiune),
    # in rest .venv standard.
    win_venv = ROOT / ".venv_win"
    if IS_WIN and win_venv.exists():
        return win_venv
    return ROOT / ".venv"


def venv_python() -> Path:
    return venv_dir() / ("Scripts" if IS_WIN else "bin") / ("python.exe" if IS_WIN else "python")


def venv_pip() -> Path:
    return venv_dir() / ("Scripts" if IS_WIN else "bin") / ("pip.exe" if IS_WIN else "pip")


def ensure_venv() -> None:
    vpy = venv_python()
    if vpy.exists():
        return
    print("[venv] Creez mediul virtual ...", flush=True)
    subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir())], cwd=ROOT)
    if not venv_python().exists():
        raise SystemExit("Nu s-a putut crea mediul virtual. Verifica instalarea Python.")


def install_runtime_deps() -> None:
    req = ROOT / "requirements-run.txt"
    if not req.is_file():
        raise SystemExit(f"Lipseste {req.name} in radacina proiectului.")
    print("[venv] Verific dependintele Python ...", flush=True)
    # Verificam doar daca psycopg + fastapi sunt deja instalate; daca da, skip
    check = subprocess.run(
        [str(venv_python()), "-c", "import psycopg, fastapi, sqlalchemy, easyocr"],
        capture_output=True,
    )
    if check.returncode == 0:
        print("[venv] OK — dependintele sunt deja instalate.", flush=True)
        return
    print("[venv] Instalez dependintele (prima rulare poate dura 2-3 minute) ...", flush=True)
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


# ============================================================================
# Docker + Postgres
# ============================================================================
def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5, text=True
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def postgres_running() -> bool:
    """True daca containerul railway_db ruleaza si raspunde."""
    try:
        r = subprocess.run(
            ["docker", "exec", "railway_db", "pg_isready", "-U", "railway", "-d", "railway_db"],
            capture_output=True, timeout=5, text=True,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def ensure_postgres() -> None:
    """Porneste Postgres prin docker compose daca nu ruleaza."""
    if not docker_available():
        raise SystemExit(
            "Docker Desktop nu este pornit sau Docker nu este instalat.\n"
            "Porneste Docker Desktop si reia 'python run.py'."
        )

    if postgres_running():
        print("[postgres] OK — containerul railway_db ruleaza deja.", flush=True)
        return

    print("[postgres] Pornesc PostgreSQL prin docker compose ...", flush=True)
    subprocess.check_call(
        ["docker", "compose", "up", "-d", "postgres"],
        cwd=ROOT,
    )

    # Asteapta pana e healthy (max 30s)
    print("[postgres] Astept ca DB-ul sa fie ready ...", flush=True)
    deadline = time.time() + 30
    while time.time() < deadline:
        if postgres_running():
            print("[postgres] OK — DB ready.", flush=True)
            return
        time.sleep(1)
    raise SystemExit("PostgreSQL nu a devenit ready in 30 secunde. Verifica `docker compose logs postgres`.")


def db_query(sql: str) -> str:
    """Ruleaza un query simplu si returneaza output-ul ca text."""
    r = subprocess.run(
        ["docker", "exec", "railway_db", "psql", "-U", "railway", "-d", "railway_db",
         "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=10,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def ensure_schema_loaded() -> None:
    """Daca tabela 'users' nu exista, reincarca schema + seed."""
    has_users = db_query("SELECT to_regclass('public.users')")
    if has_users and has_users != "":
        return
    print("[postgres] Schema lipseste — incarc schema.sql + seed_demo.sql ...", flush=True)
    for fname in ["schema.sql", "seed_demo.sql"]:
        path = ROOT / "database" / fname
        if not path.is_file():
            continue
        with open(path, "rb") as f:
            r = subprocess.run(
                ["docker", "exec", "-i", "railway_db", "psql", "-U", "railway", "-d", "railway_db"],
                stdin=f, capture_output=True, text=True,
            )
            if r.returncode != 0:
                print(f"[postgres] WARN la incarcare {fname}: {r.stderr[:200]}", flush=True)
    print("[postgres] Schema incarcata.", flush=True)


def ensure_cfr_imported() -> None:
    """Daca lipsesc trenurile, ruleaza importul oficial CFR."""
    if os.environ.get("RUN_SKIP_IMPORT_CFR") == "1":
        print("[cfr] Skipping import (RUN_SKIP_IMPORT_CFR=1).", flush=True)
        return

    nr = db_query("SELECT COUNT(*) FROM trains")
    try:
        count = int(nr) if nr else 0
    except ValueError:
        count = 0

    if count >= 100:
        print(f"[cfr] OK — {count} trenuri deja in BD.", flush=True)
        return

    importer = ROOT / "database" / "import_cfr.py"
    if not importer.is_file():
        print("[cfr] WARN: lipseste database/import_cfr.py — sar peste import.", flush=True)
        return

    ext_dir = ROOT / "database" / "external"
    if not ext_dir.is_dir() or not any(ext_dir.glob("*.xml")):
        print("[cfr] WARN: lipsesc XML-urile din database/external/ — sar peste import.", flush=True)
        return

    print(f"[cfr] Importez catalogul oficial CFR (poate dura 2-3 minute) ...", flush=True)
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://railway:railway_dev@localhost:5432/railway_db"
    r = subprocess.run(
        [str(venv_python()), str(importer)],
        cwd=ROOT, env=env,
    )
    if r.returncode != 0:
        print("[cfr] WARN: importul a esuat — aplicatia porneste fara catalog real.", flush=True)
    else:
        print("[cfr] Import complet.", flush=True)


# ============================================================================
# Frontend
# ============================================================================
def require_frontend_dist() -> None:
    index = ROOT / "frontend" / "dist" / "index.html"
    if not index.is_file():
        raise SystemExit(
            "Lipseste frontend/dist (build-ul React).\n"
            "Ruleaza o data: cd frontend && npm install && npm run build"
        )


# ============================================================================
# Main
# ============================================================================
def main() -> None:
    os.chdir(ROOT)

    print()
    print("=" * 60)
    print("  Railway Digital Identity Platform — pornire automata")
    print("=" * 60)
    print()

    # 1. Verificari preliminare
    ensure_venv()
    install_runtime_deps()
    require_frontend_dist()

    # 2. Postgres
    ensure_postgres()
    ensure_schema_loaded()
    ensure_cfr_imported()

    # 3. Environment pentru procese copil
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env["DATABASE_URL"] = env.get(
        "DATABASE_URL",
        "postgresql+psycopg://railway:railway_dev@localhost:5432/railway_db",
    )
    # SECRET_KEY este required de config.py — punem unul de development daca lipseste
    env.setdefault(
        "SECRET_KEY",
        "dev-only-secret-key-for-local-run-py-min-32-characters-long",
    )

    web_port = env.get("RUN_WEB_PORT", "8765")

    # HTTPS opțional: activeaza cu RUN_SSL=1 (necesita acceptarea certului in browser)
    use_ssl = env.get("RUN_SSL", "0") == "1"

    # 4. Pornesc backend
    print("[backend] Pornesc API FastAPI pe :8000 ...", flush=True)
    backend = subprocess.Popen(
        # --reload: uvicorn detecteaza modificari ale fisierelor .py si reincarca
        # codul automat. Util in dezvoltare ca sa nu trebuiasca sa restartezi
        # manual procesul dupa fiecare edit. In productie ar fi mai bine fara.
        [str(venv_python()), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
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

    # Asteptam pana backend-ul accepta cereri (max 15s)
    print("[backend] Astept backend-ul sa fie ready ...", flush=True)
    import urllib.error
    import urllib.request
    deadline = time.time() + 15
    backend_ok = False
    while time.time() < deadline:
        if backend.poll() is not None:
            stop_all()
            raise SystemExit("Backend-ul s-a oprit. Verifica mesajele de mai sus.")
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
            backend_ok = True
            break
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)

    if not backend_ok:
        stop_all()
        raise SystemExit("Backend-ul nu raspunde pe /health.")
    print("[backend] OK — API ready.", flush=True)

    # 5. Pornesc proxy + frontend static
    scheme = "https" if use_ssl else "http"
    ssl_label = " (HTTPS)" if use_ssl else ""
    print(f"[web] Pornesc serverul web{ssl_label} (UI + proxy /api) pe :{web_port} ...", flush=True)
    proxy_cmd = [
        str(venv_python()),
        str(ROOT / "proxy_server.py"),
        "--host", "0.0.0.0",
        "--port", web_port,
    ]
    if use_ssl:
        proxy_cmd.append("--ssl")
    proxy = subprocess.Popen(proxy_cmd, cwd=ROOT, env=env)
    children.append(proxy)

    time.sleep(1.5)
    if proxy.poll() is not None:
        stop_all()
        raise SystemExit("Serverul web nu a pornit.")

    url = f"{scheme}://127.0.0.1:{web_port}"
    # Detectam IP-ul local pentru afisarea URL-ului de acces de pe telefon
    try:
        import socket as _socket
        local_ip = next(
            (info[4][0] for info in _socket.getaddrinfo(_socket.gethostname(), None, _socket.AF_INET)
             if not info[4][0].startswith("127.")),
            None,
        )
    except Exception:
        local_ip = None

    print()
    print("=" * 60)
    print(f"  Aplicatia ruleaza la: {url}")
    if local_ip:
        print(f"  Acces telefon (retea locala): {scheme}://{local_ip}:{web_port}")
        if use_ssl:
            print(f"  (prima deschidere: accepta avertismentul de certificat in browser)")
    print()
    print("  Conturi demo (parola: demo2026):")
    print("    user.demo@railwaydemo.com       (pasager student)")
    print("    agent.train@railwaydemo.com     (conductor tren)")
    print("    agent.upb@railwaydemo.com       (agent universitar UPB)")
    print("    agent.ase@railwaydemo.com       (agent universitar ASE)")
    print()
    print("  Apasa Ctrl+C pentru a opri toate serviciile.")
    print("=" * 60)
    print()

    # 6. Deschid browserul
    if os.environ.get("RUN_SKIP_BROWSER") != "1":
        try:
            webbrowser.open(url)
        except Exception:
            pass

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
