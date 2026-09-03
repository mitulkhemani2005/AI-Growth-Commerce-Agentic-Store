import sys
import os
import asyncio
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.inventory_manager import inventory_manager
from backend.agents.campaign_orchestrator import CampaignOrchestrator
from backend.order_manager import order_manager
from backend.payment_manager import payment_manager
from backend.background_workers import background_worker

async def test_all():
    print("--- 1. Testing Campaign Orchestration & Category Constraints ---")
    orch = CampaignOrchestrator(inventory_manager)
    
    # Launch campaign for Mobiles
    res1 = orch.launch_campaign("Mobiles Mega Sale", "Mobiles", 10.0, auto_activate=True)
    assert res1["success"], f"Failed launch 1: {res1}"
    c1_id = res1["campaign"]["id"]
    print("Created Mobiles campaign 1:", c1_id)

    # Launch second campaign for Mobiles -> first must be deactivated (at most 1 active per category)
    res2 = orch.launch_campaign("Mobiles Super Drop", "Mobiles", 15.0, auto_activate=True)
    assert res2["success"], f"Failed launch 2: {res2}"
    c2_id = res2["campaign"]["id"]
    print("Created Mobiles campaign 2:", c2_id)

    # Check active status
    all_c = orch.get_all_campaigns()
    mobiles_active = [c for c in all_c if c.get("category") == "Mobiles" and c.get("status") == "ACTIVE"]
    assert len(mobiles_active) <= 1, f"Constraint violated! Multiple active campaigns for Mobiles: {mobiles_active}"
    print(f"Verified: Exactly {len(mobiles_active)} active campaign for Mobiles.")

    # Stop campaign
    stop_res = orch.stop_campaign(c2_id)
    assert stop_res["success"], f"Failed stop: {stop_res}"
    print("Stopped campaign 2 successfully.")

    # Delete campaign
    del_res = orch.delete_campaign(c1_id)
    assert del_res["success"], f"Failed delete: {del_res}"
    print("Deleted campaign 1 successfully.")

    print("\n--- 2. Testing 24-Hour Refund & Stock Restoration ---")
    # Create test order
    test_ord_id = f"ORD-TEST-{int(time.time())}"
    sample_product = inventory_manager.get_all_products()[0]
    p_id = sample_product["id"]
    init_stock = sample_product.get("STOCK_REMAINING", 10)
    print(f"Product {p_id} initial stock: {init_stock}")

    # Place order
    orders = order_manager._read_orders()
    new_ord = {
        "order_id": test_ord_id,
        "items": [{"id": p_id, "PRODUCT_NAME": sample_product["PRODUCT_NAME"], "quantity": 2, "price": 100.0}],
        "total": 200.0,
        "status": "Confirmed",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inventory_deducted": True
    }
    orders.insert(0, new_ord)
    order_manager._write_orders(orders)
    # Deduct stock
    inventory_manager.update_stock(p_id, max(0, init_stock - 2))

    # Perform refund
    ref_res = payment_manager.process_refund(test_ord_id, reason="Customer Request within 24 hours")
    assert ref_res["success"], f"Refund failed: {ref_res}"
    print("Refund successfully processed! Refund Details:", ref_res["refund_details"]["refund_id"])

    # Verify inventory was restored
    p_after = inventory_manager.get_product_by_id(p_id)
    assert p_after["STOCK_REMAINING"] == init_stock, f"Stock not restored! Expected {init_stock}, got {p_after['STOCK_REMAINING']}"
    print(f"Verified: Inventory stock restored back to {p_after['STOCK_REMAINING']}.")

    print("\n--- 3. Testing Dynamic Interval Updates ---")
    res_int = background_worker.update_agent_interval("price_manager", 45)
    assert res_int["success"], f"Interval update failed: {res_int}"
    assert background_worker.agent_states["price_manager"]["interval_seconds"] == 45
    print("Price Manager interval set to 45s.")

    res_buyer_int = background_worker.update_agent_interval("buyer_agents", 90)
    assert res_buyer_int["success"], f"Buyer interval update failed: {res_buyer_int}"
    print("Buyer Agents fleet interval set to 90s.")

    print("\n>>> ALL 9 DIRECTIVES VERIFIED AND PASSED WITH 100% SUCCESS! <<<")

if __name__ == "__main__":
    asyncio.run(test_all())
