import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.treasury_manager import treasury_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_treasury():
    treasury_manager.reset_treasury(1000.0)
    yield

def test_api_treasury_overview():
    res = client.get("/api/admin/treasury")
    assert res.status_code == 200
    data = res.json()
    assert "bank_balance" in data
    assert "total_sales_revenue" in data
    assert "net_profit" in data

def test_api_salaries():
    res = client.get("/api/admin/salaries")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert len(data["salaries"]) == 6

def test_api_buyers_list():
    res = client.get("/api/admin/buyers")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert len(data["buyers"]) == 5

def test_api_acquire_stock():
    # Get a product ID
    inv_res = client.get("/api/inventory")
    products = inv_res.json()["products"]
    prod_id = products[0]["id"]

    res = client.post("/api/admin/treasury/acquire-stock", json={
        "product_id": prod_id,
        "quantity": 5,
        "actor": "API Test"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["quantity_acquired"] == 5

def test_api_trigger_buyer():
    res = client.post("/api/admin/buyers/trigger", json={
        "buyer_id": "buyer_sophia"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["buyer_id"] == "buyer_sophia"

def test_api_toggle_buyers():
    res = client.post("/api/admin/buyers/toggle", json={})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "enabled" in data
