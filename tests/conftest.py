"""Run tests against disposable data, never the developer's store or gateway."""

import os
import json
import shutil
import tempfile
from pathlib import Path

import pytest
from dotenv import dotenv_values

_file_settings = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
_external_credentials = tuple(os.getenv(name) or _file_settings.get(name, "") for name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET"))

# This runs before test modules import backend singletons.
_sandbox = tempfile.TemporaryDirectory(prefix="nova-tests-")
_test_data = Path(_sandbox.name) / "data"
shutil.copytree(Path(__file__).resolve().parents[1] / "data", _test_data)
os.environ["NOVA_DATA_DIR"] = str(_test_data)
os.environ["PAYMENT_MODE"] = "demo"
os.environ["AI_ENABLED"] = "false"
os.environ["BACKGROUND_AGENTS_ENABLED"] = "false"
os.environ["BUYER_SIMULATION_ENABLED"] = "false"
os.environ["NOVA_ADMIN_TOKEN"] = ""
os.environ["RAZORPAY_KEY_ID"] = ""
os.environ["RAZORPAY_KEY_SECRET"] = "nova-disposable-test-secret"

# Deterministic business fixtures independent of the current running demo state.
_products = json.loads((_test_data / "inventory.json").read_text(encoding="utf-8"))
for product in _products:
    product["STOCK_REMAINING"] = 30
    product["BASE_PRICE"] = 1200.0
    product["PRICE"] = 2000.0
(_test_data / "inventory.json").write_text(json.dumps(_products), encoding="utf-8")
for name in ["orders", "campaigns", "agent_logs", "agent_messages", "agent_conversations", "reviews", "agent_tasks", "idempotency_records"]:
    (_test_data / f"{name}.json").unlink(missing_ok=True)


def pytest_addoption(parser):
    parser.addoption("--run-external", action="store_true", help="Run tests needing Ollama or real Razorpay credentials.")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-external"):
        return
    for item in items:
        if "external" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="Requires external services; enable with --run-external."))


@pytest.fixture
def gateway_test_credentials():
    key, secret = _external_credentials
    if not key.startswith("rzp_test_") or not secret:
        pytest.skip("External gateway checks require Razorpay test credentials.")
    return key, secret


@pytest.fixture(autouse=True)
def isolate_store_files():
    """Restore disk snapshots after each case, including when a test fails."""
    before = {path.name: path.read_bytes() for path in _test_data.glob("*.json")}
    yield
    for path in _test_data.glob("*.json"):
        if path.name not in before:
            path.unlink()
    for name, contents in before.items():
        (_test_data / name).write_bytes(contents)
