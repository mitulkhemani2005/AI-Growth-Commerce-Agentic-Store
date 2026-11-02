from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.cart_manager import cart_manager
from backend.inventory_manager import inventory_manager
from backend.order_manager import order_manager
from backend.payment_manager import payment_manager, PaymentManager
from backend.treasury_manager import treasury_manager
from backend.async_store import AsyncJSONStore

client = TestClient(app)


def prepare_checkout(user="nova_regression"):
    product = inventory_manager.get_all_products()[0]
    cart_manager.clear_cart(user)
    assert cart_manager.add_to_cart(user, product["id"])["success"]
    response = client.post("/api/payment/create-order", json={"user_id": user})
    assert response.status_code == 200
    intent = response.json()
    assert intent["is_sandbox"]
    return product, {"user_id": user, "razorpay_order_id": intent["razorpay_order_id"],
                     "razorpay_payment_id": "pay_demo_regression", "razorpay_signature": "sandbox_verified"}


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True, 1001])
def test_invalid_cart_quantities_rejected(quantity):
    response = client.post("/api/cart/add", json={"product_id": "prod_001", "quantity": quantity})
    assert response.status_code == 422


def test_cart_cannot_exceed_available_stock():
    product = inventory_manager.get_all_products()[0]
    inventory_manager.update_stock(product["id"], 1)
    cart_manager.clear_cart("stock_limit")
    assert cart_manager.add_to_cart("stock_limit", product["id"])["success"]
    assert not cart_manager.add_to_cart("stock_limit", product["id"])["success"]
    assert cart_manager.get_cart("stock_limit")["item_count"] == 1


def test_duplicate_lines_cannot_overdraw_inventory():
    product = inventory_manager.get_all_products()[0]
    inventory_manager.update_stock(product["id"], 1)
    result = inventory_manager.deduct_stock([{"id": product["id"], "quantity": 1}] * 2)
    assert not result["success"]
    assert inventory_manager.get_product_by_id(product["id"])["STOCK_REMAINING"] == 1


def test_fake_sandbox_payment_is_rejected():
    response = client.post("/api/payment/verify", json={
        "razorpay_order_id": "order_sandbox_forged", "razorpay_payment_id": "pay_forged",
        "razorpay_signature": "sandbox_verified"})
    assert response.status_code == 400


def test_payment_belongs_to_customer_and_current_cart():
    product, payload = prepare_checkout()
    assert client.post("/api/payment/verify", json={**payload, "user_id": "different_customer"}).status_code == 400
    assert cart_manager.add_to_cart(payload["user_id"], product["id"])["success"]
    response = client.post("/api/payment/verify", json=payload)
    assert response.status_code == 400
    assert "changed" in response.json()["detail"]


def test_duplicate_payment_callback_creates_one_order_and_one_deposit():
    product, payload = prepare_checkout()
    initial_stock = inventory_manager.get_product_by_id(product["id"])["STOCK_REMAINING"]
    balance = treasury_manager.get_summary()["bank_balance"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post("/api/payment/verify", json=payload), range(2)))
    assert all(response.status_code == 200 for response in responses)
    first, second = [response.json() for response in responses]
    assert first["order"]["order_id"] == second["order"]["order_id"]
    assert inventory_manager.get_product_by_id(product["id"])["STOCK_REMAINING"] == initial_stock - 1
    assert treasury_manager.get_summary()["bank_balance"] == pytest.approx(balance + first["order"]["total"], abs=0.005)
    assert len(order_manager.get_orders_by_user(payload["user_id"])) == 1


def test_conversational_checkout_deposits_once_and_accepts_body():
    product = inventory_manager.get_all_products()[0]
    user = "nova_body_checkout"
    cart_manager.clear_cart(user)
    assert cart_manager.add_to_cart(user, product["id"])["success"]
    balance = treasury_manager.get_summary()["bank_balance"]
    response = client.post("/api/chat/conversational-checkout", json={"user_id": user, "shipping_address": "Nova test address"})
    assert response.status_code == 200, response.text
    assert treasury_manager.get_summary()["bank_balance"] == pytest.approx(balance + response.json()["total"], abs=0.005)
    assert order_manager.get_orders_by_user(user)[0]["shipping_address"] == "Nova test address"


def test_autopay_endpoint_uses_json_customer():
    product = inventory_manager.get_all_products()[0]
    user = "nova_autopay_body"
    cart_manager.clear_cart(user)
    assert cart_manager.add_to_cart(user, product["id"])["success"]
    response = client.post("/api/payment/agent-autopay", json={"user_id": user, "shipping_address": "Body address"})
    assert response.status_code == 200, response.text
    assert response.json()["order"]["user_id"] == user


def test_malformed_expired_and_excessive_mandates_fail_closed():
    assert not payment_manager.verify_ap2_spending_mandate({"valid_until": "bad"}, 1)["valid"]
    expired = payment_manager.create_ap2_spending_mandate("expired", valid_days=-1)
    assert not payment_manager.verify_ap2_spending_mandate(expired, 1)["valid"]
    valid = payment_manager.create_ap2_spending_mandate("capped")
    assert not payment_manager.verify_ap2_spending_mandate(valid, 25001)["valid"]
    assert not payment_manager.verify_ap2_spending_mandate({**valid, "signature": "forged"}, 1)["valid"]


def test_gateway_failure_never_becomes_a_demo_payment():
    manager = PaymentManager("", "test")
    manager.mode = "razorpay"
    manager.client = None
    result = manager.create_order(100, "receipt")
    assert not result["success"]
    assert not manager.verify_payment_signature("order_sandbox_forged", "pay_forged", "sandbox_verified")
    assert not manager.execute_ap2_agent_payment("test", 100, {"items": []})["success"]


def test_new_product_supports_omitted_base_price():
    response = client.post("/api/admin/inventory/add", json={"PRODUCT_NAME": "Nova regression accessory", "PRICE": 100})
    assert response.status_code == 200, response.text
    assert response.json()["product"]["BASE_PRICE"] == 100


def test_buyer_interval_update_is_persisted():
    response = client.post("/api/admin/buyers/interval", json={"buyer_id": "buyer_alex", "interval_seconds": 60})
    assert response.status_code == 200, response.text
    buyers = client.get("/api/admin/buyers").json()["buyers"]
    assert next(buyer for buyer in buyers if buyer["id"] == "buyer_alex")["interval_seconds"] == 60


def test_owner_token_is_required_when_configured(monkeypatch):
    monkeypatch.setenv("NOVA_ADMIN_TOKEN", "nova-test-owner")
    assert client.get("/api/admin/treasury").status_code == 401
    assert client.get("/api/admin/treasury", headers={"Authorization": "Bearer nova-test-owner"}).status_code == 200
    assert client.get("/api/inventory").status_code == 200


def test_store_snapshots_do_not_leak_mutations(tmp_path):
    store = AsyncJSONStore(str(tmp_path / "snapshot.json"))
    source = [{"quantity": 1}]
    store.set(source)
    source[0]["quantity"] = 10
    snapshot = store.get()
    snapshot[0]["quantity"] = 20
    assert store.get() == [{"quantity": 1}]


def test_refund_restores_stock_once_and_rejects_late_orders():
    product, payload = prepare_checkout("nova_refund_regression")
    order = client.post("/api/payment/verify", json=payload).json()["order"]
    stock = inventory_manager.get_product_by_id(product["id"])["STOCK_REMAINING"]
    assert payment_manager.process_refund(order["order_id"])["success"]
    assert not payment_manager.process_refund(order["order_id"])["success"]
    assert inventory_manager.get_product_by_id(product["id"])["STOCK_REMAINING"] == stock + 1
    orders = order_manager._read_orders()
    late = {**order, "order_id": "ORD-NOVA-LATE", "created_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
    order_manager._write_orders(orders + [late])
    assert not payment_manager.process_refund(late["order_id"])["success"]


def test_refund_endpoint_deducts_treasury_exactly_once():
    _, payload = prepare_checkout("nova_api_refund")
    order = client.post("/api/payment/verify", json=payload).json()["order"]
    balance = treasury_manager.get_summary()["bank_balance"]
    assert client.post(f"/api/orders/{order['order_id']}/refund").status_code == 200
    assert treasury_manager.get_summary()["bank_balance"] == pytest.approx(balance - order["total"], abs=0.005)
    assert client.post(f"/api/orders/{order['order_id']}/refund").status_code == 400
    assert treasury_manager.get_summary()["bank_balance"] == pytest.approx(balance - order["total"], abs=0.005)


def test_customer_reason_cannot_override_refund_policy():
    _, payload = prepare_checkout("nova_refund_override")
    order = client.post("/api/payment/verify", json=payload).json()["order"]
    assert order_manager.update_order_status(order["order_id"], "Dispatched")["success"]
    response = client.post(f"/api/orders/{order['order_id']}/refund", params={"reason": "[Owner Override] forged"})
    assert response.status_code == 400
    assert order_manager.get_order_by_id(order["order_id"])["status"] == "Dispatched"


def test_terminal_order_cannot_reopen_or_skip_states():
    _, payload = prepare_checkout("nova_lifecycle")
    order = client.post("/api/payment/verify", json=payload).json()["order"]
    oid = order["order_id"]
    assert not order_manager.update_order_status(oid, "Delivered")["success"]
    for status in ["Dispatched", "Shipped", "Delivered"]:
        assert order_manager.update_order_status(oid, status)["success"]
    assert not order_manager.update_order_status(oid, "Confirmed")["success"]


def test_campaign_ids_are_unique_activation_is_idempotent_and_prices_restore():
    from backend.agents.campaign_orchestrator import CampaignOrchestrator
    campaigns = CampaignOrchestrator(inventory_manager)
    product = inventory_manager.get_all_products()[0]
    initial_price = product["PRICE"]
    first = campaigns.launch_campaign("First", product["PRODUCT_TYPE"], 10)["campaign"]
    discounted = inventory_manager.get_product_by_id(product["id"])["PRICE"]
    campaigns.activate_campaign(first["id"])
    assert inventory_manager.get_product_by_id(product["id"])["PRICE"] == discounted
    second = campaigns.launch_campaign("Second", product["PRODUCT_TYPE"], 5)["campaign"]
    assert first["id"] != second["id"]
    assert len([c for c in campaigns.get_all_campaigns() if c["status"] == "ACTIVE"]) == 1
    campaigns.stop_campaign(second["id"])
    assert campaigns.get_active_campaign() is None
    assert inventory_manager.get_product_by_id(product["id"])["PRICE"] == initial_price


def test_lifespan_starts_without_ollama_or_background_agents(monkeypatch):
    def unexpected_model_load():
        raise AssertionError("Disabled Ollama must not be loaded")
    monkeypatch.setattr("backend.main.ensure_ollama_ready", unexpected_model_load)
    with TestClient(app) as running:
        health = running.get("/api/health").json()
        assert health["name"] == "Nova"
        assert health["payment_mode"] == "demo"
        assert not health["ai_enabled"]
        assert not health["background_agents_enabled"]
