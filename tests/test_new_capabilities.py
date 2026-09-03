import pytest
import asyncio
from backend.cart_manager import cart_manager
from backend.order_manager import order_manager
from backend.payment_manager import payment_manager
from backend.inventory_manager import inventory_manager
from backend.agent_tasks import task_manager
from backend.admin_agents import message_bus, price_manager_agent, dispatcher_agent, finance_manager_agent
from backend.events import EventType

@pytest.mark.asyncio
async def test_ap2_payment_and_event_messaging():
    uid = "test_user_ap2_verification"
    cart_manager.clear_cart(uid)
    
    products = inventory_manager.get_all_products()
    test_p = products[0]
    cart_manager.add_to_cart(uid, test_p["id"], 1)
    
    # Check cart
    cart = cart_manager.get_cart(uid)
    assert len(cart.get("items", [])) >= 1
    
    # Perform AP2 autonomous pay
    res = payment_manager.autonomous_agent_pay(uid)
    assert res.get("success") is True
    assert res.get("order_id") is not None
    assert res.get("razorpay_payment_id") is not None
    assert res.get("order", {}).get("status") == "Confirmed"
    
    # Verify messages published on message bus for this specific order
    oid = res.get("order_id")
    order_msgs = [m for m in message_bus.get_all_messages() if m.get("payload", {}).get("order_id") == oid]
    subjects = [m.get("subject") for m in order_msgs]
    assert "ORDER_CONFIRMED" in subjects or "ORDER_PAYMENT_CAPTURED" in subjects or "PAYMENT_RECEIVED" in subjects
    
    # Assert NO event messages were sent by CEO Agent
    ceo_msgs = [m for m in order_msgs if m.get("from_agent") == "CEO Agent"]
    assert len(ceo_msgs) == 0

@pytest.mark.asyncio
async def test_task_claiming_and_execution_lifecycle():
    # 1. Create a task for Price Manager Agent
    task = task_manager.create_task(
        assigned_to="Price Manager Agent",
        objective="Run promotional discount audit on catalog",
        priority="high",
        created_by="CEO Agent"
    )
    assert task.status == "pending"
    
    # 2. Run autonomous cycle for Price Manager
    res = await price_manager_agent.run_autonomous_cycle()
    assert res.get("success") is True
    
    # 3. Check task is now completed
    updated_t = task_manager.get_task(task.task_id)
    assert updated_t.status == "completed"
    assert updated_t.result is not None
    
    # 4. Check message bus has TASK_COMPLETED report
    inbox_ceo = message_bus.get_inbox("CEO Agent")
    task_msgs = [m for m in inbox_ceo if m.get("subject") == "TASK_COMPLETED" and m.get("payload", {}).get("task_id") == task.task_id]
    assert len(task_msgs) >= 1

@pytest.mark.asyncio
async def test_ai_chat_ap2_and_razorpay_checkout():
    from backend.agent import CommerceAgent
    agent = CommerceAgent()
    uid = "test_chat_user_ap2"
    
    # Ensure inventory has stock
    inventory_manager.update_stock("prod_001", 50)
    inventory_manager.update_stock("prod_002", 50)
    
    # Setup cart
    cart_manager.clear_cart(uid)
    add_res = cart_manager.add_to_cart(uid, "prod_001", 1)
    assert add_res.get("success") is True
    
    # 1. Customer asks for AP2 auto-pay
    ap2_chat_res = await agent.run_prompt(
        prompt="Please auto pay for my cart using AP2 autonomous payment",
        user_id=uid
    )
    assert ap2_chat_res.get("response") is not None
    assert ap2_chat_res.get("action_data", {}).get("autonomous_agent_pay", {}).get("success") is True
    assert "AP2" in ap2_chat_res.get("response")
    
    # Setup cart again with second product
    add_res2 = cart_manager.add_to_cart(uid, "prod_002", 1)
    assert add_res2.get("success") is True
    
    # 2. Customer asks for standard Razorpay checkout
    checkout_chat_res = await agent.run_prompt(
        prompt="I want to checkout my cart now and pay with card",
        user_id=uid
    )
    assert checkout_chat_res.get("checkout_payload") is not None
    assert checkout_chat_res.get("checkout_payload", {}).get("needs_razorpay_checkout") is True

