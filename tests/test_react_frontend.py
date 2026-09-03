import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_root_serves_react_frontend():
    response = client.get("/")
    assert response.status_code == 200
    assert '<div id="root">' in response.text
    assert "src=\"/assets/" in response.text or "module" in response.text

def test_admin_serves_react_frontend():
    response = client.get("/admin")
    assert response.status_code == 200
    assert '<div id="root">' in response.text

def test_inventory_api():
    response = client.get("/api/inventory")
    assert response.status_code == 200
    data = response.json()
    assert "products" in data
    assert len(data["products"]) > 0

def test_cart_api():
    response = client.get("/api/cart?user_id=user_alex")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data

def test_admin_overview_api():
    response = client.get("/api/admin/overview")
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "kpis" in data

def test_admin_treasury_api():
    response = client.get("/api/admin/treasury")
    assert response.status_code == 200
    data = response.json()
    assert "bank_balance" in data

def test_admin_buyers_api():
    response = client.get("/api/admin/buyers")
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert len(data.get("buyers", [])) >= 5

if __name__ == "__main__":
    test_root_serves_react_frontend()
    test_admin_serves_react_frontend()
    test_inventory_api()
    test_cart_api()
    test_admin_overview_api()
    test_admin_treasury_api()
    test_admin_buyers_api()
    print("ALL TESTS PASSED SUCCESSFULLY!")
