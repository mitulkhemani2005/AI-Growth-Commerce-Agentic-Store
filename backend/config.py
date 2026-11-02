"""Shared Nova configuration. Environment variables override the project .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DATA_DIR = Path(os.getenv("NOVA_DATA_DIR", str(BASE_DIR / "data"))).resolve()


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def data_file(name: str) -> str:
    return str(DATA_DIR / name)


AI_ENABLED = env_bool("AI_ENABLED", True)
BACKGROUND_AGENTS_ENABLED = env_bool("BACKGROUND_AGENTS_ENABLED", True)
PAYMENT_MODE = os.getenv("PAYMENT_MODE", "demo").strip().lower()
if PAYMENT_MODE not in {"demo", "razorpay"}:
    raise ValueError("PAYMENT_MODE must be demo or razorpay")
