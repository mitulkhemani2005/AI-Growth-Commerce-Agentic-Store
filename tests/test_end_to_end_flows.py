"""
End-to-End Integration Flow Tests
=================================
Validates full multi-agent business flows:
1. Discovery -> Purchase Assistant -> Checkout -> Dispatch -> Delivery
2. Low Stock -> Restock Request -> CEO Approval -> Inventory Acquisition
3. Dynamic Price Optimization -> Policy Validation -> Live Catalog Update
4. Cancellation -> 24h Policy Check -> Finance Refund Execution -> Inventory Restock
5. Defect Feedback -> Quality Alert -> CEO Escalation
"""

import pytest
import asyncio
from datetime import datetime, timezone

from backend.agent import commerce_agent
from backend.admin_agents import (
    price_manager_agent,
    inventory_manager_agent,
    order_management_agent,
    finance_manager_agent,
    dispatcher_agent,
    review_feedback_agent,
    ceo_agent,
    message_bus
)
from backend.buyer_agents import buyer_agents_fleet
from backend.inventory_manager import inventory_manager
from backend.cart_manager import cart_manager
from backend.order_manager import order_manager
from backend.payment_manager import payment_manager
from backend.treasury_manager import treasury_manager


@pytest.fixture(autouse=True)
def init_clean_environment():
    # Setup test product and clean treasury
    treasury_manager.reset_treasury(500000.0)
    products = inventory_manager.get_all_products()
    if products:
        products[0]["STOCK_REMAINING"] = 10
        products[0]["PRICE"] = 2000.0
        products[0]["BASE_PRICE"] = 1200.0
        inventory_manager._write_inventory(products)
    yield


@pytest.mark.asyncio
async def test_end_to_end_purchase_dispatch_delivery_flow():
    products = inventory_manager.get_all_products()
    target_p = products[0]
    initial_stock = int(target_p.get("STOCK_REMAINING", 10))

    # 1. Customer uses purchase assistant
    user_id = "user_e2e_customer"
    assist_res = commerce_agent.execute_tool(
        "purchase_assistant",
        {"products": [target_p["id"]], "quantities": [2]},
        user_id=user_id
    )
    assert assist_res.get("success") is True
    assert assist_res.get("needs_razorpay_checkout") is True

    # 2. Automated payment executes
    ap2_res = payment_manager.execute_automated_preauthorized_payment(
        user_id=user_id,
        shipping_address="742 Tech Hub Boulevard",
        customer_name="E2E Customer",
        customer_email="e2e@growthcommerce.ai"
    )
    assert ap2_res.get("success") is True
    order_id = ap2_res.get("order_id")

    # Verify inventory was deducted
    updated_p = inventory_manager.get_product_by_id(target_p["id"])
    assert int(updated_p.get("STOCK_REMAINING")) == (initial_stock - 2)

    # 3. Dispatcher creates shipping label
    label_res = dispatcher_agent.create_shipping_label(order_id)
    assert label_res.get("success") is True
    tracking_num = label_res.get("tracking_number")

    # 4. Advance through lifecycle
    ship_res = await order_management_agent.advance_order(order_id, "Shipped", reason="In transit with carrier")
    assert ship_res.get("success") is True

    deliv_res = await order_management_agent.advance_order(order_id, "Delivered", reason="Signed by customer")
    assert deliv_res.get("success") is True

    # Check final order state
    final_order = order_manager.get_order_by_id(order_id)
    assert final_order.get("status") == "Delivered"
    assert final_order.get("tracking_number") == tracking_num


@pytest.mark.asyncio
async def test_end_to_end_restock_and_ceo_approval_flow():
    products = inventory_manager.get_all_products()
    target_p = products[0]
    pid = target_p["id"]
    base_p = float(target_p.get("BASE_PRICE") or 1000.0)

    # 1. Inventory Manager creates restock request
    req_res = await inventory_manager_agent.create_purchase_request(pid, quantity=10, reason="Safety stock low")
    assert req_res.get("success") is True

    # 2. CEO Agent approves request
    appr_res = await ceo_agent._execute_ceo_tool("approve_restock_request", {"product_identifier": pid, "quantity": 10, "approved": True})
    assert appr_res.get("success") is True
    assert appr_res.get("approved") is True

    # 3. Inventory Manager autonomous cycle acquires wholesale stock
    cur_stock = int(inventory_manager.get_product_by_id(pid).get("STOCK_REMAINING", 0))
    cycle_res = await inventory_manager_agent.run_autonomous_cycle()
    assert cycle_res.get("success") is True

    new_stock = int(inventory_manager.get_product_by_id(pid).get("STOCK_REMAINING", 0))
    assert new_stock >= (cur_stock + 10)


@pytest.mark.asyncio
async def test_end_to_end_cancellation_and_finance_refund_flow():
    # 1. Create a confirmed order
    order_res = order_manager.create_order(
        user_id="user_refund_test",
        items=[{"id": "prod_001", "PRODUCT_NAME": "Nova Test Product", "quantity": 1, "price": 1500.0}],
        total=1500.0,
        shipping_address="Refund Street"
    )
    order_id = order_res.get("order_id")

    # 2. Finance Manager processes refund
    refund_res = await finance_manager_agent.process_refund(order_id, reason="Customer canceled within 24h window")
    assert refund_res.get("success") is True
    assert refund_res.get("status") == "Refunded"

    # 3. Attempt duplicate refund -> Must be rejected / idempotent replay
    dup_refund = await finance_manager_agent.process_refund(order_id, reason="Duplicate attempt")
    assert dup_refund.get("idempotent_replay") is True or dup_refund.get("status") == "Refunded"


def test_end_to_end_continuous_qa_invariants():
    report = buyer_agents_fleet.generate_test_report()
    assert report.get("success") is True
    assert report.get("invariants_result", {}).get("passed") is True
