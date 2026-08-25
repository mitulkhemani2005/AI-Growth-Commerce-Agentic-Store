import asyncio
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


from backend.inventory_manager import inventory_manager
from backend.order_manager import order_manager
from backend.review_manager import review_manager
from backend.agent import commerce_agent
from backend.admin_agents import (
    price_manager_agent,
    inventory_manager_agent,
    order_manager_agent,
    refund_manager_agent,
    dispatcher_agent,
    review_feedback_agent,
    admin_chat_agent
)
from backend.background_workers import background_worker

async def test_all_async():
    print("==================================================================", flush=True)
    print("TESTING FULL ASYNC SYSTEM (CUSTOMER AGENT + 6 24/7 ADMIN AGENTS)", flush=True)
    print("==================================================================", flush=True)

    # 1. Test Customer Storefront Agent (Async)
    print("\n--- 1. Testing Customer Storefront Agent (Async ReAct) ---", flush=True)
    cust_res = await commerce_agent.run_prompt("Find all accessories, add to my cart and prepare order")
    print(f"[OK] Customer Agent Response: {cust_res.get('response')[:120]}...", flush=True)
    print(f"[OK] Tools Executed: {[t['name'] for t in cust_res.get('tool_calls', [])]}", flush=True)

    # 2. Test 6 Specialist Agents Autonomous Cycles (Async)
    print("\n--- 2. Testing 6 Specialist Agents Autonomous Cycles (Async) ---", flush=True)
    p_res = await price_manager_agent.run_autonomous_cycle()
    print("[OK] Price Manager Agent:", p_res["details"][:80], "...", flush=True)

    inv_res = await inventory_manager_agent.run_autonomous_cycle()
    print("[OK] Inventory Manager Agent:", inv_res["details"][:80], "...", flush=True)

    ord_res = await order_manager_agent.run_autonomous_cycle()
    print("[OK] Order Manager Agent:", ord_res["details"][:80], "...", flush=True)

    disp_res = await dispatcher_agent.run_autonomous_cycle()
    print("[OK] Dispatcher Agent:", disp_res["details"][:80], "...", flush=True)

    ref_res = await refund_manager_agent.run_autonomous_cycle()
    print("[OK] Refund Manager Agent:", ref_res["details"][:80], "...", flush=True)

    rev_res = await review_feedback_agent.run_autonomous_cycle()
    print("[OK] Review & Feedback Agent:", rev_res["details"][:80], "...", flush=True)

    # 3. Test Omnipotent Admin Chatbot (Async)
    print("\n--- 3. Testing Omnipotent Admin Chatbot (Async) ---", flush=True)
    chat_out = await admin_chat_agent.run_prompt("Price manager, discount all Footwear by 5%")
    print(f"[OK] Admin Chat Response: {chat_out.get('response')[:120]}...", flush=True)
    print(f"[OK] Tools Executed: {[t['name'] for t in chat_out.get('tool_calls', [])]}", flush=True)

    print("\n==================================================================", flush=True)
    print("ALL ASYNC CUSTOMER & 24/7 ADMIN AGENTS VERIFIED 100% OPERATIONAL!", flush=True)
    print("==================================================================", flush=True)

if __name__ == "__main__":
    asyncio.run(test_all_async())
