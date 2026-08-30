import asyncio
import pytest
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
from backend.treasury_manager import treasury_manager
from backend.inventory_manager import inventory_manager
from backend.order_manager import order_manager

@pytest.mark.asyncio
async def test_admin_fleet_inter_agent_collaboration():
    # 1. Reset Treasury and Setup Clean State
    treasury_manager.reset_treasury(10000.0)
    message_bus.clear_history()
    
    # 2. Test Inventory Manager Low Stock -> Restock Request to CEO
    products = inventory_manager.get_all_products()
    assert len(products) > 0
    p = products[0]
    p_id = p["id"]
    # Temporarily set stock to 2
    inventory_manager.update_stock(p_id, 2)
    
    # Run Inventory Manager cycle
    inv_res = await inventory_manager_agent.run_autonomous_cycle()
    assert inv_res["success"] is True
    
    # Check Message Bus has RESTOCK_REQUEST sent to CEO Agent
    msgs = message_bus.get_all_messages(limit=10)
    restock_req_msgs = [m for m in msgs if m.get("subject") == "RESTOCK_REQUEST"]
    assert len(restock_req_msgs) > 0
    assert restock_req_msgs[0]["to"] == "CEO Agent"
    
    # 3. Test CEO Agent cycle -> Approves Restock Request
    ceo_res = await ceo_agent.run_autonomous_cycle()
    assert ceo_res["success"] is True
    
    # Check Message Bus has RESTOCK_APPROVED sent to Inventory Manager Agent
    msgs = message_bus.get_all_messages(limit=10)
    restock_app_msgs = [m for m in msgs if m.get("subject") == "RESTOCK_APPROVED"]
    assert len(restock_app_msgs) > 0
    assert restock_app_msgs[0]["to"] == "Inventory Manager Agent"
    
    # 4. Run Inventory Manager cycle again -> Executes Approved Restock
    inv_res2 = await inventory_manager_agent.run_autonomous_cycle()
    assert inv_res2["success"] is True
    assert len(inv_res2["restocked"]) > 0
    
    # Check stock incremented
    updated_p = inventory_manager.get_product_by_id(p_id)
    assert int(updated_p["STOCK_REMAINING"]) > 2
    
    # 5. Create a new Confirmed order and test Dispatcher Agent
    order_res = order_manager.create_order(
        user_id="user_alex",
        items=[{"id": p_id, "quantity": 1}],
        customer_name="Alex Rivera",
        initial_status="Confirmed"
    )
    assert order_res["success"] is True
    new_oid = order_res["order"]["order_id"]
    
    # Run Dispatcher cycle -> Should dispatch order
    disp_res = await dispatcher_agent.run_autonomous_cycle()
    assert disp_res["success"] is True
    assert disp_res["dispatched_count"] > 0
    
    # Verify order is now Dispatched with tracking number
    dispatched_order = order_manager.get_order_by_id(new_oid)
    assert dispatched_order["status"] == "Dispatched"
    assert dispatched_order["tracking_number"] is not None
    assert dispatched_order["tracking_number"].startswith("TRK-")
    
    # Check Message Bus has DISPATCH_COMPLETED
    msgs = message_bus.get_all_messages(limit=15)
    disp_msgs = [m for m in msgs if m.get("subject") == "DISPATCH_COMPLETED"]
    assert len(disp_msgs) > 0
    
    # 6. Test CEO Owner Report
    report_res = await ceo_agent.generate_owner_report()
    assert report_res["success"] is True
    assert "report_markdown" in report_res
    assert "kpis" in report_res
    assert report_res["kpis"]["bank_balance"] > 0
