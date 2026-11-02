"""Optional Razorpay test-mode integration. Creates an unpaid order only."""
import uuid
import pytest
from backend.payment_manager import PaymentManager


@pytest.mark.external
def test_razorpay_creates_unpaid_test_order(gateway_test_credentials):
    key, secret = gateway_test_credentials
    manager = PaymentManager(key, secret)
    manager.mode = "razorpay"
    manager._init_client()
    result = manager.create_order(1.0, f"nova_test_{uuid.uuid4().hex[:16]}")
    assert result["success"], result.get("error")
    assert result["is_live_sdk"]
    assert not result["is_sandbox"]
    assert result["amount"] == 100
    gateway_order = manager.client.order.fetch(result["razorpay_order_id"])
    assert gateway_order["status"] == "created"
    assert gateway_order["amount_paid"] == 0
