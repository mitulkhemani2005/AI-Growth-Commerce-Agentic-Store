"""
Unit Tests for Upgraded Agent Capabilities & High-Level Decision Tools
"""

import pytest
import asyncio
from backend.agent import commerce_agent
from backend.admin_agents import (
    price_manager_agent,
    inventory_manager_agent,
    order_management_agent,
    finance_manager_agent,
    dispatcher_agent,
    review_feedback_agent,
    ceo_agent
)
from backend.buyer_agents import buyer_agents_fleet
from backend.inventory_manager import inventory_manager
from backend.order_manager import order_manager
from backend.treasury_manager import treasury_manager


@pytest.fixture(autouse=True)
def setup_store_fixtures():
    # Ensure active test products exist
    products = inventory_manager.get_all_products()
    if products:
        products[0]["STOCK_REMAINING"] = 10
        products[0]["PRICE"] = 1500.0
        products[0]["BASE_PRICE"] = 1000.0
        inventory_manager._write_inventory(products)
    yield


# 1. Nova (Customer Agent) Tools
def test_nova_purchase_assistant():
    products = inventory_manager.get_all_products()
    pid = products[0]["id"]
    res = commerce_agent.execute_tool(
        "purchase_assistant",
        {"products": [pid], "quantities": [1]},
        user_id="user_test"
    )
    assert res.get("success") is True
    assert res.get("needs_razorpay_checkout") is True
    assert len(res.get("added_items", [])) == 1


def test_nova_recommendations_and_comparisons():
    # Recommendations
    rec_res = commerce_agent.execute_tool("recommend_products", {"category": "Mobiles"}, user_id="user_test")
    assert rec_res.get("success") is True
    assert "recommendations" in rec_res

    # Compare
    products = inventory_manager.get_all_products()
    if len(products) >= 2:
        comp_res = commerce_agent.execute_tool("compare_products", {"product_ids": [products[0]["id"], products[1]["id"]]}, user_id="user_test")
        assert comp_res.get("success") is True
        assert len(comp_res.get("comparison", [])) == 2


def test_nova_apply_coupon():
    c_res = commerce_agent.execute_tool("apply_coupon", {"coupon_code": "GROWTH10"}, user_id="user_test")
    assert c_res.get("success") is True
    assert c_res.get("discount_percentage") == 10.0


# 2. Price Manager Agent Tools
def test_price_manager_estimate_optimal_price():
    products = inventory_manager.get_all_products()
    pid = products[0]["id"]
    res = price_manager_agent.estimate_optimal_price(pid)
    assert res.get("success") is True
    assert "recommended_price" in res
    assert res.get("recommended_price") >= float(products[0]["BASE_PRICE"])


@pytest.mark.asyncio
async def test_price_manager_set_approved_price():
    products = inventory_manager.get_all_products()
    pid = products[0]["id"]
    base_p = float(products[0]["BASE_PRICE"])
    target_p = round(base_p * 1.30, 2)
    res = await price_manager_agent.set_approved_price(pid, target_p, reason="Test approved price update")
    assert res.get("success") is True
    assert res.get("new_price") == target_p


# 3. Inventory Manager Agent Tools
def test_inventory_manager_reorder_point():
    products = inventory_manager.get_all_products()
    pid = products[0]["id"]
    res = inventory_manager_agent.calculate_reorder_point(pid)
    assert res.get("success") is True
    assert "reorder_point" in res
    assert "safety_stock" in res


@pytest.mark.asyncio
async def test_inventory_manager_reconcile_inventory():
    products = inventory_manager.get_all_products()
    pid = products[0]["id"]
    res = await inventory_manager_agent.reconcile_inventory(pid, 15, reason="Audit physical count verified")
    assert res.get("success") is True
    assert res.get("new_stock") == 15


# 4. Order Management Agent Tools
@pytest.mark.asyncio
async def test_order_management_advance_order():
    orders = order_manager.get_all_orders()
    if not orders:
        order_manager.create_order(
            user_id="user_test",
            items=[{"id": "prod_001", "PRODUCT_NAME": "Nova Phone", "quantity": 1, "price": 1000.0}],
            total=1000.0,
            shipping_address="Test Address"
        )
        orders = order_manager.get_all_orders()

    oid = orders[0]["order_id"]
    # Update to Confirmed first if needed
    order_manager.update_order_status(oid, "Pending")
    res = await order_management_agent.advance_order(oid, "Confirmed", reason="Payment confirmed")
    assert res.get("success") is True


# 5. Dispatcher Agent Tools
def test_dispatcher_select_carrier_and_create_label():
    carrier_res = dispatcher_agent.select_best_carrier()
    assert carrier_res.get("success") is True
    assert "carrier" in carrier_res

    orders = order_manager.get_all_orders()
    if orders:
        label_res = dispatcher_agent.create_shipping_label(orders[0]["order_id"])
        assert label_res.get("success") is True
        assert label_res.get("tracking_number").startswith("TRK-")


# 6. Finance Manager Agent Tools
def test_finance_manager_reconcile_payments():
    res = finance_manager_agent.reconcile_payments()
    assert res.get("success") is True
    assert res.get("reconciliation_status") == "MATCHED"


# 7. Review & Feedback Agent Tools
def test_review_manager_cluster_issues():
    res = review_feedback_agent.cluster_review_issues()
    assert res.get("success") is True
    assert "issue_clusters" in res


# 8. CEO Agent Tools
@pytest.mark.asyncio
async def test_ceo_delegate_and_simulate():
    del_res = await ceo_agent.delegate_task("Price Manager Agent", "Conduct price elasticity review")
    assert del_res.get("success") is True
    assert "task_id" in del_res

    sim_res = ceo_agent.simulate_business_decision("Reduce Audio SKU prices by 5%")
    assert sim_res.get("success") is True
    assert "expected_revenue_change" in sim_res
    assert "recommendation" in sim_res


# 9. Buyer Fleet Invariant QA
def test_buyer_fleet_validate_invariants():
    inv_res = buyer_agents_fleet.validate_business_invariants()
    assert inv_res.get("success") is True
    assert inv_res.get("passed") is True
    assert inv_res.get("total_violations") == 0
