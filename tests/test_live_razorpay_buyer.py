import pytest
import asyncio
import razorpay
from backend.buyer_agents import buyer_agents_fleet
from backend.inventory_manager import inventory_manager
from backend.payment_manager import payment_manager
from backend.order_manager import order_manager

@pytest.mark.asyncio
async def test_ai_buyer_real_razorpay_payment():
    # Ensure inventory has stock
    for p in inventory_manager.get_all_products():
        inventory_manager.update_stock(p["id"], 30)

    # Force buyer_alex to execute a purchase
    buyer = buyer_agents_fleet.get_buyer_by_id("buyer_alex")
    old_prob = buyer.get("return_probability", 0.05)
    buyer["return_probability"] = 0.0
    all_buyers = buyer_agents_fleet.get_all_buyers()
    buyer_agents_fleet._write_buyers([buyer if b["id"] == "buyer_alex" else b for b in all_buyers])

    try:
        res = await buyer_agents_fleet.execute_buyer_step("buyer_alex")
        assert res.get("success") is True, f"Buyer step failed: {res}"
        
        oid = res.get("order_id")
        assert oid is not None, "Order ID must be present"
        
        order = order_manager.get_order_by_id(oid)
        assert order is not None, "Order must exist in database"
        
        rzp_ord_id = order.get("razorpay_order_id")
        rzp_pay_id = order.get("razorpay_payment_id")
        
        assert rzp_ord_id is not None, "Razorpay Order ID must not be None"
        assert rzp_pay_id is not None, "Razorpay Payment ID must not be None"
        assert rzp_pay_id.startswith("pay_"), "Payment ID must start with pay_"
        
        # Verify directly on Razorpay's live server API
        client = razorpay.Client(auth=(payment_manager.key_id, payment_manager.key_secret))
        pay_info = client.payment.fetch(rzp_pay_id)
        
        assert pay_info.get("id") == rzp_pay_id
        assert pay_info.get("status") == "captured", f"Expected captured status on Razorpay, got {pay_info.get('status')}"
        assert pay_info.get("order_id") == rzp_ord_id
        
        # Verify Razorpay order status is paid
        ord_info = client.order.fetch(rzp_ord_id)
        assert ord_info.get("status") == "paid"
        assert ord_info.get("amount_paid") > 0
        
    finally:
        # Restore buyer probability
        buyer["return_probability"] = old_prob
        all_buyers = buyer_agents_fleet.get_all_buyers()
        buyer_agents_fleet._write_buyers([buyer if b["id"] == "buyer_alex" else b for b in all_buyers])
