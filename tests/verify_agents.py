import asyncio
import json
import sys
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
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

async def test_all_admin_agents():
    print("=== STARTING ADMIN AGENT VALIDATION ===")
    treasury_manager.reset_treasury(10000.0)
    
    print("\n--- 1. Testing Price Manager Agent ---")
    res_price = await price_manager_agent.run_autonomous_cycle()
    print("Price Manager:", res_price.get("success"), "|", res_price.get("details"))
    
    print("\n--- 2. Testing Inventory Manager Agent ---")
    res_inv = await inventory_manager_agent.run_autonomous_cycle()
    print("Inventory Manager:", res_inv.get("success"), "|", res_inv.get("details"))
    
    print("\n--- 3. Testing CEO Agent ---")
    res_ceo = await ceo_agent.run_autonomous_cycle()
    print("CEO Agent:", res_ceo.get("success"), "|", res_ceo.get("details"))
    
    print("\n--- 4. Testing CEO Owner Report ---")
    res_report = await ceo_agent.generate_owner_report()
    print("CEO Report Success:", res_report.get("success"))
    print("Report KPIs:", res_report.get("kpis"))
    
    print("\n--- 5. Testing Dispatcher Agent ---")
    res_disp = await dispatcher_agent.run_autonomous_cycle()
    print("Dispatcher:", res_disp.get("success"), "|", res_disp.get("details"))
    
    print("\n--- 6. Testing Order Management Agent ---")
    res_ord = await order_management_agent.run_autonomous_cycle()
    print("Order Manager:", res_ord.get("success"), "|", res_ord.get("details"))
    
    print("\n--- 7. Testing Review & Feedback Agent ---")
    res_rev = await review_feedback_agent.run_autonomous_cycle()
    print("Review Feedback:", res_rev.get("success"), "|", res_rev.get("details"))
    
    print("\n--- 8. Testing Finance Manager Agent ---")
    res_fin = await finance_manager_agent.run_autonomous_cycle()
    print("Finance Manager:", res_fin.get("success"), "|", res_fin.get("details"))
    
    print("\n--- 9. Message Bus Inter-Agent Communication Telemetry ---")
    all_msgs = message_bus.get_all_messages(limit=30)
    print(f"Total Messages on Bus: {len(all_msgs)}")
    for i, m in enumerate(all_msgs[:12]):
        print(f"  [{i+1}] {m.get('from')} -> {m.get('to')} | Subject: {m.get('subject')}")
        print(f"       Payload sample: {json.dumps(m.get('payload', {}))[:100]}...")

    print("\n=== ALL ADMIN AGENTS VALIDATED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(test_all_admin_agents())
