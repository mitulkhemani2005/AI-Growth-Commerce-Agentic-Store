import time

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend import ollama_loader
from backend.admin_agents import log_agent_action, get_agent_logs


def test_gpu_model_matching_never_accepts_another_parameter_size(monkeypatch):
    monkeypatch.setattr(ollama_loader, "get_running_vram_models", lambda host=None: [
        {"name": "qwen2.5:0.5b", "size": 500, "size_vram": 500}
    ])
    assert ollama_loader.model_is_fully_gpu_resident("qwen2.5:0.5b")
    assert not ollama_loader.model_is_fully_gpu_resident("qwen2.5:7b")


@pytest.mark.parametrize("vram", [0, 499])
def test_partial_or_cpu_model_is_not_ready(monkeypatch, vram):
    monkeypatch.setattr(ollama_loader, "get_running_vram_models", lambda host=None: [
        {"name": "qwen2.5:0.5b", "size": 500, "size_vram": vram}
    ])
    assert not ollama_loader.model_is_fully_gpu_resident("qwen2.5:0.5b")


def test_missing_configured_model_does_not_load_an_alternative(monkeypatch):
    monkeypatch.setattr(ollama_loader, "is_ollama_running", lambda: True)
    monkeypatch.setattr(ollama_loader, "get_available_models", lambda: ["qwen2.5:0.5b"])
    monkeypatch.setattr(ollama_loader, "preload_model_in_vram", lambda *_: pytest.fail("Unexpected model load"))
    assert not ollama_loader.ensure_ollama_ready("qwen2.5:7b")


def test_unverified_preload_is_rejected_and_unloaded(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    unloaded = []
    monkeypatch.setattr(ollama_loader.urllib.request, "urlopen", lambda *a, **kw: Response())
    monkeypatch.setattr(ollama_loader, "get_running_vram_models", lambda host=None: [])
    monkeypatch.setattr(ollama_loader, "unload_model_from_vram", lambda name, host: unloaded.append(name))
    assert not ollama_loader.preload_model_in_vram("qwen2.5:0.5b")
    assert unloaded == ["qwen2.5:0.5b"]


def test_cpu_residency_prevents_an_inference_request(monkeypatch):
    from backend import llm_runtime
    monkeypatch.setattr(llm_runtime, "configured_model", lambda: "test:local")
    monkeypatch.setattr(llm_runtime, "model_is_fully_gpu_resident", lambda model: False)
    monkeypatch.setattr(llm_runtime, "ensure_ollama_ready", lambda model: False)
    monkeypatch.setattr(llm_runtime, "OpenAI", lambda **kw: pytest.fail("CPU model must not receive inference"))
    with pytest.raises(RuntimeError, match="CPU/RAM inference is blocked"):
        llm_runtime.complete_chat(model="test:local", messages=[])


def test_manual_run_is_scheduled_on_the_application_event_loop(monkeypatch):
    called = []

    async def run(key):
        called.append(key)
        log_agent_action("Dispatcher Agent", "Verification cycle completed", "Manual scheduling works.")
        return {"success": True}

    monkeypatch.setattr("backend.main.background_worker.trigger_agent", run)
    with TestClient(app) as client:
        result = client.post("/api/admin/agents/trigger", json={"agent_key": "dispatcher"})
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "QUEUED"
        for _ in range(20):
            if called:
                break
            time.sleep(0.01)
        assert called == ["dispatcher"]
        logs = client.get("/api/admin/agent-logs").json()["logs"]
        assert any(item["action"] == "Verification cycle completed" for item in logs)


def test_activity_api_keeps_newest_actions_and_all_details():
    first = log_agent_action("QA Agent", "First action", "First detail")
    second = log_agent_action("QA Agent", "Second action", "Second detail")
    logs = get_agent_logs(2)
    assert [entry["id"] for entry in logs] == [second["id"], first["id"]]
    assert logs[0]["details"] == "Second detail"


@pytest.mark.asyncio
async def test_discovery_respects_category_and_budget_without_model_hallucinations():
    from backend.agent import commerce_agent
    result = await commerce_agent.run_prompt("Show me laptops under 5000 rupees.", user_id="grounded_discovery")
    assert result["response_source"] == "live_inventory"
    products = result["action_data"]["searched_products"]
    assert products
    assert all(product["PRODUCT_TYPE"] == "Laptops" and product["PRICE"] <= 5000 for product in products)
    assert "Mouse" not in result["response"]
    assert result["checkout_payload"] is None


@pytest.mark.asyncio
async def test_repeated_scarcity_cycles_do_not_compound_prices(monkeypatch):
    from backend.admin_agents import PriceManagerAgent, inventory_manager, message_bus
    product = dict(inventory_manager.get_all_products()[0])
    product.update(BASE_PRICE=100, PRICE=135, STOCK_REMAINING=2)
    inventory_manager._write_inventory([product])
    monkeypatch.setattr(message_bus, "get_inbox", lambda *_: [])
    manager = PriceManagerAgent()
    for _ in range(30):
        await manager.run_autonomous_cycle()
    assert inventory_manager.get_product_by_id(product["id"])["PRICE"] == 155.25


@pytest.mark.asyncio
async def test_scarcity_does_not_overwrite_higher_owner_price(monkeypatch):
    from backend.admin_agents import PriceManagerAgent, inventory_manager, message_bus
    product = dict(inventory_manager.get_all_products()[0])
    product.update(BASE_PRICE=100, PRICE=190, STOCK_REMAINING=2)
    inventory_manager._write_inventory([product])
    monkeypatch.setattr(message_bus, "get_inbox", lambda *_: [])
    await PriceManagerAgent().run_autonomous_cycle()
    assert inventory_manager.get_product_by_id(product["id"])["PRICE"] == 190
