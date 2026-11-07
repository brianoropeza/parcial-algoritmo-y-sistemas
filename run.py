#!/usr/bin/env python3
"""Disruption Companion — run everything with ONE command.

    Windows:        py run.py
    Linux / macOS:  python3 run.py

What it does:
  1. Creates a local virtual environment in .venv (only the first time).
  2. Installs backend and frontend dependencies.
  3. Starts the backend (FastAPI, http://localhost:8000/docs).
  4. Starts the frontend (Streamlit, http://localhost:8501) and opens the browser.
  Ctrl+C stops both.

Options:
  --test        install dependencies, run backend and frontend tests, and exit.
  --no-install  skip the dependency installation step.
  --no-browser  do not open the browser automatically.
"""
import os
import signal
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:8501"


def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def ensure_environment(install: bool) -> None:
    if sys.version_info < (3, 12):
        sys.exit(f"Python 3.12 or later is required (found {sys.version.split()[0]}).")
    if not PY.exists():
        step(f"Creating virtual environment in {VENV.name}")
        venv.create(VENV, with_pip=True)
    if install:
        step("Installing dependencies (the first time may take a few minutes)")
        subprocess.check_call([str(PY), "-m", "pip", "install", "-q", "--disable-pip-version-check",
                               "-r", str(BACKEND / "requirements.txt"), "-r", str(FRONTEND / "requirements.txt")])


def run_tests() -> int:
    codes = []
    for name, folder in (("backend", BACKEND), ("frontend", FRONTEND)):
        step(f"Running {name} tests")
        codes.append(subprocess.call([str(PY), "-m", "pytest", "-q", "-p", "no:warnings"], cwd=folder))
    ok = all(c == 0 for c in codes)
    step("All tests passed" if ok else "Some tests failed")
    return 0 if ok else 1


def wait_for(url: str, seconds: int = 40) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except OSError:
            time.sleep(0.5)
    return False


def start_services(open_browser: bool) -> int:
    if wait_for(f"{BACKEND_URL}/api/health", 1):
        sys.exit("Port 8000 is already in use (is the backend already running?). Stop it and try again.")

    step("Starting backend")
    backend = subprocess.Popen([str(PY), "-m", "uvicorn", "app.main:app", "--port", "8000"], cwd=BACKEND)
    procs = [backend]
    try:
        if not wait_for(f"{BACKEND_URL}/api/health"):
            print("The backend did not start. See the messages above.")
            return 1
        step("Starting frontend")
        frontend = subprocess.Popen(
            [str(PY), "-m", "streamlit", "run", "app.py", "--server.port", "8501",
             "--server.headless", "true", "--browser.gatherUsageStats", "false"],
            cwd=FRONTEND, env={**os.environ, "BACKEND_URL": BACKEND_URL})
        procs.append(frontend)
        if wait_for(FRONTEND_URL) and open_browser:
            webbrowser.open(FRONTEND_URL)
        print(f"\n  Frontend: {FRONTEND_URL}   (enter booking code ABC123)"
              f"\n  Backend:  {BACKEND_URL}/docs"
              f"\n  Press Ctrl+C to stop both.\n", flush=True)
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        print("A service stopped unexpectedly. See the messages above.")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        step("Stopping services")
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


def _interrupt(*_):
    raise KeyboardInterrupt


def main() -> int:
    # Ctrl+C (and a termination request) always stop both services cleanly.
    signal.signal(signal.SIGINT, _interrupt)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _interrupt)
    args = set(sys.argv[1:])
    ensure_environment(install="--no-install" not in args)
    if "--test" in args:
        return run_tests()
    return start_services(open_browser="--no-browser" not in args)


if __name__ == "__main__":
    sys.exit(main())
