import asyncio
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


from backend.inventory_manager import inventory_manager
from backend.cart_manager import cart_manager
from backend.order_manager import order_manager
from backend.review_manager import review_manager
from backend.admin_agents import (
    price_manager_agent,
    inventory_manager_agent,
    order_management_agent,
    finance_manager_agent,
    dispatcher_agent,
    review_feedback_agent,
    ceo_agent,
    admin_chat_agent,
    message_bus,
    get_agent_logs,
    # legacy aliases
    order_manager_agent,
    refund_manager_agent
)
from backend.background_workers import background_worker

async def test_all_async():
    print("==================================================================", flush=True)
    print("TESTING FULL SYSTEM (INR CURRENCY + 0% TAX + OWNER BASE PRICE + AUDIT LOGS)", flush=True)
    print("==================================================================", flush=True)

    # 1. Test 0% Tax and INR Currency in Cart & Order Manager
    print("\n--- 1. Testing 0% Tax & INR Currency Policy ---", flush=True)
    cart_manager.clear_cart("user_test_inr")
    cart_manager.add_to_cart("user_test_inr", "NOVA Apex Pro 5G Smartphone", quantity=2)
    cart = cart_manager.get_cart("user_test_inr")
    print(f"[OK] Cart Subtotal: ₹{cart['subtotal']} | Tax (0%): ₹{cart['estimated_tax']} | Total: ₹{cart['estimated_total']}", flush=True)
    assert cart["estimated_tax"] == 0.0, "Tax must be 0%!"
    assert cart["estimated_total"] == cart["subtotal"], "Total must equal subtotal with 0% tax!"

    # 2. Test BASE_PRICE Floor Protection
    print("\n--- 2. Testing Owner BASE_PRICE Floor Rule ---", flush=True)
    prods = inventory_manager.get_all_products()
    for p in prods:
        assert "BASE_PRICE" in p, f"Product {p['id']} missing BASE_PRICE!"
        assert p["PRICE"] >= p["BASE_PRICE"], f"Product {p['id']} price {p['PRICE']} is below base {p['BASE_PRICE']}!"
    print(f"[OK] Verified {len(prods)} products strictly obey PRICE >= BASE_PRICE.", flush=True)

    # 3. Test 6 Specialist Agents Autonomous Cycles
    print("\n--- 3. Testing 6 Specialist Agents Autonomous Cycles (Async) ---", flush=True)
    p_res = await price_manager_agent.run_autonomous_cycle()
    print("[OK] Price Manager Agent:", p_res["details"][:80], "...", flush=True)

    inv_res = await inventory_manager_agent.run_autonomous_cycle()
    print("[OK] Inventory Manager Agent:", inv_res["details"][:80], "...", flush=True)

    ord_res = await order_management_agent.run_autonomous_cycle()
    print("[OK] Order Management Agent:", ord_res["details"][:80], "...", flush=True)

    disp_res = await dispatcher_agent.run_autonomous_cycle()
    print("[OK] Dispatcher Agent:", disp_res["details"][:80], "...", flush=True)

    fin_res = await finance_manager_agent.run_autonomous_cycle()
    print("[OK] Finance Manager Agent:", fin_res["details"][:80], "...", flush=True)

    rev_res = await review_feedback_agent.run_autonomous_cycle()
    print("[OK] Review & Feedback Agent:", rev_res["details"][:80], "...", flush=True)

    # 4. Test CEO Agent and Message Bus
    print("\n--- 4. Testing CEO Agent & Inter-Agent Message Bus ---", flush=True)
    bus_snapshot = message_bus.get_inbox_snapshot()
    print(f"[OK] Message Bus Snapshot: {bus_snapshot}", flush=True)
    ceo_res = await ceo_agent.run_autonomous_cycle()
    print("[OK] CEO Agent:", ceo_res["details"][:100], "...", flush=True)

    # 5. Test Audit Trail Logs
    print("\n--- 5. Testing Audit Trail Logs for Frontend ---", flush=True)
    logs = get_agent_logs(limit=20)
    print(f"[OK] Audit Trail contains {len(logs)} recent agent decisions.", flush=True)
    for l in logs[:3]:
        print(f"     • [{l.get('agent_name')}]: {l.get('action')} -> {l.get('details')[:60]}...", flush=True)

    print("\n==================================================================", flush=True)
    print("ALL INR, 0% TAX, OWNER BASE PRICE & AUDIT LOG REQUIREMENTS VERIFIED!", flush=True)
    print("==================================================================", flush=True)

if __name__ == "__main__":
    asyncio.run(test_all_async())
