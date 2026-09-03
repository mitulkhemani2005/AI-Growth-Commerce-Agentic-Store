import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_store_root_and_branding():
    response = client.get("/")
    assert response.status_code == 200
    assert '<div id="root">' in response.text
    assert "Nava: Agentic AI Store" in response.text

def test_agent_readable_catalog():
    response = client.get("/.well-known/agent-catalog.json")
    assert response.status_code == 200
    data = response.json()
    assert data.get("protocol") == "UAP/ACP/AP2"
    assert data.get("store_name") == "Nava: Agentic AI Store"
    assert "products" in data
    assert len(data["products"]) > 0
    # Check first item schema
    p0 = data["products"][0]
    assert "@context" in p0
    assert "offers" in p0
    assert "priceFloor" in p0["offers"]
    assert "policies" in p0
    assert p0["policies"]["refund_window_hours"] == 24

def test_ap2_manifest():
    response = client.get("/.well-known/ap2-manifest.json")
    assert response.status_code == 200
    data = response.json()
    assert data.get("protocol") == "AP2"
    assert "mandate_limits" in data
    assert data["mandate_limits"]["max_single_transaction_inr"] == 25000.0

def test_cart_cross_sells():
    response = client.get("/api/cart/cross-sells?user_id=user_alex")
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "recommendations" in data
    assert len(data["recommendations"]) > 0
    r0 = data["recommendations"][0]
    assert "bundle_price" in r0
    assert "rationale" in r0

def test_campaign_orchestrator():
    response = client.get("/api/campaigns/active")
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True

    # Test launching a campaign
    launch_res = client.post("/api/admin/campaigns/launch", json={
        "title": "Weekend Titanium Drop",
        "category": "Laptops",
        "discount_percent": 10.0,
        "duration_hours": 48
    })
    assert launch_res.status_code == 200
    launch_data = launch_res.json()
    assert launch_data.get("success") is True
    assert "Weekend Titanium Drop" in launch_data["campaign"]["title"]

def test_financial_guardrails_audit_trail():
    response = client.get("/api/admin/audit-trail")
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "audit_trail" in data

def test_graceful_failure_handling_ap2_overspend():
    response = client.post("/api/simulation/failure-test", json={
        "failure_type": "AP2_OVERSPEND"
    })
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is False
    assert data.get("status") == "BOUNDED_REJECTION"
    assert "exceeds" in data.get("message")
    assert "graceful_recovery" in data

def test_graceful_failure_handling_expired_refund():
    response = client.post("/api/simulation/failure-test", json={
        "failure_type": "EXPIRED_REFUND"
    })
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is False
    assert data.get("status") == "GATED_REJECTION"
    assert "exceeds 24-hour" in data.get("message")

def test_graceful_failure_handling_base_floor_breach():
    response = client.post("/api/simulation/failure-test", json={
        "failure_type": "BASE_FLOOR_BREACH"
    })
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "BOUNDED_ENFORCEMENT"
    assert "Clamped" in data.get("message")

if __name__ == "__main__":
    test_store_root_and_branding()
    test_agent_readable_catalog()
    test_ap2_manifest()
    test_cart_cross_sells()
    test_campaign_orchestrator()
    test_financial_guardrails_audit_trail()
    test_graceful_failure_handling_ap2_overspend()
    test_graceful_failure_handling_expired_refund()
    test_graceful_failure_handling_base_floor_breach()
    print(">>> ALL NAVA STORE INTEGRATION TESTS PASSED WITH 100% SUCCESS! <<<")
