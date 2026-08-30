"""
run_agents_office.py
--------------------
Launcher for the AgentsOffice pixel-art RPG multi-agent workspace.

Usage:
    python run_agents_office.py          # backend only (port 8001)
    python run_agents_office.py --dev    # backend + frontend dev server

Access:
    Office UI  : http://localhost:8001/static/office/   (production build)
    Frontend   : http://localhost:5174/static/office/   (dev mode with HMR)
    API Docs   : http://localhost:8001/docs
    Health     : http://localhost:8001/api/v1/health
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
AGENTS_OFFICE_DIR = ROOT / "agents_office"
FRONTEND_DIR = AGENTS_OFFICE_DIR / "frontend"


def check_prerequisites():
    """Verify that required tools are available."""
    errors = []

    # Check Python packages
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        errors.append(
            "uvicorn not found. Run: pip install -r agents_office/requirements.txt"
        )

    try:
        import fastapi  # noqa: F401
    except ImportError:
        errors.append(
            "fastapi not found. Run: pip install -r agents_office/requirements.txt"
        )

    if errors:
        print("[!] Prerequisites not met:")
        for e in errors:
            print(f"   * {e}")
        sys.exit(1)


def install_python_deps():
    """Install AgentsOffice Python requirements."""
    req_file = AGENTS_OFFICE_DIR / "requirements.txt"
    print(f"[*] Installing Python dependencies from {req_file.name}...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(req_file), "--prefer-binary"],
        cwd=str(AGENTS_OFFICE_DIR),
    )
    print("[+] Python dependencies installed.\n")


def start_backend():
    """Start the AgentsOffice FastAPI backend on port 8001."""
    print("[-] Starting AgentsOffice backend on http://localhost:8001")
    print("    Office UI -> http://localhost:8001/static/office/")
    print("    API Docs  -> http://localhost:8001/docs\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(AGENTS_OFFICE_DIR)

    # Load .env from agents_office directory
    env_file = AGENTS_OFFICE_DIR / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env.setdefault(key.strip(), value.strip())

    try:
        subprocess.run(
            [
                sys.executable, "-m", "uvicorn",
                "app.main:app",
                "--reload",
                "--host", "0.0.0.0",
                "--port", "8001",
            ],
            cwd=str(AGENTS_OFFICE_DIR),
            env=env,
        )
    except KeyboardInterrupt:
        print("\n[!] AgentsOffice backend stopped.")


def start_dev_mode():
    """Start both backend and frontend dev server concurrently."""
    import threading

    print("[*] Starting AgentsOffice in full dev mode...\n")
    print("    Backend  -> http://localhost:8001/docs")
    print("    Office   -> http://localhost:5174/static/office/\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(AGENTS_OFFICE_DIR)

    # Load .env
    env_file = AGENTS_OFFICE_DIR / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env.setdefault(key.strip(), value.strip())

    # Frontend: npm run dev
    frontend_proc = None
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        print("[*] Installing frontend Node.js dependencies...")
        subprocess.check_call(["npm", "install"], cwd=str(FRONTEND_DIR), shell=True)
        print("[+] Frontend dependencies installed.\n")

    def run_frontend():
        nonlocal frontend_proc
        frontend_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(FRONTEND_DIR),
            shell=True,
            env=env,
        )
        frontend_proc.wait()

    frontend_thread = threading.Thread(target=run_frontend, daemon=True)
    frontend_thread.start()

    # Backend: uvicorn --reload
    try:
        subprocess.run(
            [
                sys.executable, "-m", "uvicorn",
                "app.main:app",
                "--reload",
                "--host", "0.0.0.0",
                "--port", "8001",
            ],
            cwd=str(AGENTS_OFFICE_DIR),
            env=env,
        )
    except KeyboardInterrupt:
        print("\n[!] AgentsOffice stopped.")
        if frontend_proc:
            frontend_proc.terminate()


def main():
    parser = argparse.ArgumentParser(
        description="Launch the AgentsOffice pixel-art RPG multi-agent workspace"
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Start both backend and frontend dev server (requires Node.js)",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install Python dependencies before starting",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  [AgentsOffice] Pixel-Art RPG Multi-Agent Workspace")
    print("=" * 60)
    print()


    if args.install:
        install_python_deps()

    check_prerequisites()

    if args.dev:
        start_dev_mode()
    else:
        start_backend()


if __name__ == "__main__":
    main()
