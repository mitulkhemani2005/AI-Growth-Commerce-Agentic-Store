import pytest
import asyncio
import os
import json
from backend.treasury_manager import treasury_manager
from backend.inventory_manager import inventory_manager
from backend.salary_manager import salary_manager
from backend.buyer_agents import buyer_agents_fleet
from backend.admin_agents import ceo_agent, message_bus
from backend.order_manager import order_manager

@pytest.fixture(autouse=True)
def setup_treasury():
    # Reset treasury to initial capital
    treasury_manager.reset_treasury(1000.0)
    yield

def test_treasury_initial_state():
    summary = treasury_manager.get_summary()
    assert summary["bank_balance"] == 1000.0
    assert summary["total_sales_revenue"] == 0.0
    assert summary["net_profit"] == 0.0

def test_wholesale_stock_acquisition():
    # Find first product
    products = inventory_manager.get_all_products()
    assert len(products) > 0
    p = products[0]
    p_id = p["id"]
    base_price = float(p.get("BASE_PRICE") or p.get("PRICE"))
    
    initial_summary = treasury_manager.get_summary()
    initial_balance = initial_summary["bank_balance"]
    initial_stock = p.get("STOCK_REMAINING", 0)

    # Acquire 10 units at base price
    res = inventory_manager.acquire_wholesale_stock(p_id, 10, actor="CEO Test")
    assert res["success"] is True
    assert res["quantity_acquired"] == 10
    assert res["base_price"] == base_price
    assert res["total_cost"] == 10 * base_price


    # Verify inventory stock incremented
    updated_p = inventory_manager.get_product_by_id(p_id)
    assert updated_p["STOCK_REMAINING"] == initial_stock + 10

    # Verify treasury balance deducted
    new_summary = treasury_manager.get_summary()
    assert new_summary["bank_balance"] == initial_balance - (10 * base_price)
    assert new_summary["total_wholesale_stock_spend"] == 10 * base_price

def test_sales_deposit_and_profit_realization():
    # Acquire 5 units
    products = inventory_manager.get_all_products()
    p = products[0]
    base_price = float(p.get("BASE_PRICE") or 2000.0)
    selling_price = float(p.get("PRICE") or (base_price + 500.0))

    inventory_manager.acquire_wholesale_stock(p["id"], 5, actor="CEO Test")
    
    summary_before = treasury_manager.get_summary()
    bal_before = summary_before["bank_balance"]

    # Sell 2 units at selling price
    order_total = 2 * selling_price
    treasury_manager.deposit_sales(
        amount=order_total,
        order_id="TEST-ORD-001",
        items_summary=f"2x {p['PRODUCT_NAME']}",
        customer="Test Customer"
    )

    summary_after = treasury_manager.get_summary()
    assert summary_after["bank_balance"] == bal_before + order_total
    assert summary_after["total_sales_revenue"] == order_total

def test_salary_manager_and_disbursal():
    salaries_data = salary_manager.get_all_salaries()
    assert len(salaries_data["salaries"]) == 6
    assert salaries_data["total_payroll_per_cycle"] > 0

    bal_before = treasury_manager.get_summary()["bank_balance"]

    # Disburse single agent salary
    res = salary_manager.pay_salaries("Price Manager Agent", actor="CEO Test")
    assert res["success"] is True
    assert res["total_disbursed"] > 0

    bal_after = treasury_manager.get_summary()["bank_balance"]
    assert bal_after == bal_before - res["total_disbursed"]

def test_5_ai_buyers_fleet_structure():
    buyers = buyer_agents_fleet.get_all_buyers()
    assert len(buyers) == 5
    buyer_ids = [b["id"] for b in buyers]
    assert "buyer_alex" in buyer_ids
    assert "buyer_sophia" in buyer_ids
    assert "buyer_david" in buyer_ids
    assert "buyer_elena" in buyer_ids
    assert "buyer_marcus" in buyer_ids

@pytest.mark.asyncio
async def test_ai_buyer_step_execution():
    # Restock all items with some units so buyers can purchase
    for p in inventory_manager.get_all_products()[:3]:
        inventory_manager.acquire_wholesale_stock(p["id"], 10, actor="CEO Test")

    # Run buyer step for Alex
    res = await buyer_agents_fleet.execute_buyer_step("buyer_alex")
    assert res["success"] is True
    assert res["buyer_id"] == "buyer_alex"
    assert "buyer_name" in res


@pytest.mark.asyncio
async def test_ceo_discussion_meeting():
    # Conduct CEO multi-agent roundtable meeting
    topic = "Wholesale stock restock budget and Q1 margin strategy"
    res = await ceo_agent.conduct_ceo_discussion(topic, participants="ALL_AGENTS")
    assert res["success"] is True
    assert res["topic"] == topic
    assert len(res["transcript"]) >= 2
    assert "conclusion" in res
    assert "discussion_id" in res
