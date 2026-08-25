import asyncio
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

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
    get_agent_logs
)
from backend.agent import commerce_agent
from backend.background_workers import background_worker

async def test_human_like_collaboration():
    print("==================================================================", flush=True)
    print("TESTING HUMAN-LIKE MULTI-AGENT COLLABORATION & MODEL ASSIGNMENTS", flush=True)
    print("==================================================================", flush=True)

    # 1. Verify Model Configurations
    print("\n--- 1. Verifying Exact Model Assignments ---", flush=True)
    print(f"Price Manager Model:        {price_manager_agent.model}")
    print(f"Inventory Manager Model:    {inventory_manager_agent.model}")
    print(f"Order Management Model:     {order_management_agent.model}")
    print(f"Finance Manager Model:      {finance_manager_agent.model}")
    print(f"Dispatcher Model:           {dispatcher_agent.model}")
    print(f"Review & Feedback Model:    {review_feedback_agent.model}")
    print(f"CEO Agent Model:            {ceo_agent.model}")
    print(f"Owner Admin Chat Model:     {admin_chat_agent.model}")
    print(f"Customer AI Nova Model:     {commerce_agent.model}")

    assert price_manager_agent.model == "openai/gpt-oss-20b"
    assert inventory_manager_agent.model == "openai/gpt-oss-20b"
    assert order_management_agent.model == "openai/gpt-oss-20b"
    assert finance_manager_agent.model == "openai/gpt-oss-20b"
    assert dispatcher_agent.model == "openai/gpt-oss-20b"
    assert review_feedback_agent.model == "openai/gpt-oss-20b"
    assert ceo_agent.model == "qwen/qwen3.6-27b"
    assert admin_chat_agent.model == "qwen/qwen3.6-27b"
    assert commerce_agent.model == "qwen/qwen3.6-27b"
    print("[OK] Exact model rules verified: Specialists = gpt-oss-20b | CEO, Customer, Owner = qwen", flush=True)

    # 2. Verify Background Intervals
    print("\n--- 2. Verifying Schedule Intervals & Delays ---", flush=True)
    status = background_worker.get_status()
    for key, a in status["agents"].items():
        print(f"• {a['name']:<28} Interval: {a['human_interval']} ({a['interval_seconds']}s)")
        assert a["interval_seconds"] >= 10, f"Agent {key} interval too short!"
    print("[OK] Rate-limiting delays configured across all background agents.", flush=True)

    # 3. Simulate Human-Like Inter-Agent Conversation (Cycle 1: Finance Alerts CEO)
    print("\n--- 3. Cycle 1: Finance Manager Audits & Alerts CEO ---", flush=True)
    fin_res = await finance_manager_agent.run_autonomous_cycle()
    print("[Finance Manager]:", fin_res["details"], flush=True)
    
    inbox_ceo = message_bus.get_inbox("CEO Agent", mark_read=False)
    print(f"[OK] CEO Inbox contains {len(inbox_ceo)} message(s) from Finance Manager.", flush=True)
    assert any(m["subject"] == "FINANCE_ALERT" for m in inbox_ceo), "CEO should have received FINANCE_ALERT"

    # 4. Cycle 1 Continued: CEO Consumes Message, Issues Directive to Price Manager, and Replies to Finance Manager
    print("\n--- 4. CEO Strategic Response & Directives ---", flush=True)
    ceo_res = await ceo_agent.run_autonomous_cycle()
    print("[CEO Agent]:", ceo_res["details"][:150], "...", flush=True)

    inbox_fin = message_bus.get_inbox("Finance Manager Agent", mark_read=False)
    inbox_price = message_bus.get_inbox("Price Manager Agent", mark_read=False)
    print(f"[OK] Finance Manager Inbox received CEO reply: {[m['subject'] for m in inbox_fin]}", flush=True)
    print(f"[OK] Price Manager Inbox received CEO directive: {[m['subject'] for m in inbox_price]}", flush=True)
    assert any(m["subject"] == "CEO_FINANCE_ACKNOWLEDGE" for m in inbox_fin), "Finance should get CEO_FINANCE_ACKNOWLEDGE"
    assert any(m["subject"] == "CEO_PRICE_DIRECTIVE" for m in inbox_price), "Price Manager should get CEO_PRICE_DIRECTIVE"

    # 5. Cycle 2: Verify No Repetitive Message Flooding (Human-Like Stateful Deduplication)
    print("\n--- 5. Cycle 2: Verifying Deduplication (No Repetitive Flooding) ---", flush=True)
    # Finance Manager processes CEO acknowledgment
    fin_res_2 = await finance_manager_agent.run_autonomous_cycle()
    print("[Finance Manager (Cycle 2)]:", fin_res_2["details"], flush=True)
    
    # Check that Finance Manager did NOT send another FINANCE_ALERT to CEO because state hasn't changed
    inbox_ceo_2 = message_bus.get_inbox("CEO Agent", mark_read=False)
    print(f"[OK] CEO Inbox after Cycle 2 has {len(inbox_ceo_2)} messages (No duplicate alert spam).", flush=True)
    assert len(inbox_ceo_2) == 0, "Finance Manager should not spam duplicate alerts!"

    # 6. Price Manager Executes Dynamic Pricing Under CEO Directive
    print("\n--- 6. Price Manager Executes Under CEO Directive ---", flush=True)
    price_res = await price_manager_agent.run_autonomous_cycle()
    print("[Price Manager]:", price_res["details"], flush=True)

    # 7. Check Audit Trail and Message Bus History
    print("\n--- 7. Verifying Persistent Audit Trail & Message Bus ---", flush=True)
    all_msgs = message_bus.get_all_messages(limit=10)
    print(f"[OK] Message bus contains {len(all_msgs)} conversation items:")
    for m in all_msgs[:4]:
        print(f"     • {m['from']} ➔ {m['to']} [{m['subject']}]")

    logs = get_agent_logs(limit=10)
    print(f"[OK] Audit logs contain {len(logs)} recent actions.")

    print("\n==================================================================", flush=True)
    print("ALL HUMAN-LIKE MULTI-AGENT REQUIREMENTS & MODEL SPECS VERIFIED!", flush=True)
    print("==================================================================", flush=True)

if __name__ == "__main__":
    asyncio.run(test_human_like_collaboration())
