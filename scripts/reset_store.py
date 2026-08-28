import os
import sys
import json
import random
import time
from datetime import datetime, timezone

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.inventory_manager import inventory_manager
from backend.treasury_manager import treasury_manager
from backend.salary_manager import salary_manager
from backend.buyer_agents import buyer_agents_fleet
from backend.order_manager import order_manager
from backend.review_manager import review_manager
from backend.cart_manager import cart_manager
from backend.admin_agents import message_bus, conversation_history, LOGS_FILE, _log_lock

def perform_complete_reset():
    print("=" * 60)
    print("🔄 PERFORMING COMPLETE STORE & MULTI-AGENT RESET")
    print("=" * 60)

    # 1. Reset Treasury to 1,000.0
    t_res = treasury_manager.reset_treasury(1000.0)
    print(f"✅ Treasury reset: Bank Balance = ₹{t_res.get('bank_balance', 1000.0):,.2f}")

    # 2. Reset Inventory to 0 stock
    products = inventory_manager.get_all_products()
    for p in products:
        p["STOCK_REMAINING"] = 0
        base_p = float(p.get("BASE_PRICE") or 10.0)
        p["PRICE"] = round(base_p * 1.25, 2)
    inventory_manager._write_inventory(products)
    print(f"✅ Inventory reset: {len(products)} products set to 0 STOCK (Wholesale restock required).")

    # 3. Reset Orders
    order_manager._write_orders([])
    print("✅ Orders reset: 0 orders in database.")

    # 4. Reset Reviews
    review_manager._write_reviews([])
    print("✅ Reviews reset: 0 reviews in database.")

    # 5. Reset Salaries
    s_res = salary_manager.reset_salaries()
    print("✅ Salaries reset: All staff agents reset to base ₹50/100 cycles.")

    # 6. Reset AI Buyers with staggered 5-min random scheduling
    b_res = buyer_agents_fleet.reset_buyers()
    buyers = buyer_agents_fleet.get_all_buyers()
    print(f"✅ AI Buyers reset: 5 shoppers staggered across 0–5 minutes:")
    for b in buyers:
        print(f"   - {b['name']} ({b['id']}): Next order in ~{b.get('next_delay_seconds')}s (status: {b['status']})")

    # 7. Clear Carts
    for b in buyers:
        cart_manager.clear_cart(b["id"])
    cart_manager.clear_cart("user_alex")
    print("✅ Shopping carts cleared.")

    # 8. Clear Message Bus, Conversations, and Audit Logs
    message_bus.clear_history()
    conversation_history.clear()
    with _log_lock:
        try:
            with open(LOGS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
        except Exception:
            pass
    print("✅ Inter-agent message bus, conversation history, and audit logs cleared.")
    print("=" * 60)
    print("🎉 FULL RESET COMPLETE: Ready for autonomous operation!")
    print("=" * 60)

if __name__ == "__main__":
    perform_complete_reset()
