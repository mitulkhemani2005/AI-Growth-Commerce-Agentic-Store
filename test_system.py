import os
import sys
import json
import asyncio

# Ensure UTF-8 stdout
sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.inventory_manager import inventory_manager
from backend.cart_manager import cart_manager
from backend.order_manager import order_manager
from backend.agent import commerce_agent
from backend.payment_manager import payment_manager
from backend.review_manager import review_manager

async def run_tests():
    print(">>> 1. Testing Inventory Search & Schema Validation...")
    products = inventory_manager.get_all_products()
    assert len(products) > 0, "Inventory is empty!"
    for p in products:
        assert "PRODUCT_NAME" in p, f"Missing PRODUCT_NAME in {p}"
        assert "PRODUCT_TYPE" in p, f"Missing PRODUCT_TYPE in {p}"
        assert "PRODUCT_SIZE" in p, f"Missing PRODUCT_SIZE in {p}"
        assert "STOCK_REMAINING" in p, f"Missing STOCK_REMAINING in {p}"
    print(f"  [PASS] Verified {len(products)} products adhere to required schema.")

    print("\n>>> 2. Testing Multi-Product & Category Search...")
    search_res = inventory_manager.search_products(product_types=["Footwear", "Outerwear"])
    assert len(search_res) >= 2, f"Expected at least 2 items, got {len(search_res)}"
    print(f"  [PASS] Found {len(search_res)} items matching Footwear + Outerwear.")

    print("\n>>> 3. Testing Cart Management...")
    user_id = "user_test"
    cart_manager.clear_cart(user_id)
    # Add product
    add_res = cart_manager.add_to_cart(user_id, "prod_001", quantity=2, size="US 10")
    assert add_res["success"], f"Failed to add to cart: {add_res}"
    cart = cart_manager.get_cart(user_id)
    assert cart["item_count"] == 2, f"Expected 2 items in cart, got {cart['item_count']}"
    print(f"  [PASS] Added item to cart. Cart subtotal: ${cart['subtotal']}")

    # Remove 1 quantity
    rem_res = cart_manager.remove_from_cart(user_id, "prod_001", quantity=1)
    assert rem_res["success"], f"Failed to remove: {rem_res}"
    cart = cart_manager.get_cart(user_id)
    assert cart["item_count"] == 1, f"Expected 1 item, got {cart['item_count']}"
    print(f"  [PASS] Reduced cart quantity to 1.")

    print("\n>>> 4. Testing Order Confirmation & Real-Time Inventory Reduction...")
    # Check initial stock
    initial_prod = inventory_manager.get_product_by_id("prod_001")
    initial_stock = initial_prod["STOCK_REMAINING"]

    # Place order
    order_res = order_manager.create_order_from_cart(
        user_id=user_id,
        shipping_address="123 Test Street, Silicon Valley, CA",
        payment_method="Razorpay Gateway (Online)"
    )
    assert order_res["success"], f"Order placement failed: {order_res}"
    order = order_res["order"]
    print(f"  [PASS] Order {order['order_id']} placed successfully! Total: ${order['total']}")

    # Verify inventory reduction in inventory.json
    updated_prod = inventory_manager.get_product_by_id("prod_001")
    expected_stock = initial_stock - 1
    assert updated_prod["STOCK_REMAINING"] == expected_stock, f"Stock not reduced properly: Expected {expected_stock}, got {updated_prod['STOCK_REMAINING']}"
    print(f"  [PASS] Stock atomically reduced: {initial_stock} -> {updated_prod['STOCK_REMAINING']}")

    # Verify order appears in order history
    orders = order_manager.get_orders_by_user(user_id)
    assert any(o["order_id"] == order["order_id"] for o in orders), "Order not found in user order history!"
    print(f"  [PASS] Order confirmed in order history.")

    print("\n>>> 5. Testing Razorpay Payment Gateway Manager & Card Validation...")
    rzp_order = payment_manager.create_order(amount_in_usd_or_inr=150.0, receipt_id="rcpt_test_101", currency="INR")
    assert rzp_order["success"], "Failed to create Razorpay order!"
    assert rzp_order["amount"] == 15000, f"Expected 15000 paise, got {rzp_order['amount']}"
    assert "razorpay_order_id" in rzp_order, "Missing razorpay_order_id"
    # Test signature verification
    sig_valid = payment_manager.verify_payment_signature(
        razorpay_order_id=rzp_order["razorpay_order_id"],
        razorpay_payment_id="pay_test_9999",
        razorpay_signature="sandbox_verified"
    )
    assert sig_valid, "Razorpay signature verification returned False!"
    
    # Test Card Details Validation
    card_val = payment_manager.validate_card_details(
        card_number="4111 1111 1111 1111",
        expiry_date="12/30",
        cvv="123",
        cardholder_name="Alex Rivera"
    )
    assert card_val["valid"], f"Card validation failed: {card_val}"
    assert card_val["card_network"] == "Visa"
    assert card_val["card_last4"] == "1111"
    assert card_val["card_number_masked"] == "**** **** **** 1111"
    print(f"  [PASS] Razorpay Order created ({rzp_order['razorpay_order_id']}) and Card validated ({card_val['card_network']} {card_val['card_number_masked']}).")

    print("\n>>> 6. Testing Razorpay Card Payment Processing & Customer Schema Persistence...")
    cart_manager.clear_cart("user_alex")
    cart_manager.add_to_cart("user_alex", "prod_006", quantity=1) # SonicFlow Headphones $189.50
    card_pay_res = payment_manager.process_razorpay_card_payment(
        user_id="user_alex",
        card_number="4111 1111 1111 1111",
        expiry_date="12/30",
        cvv="123",
        cardholder_name="Alex Rivera"
    )
    assert card_pay_res["success"], f"Razorpay card payment failed: {card_pay_res}"
    assert "razorpay_order_id" in card_pay_res, "Missing razorpay_order_id"
    
    # Confirm order and save AP2 authorization token
    alex_order_res = order_manager.create_order_from_cart(
        user_id="user_alex",
        payment_method="Razorpay Gateway (Online)",
        payment_details={
            "razorpay_order_id": card_pay_res["razorpay_order_id"],
            "razorpay_payment_id": "pay_alex_verified_99",
            "verified": True
        }
    )
    assert alex_order_res["success"], "Failed to finalize Alex's order!"
    alex_created_order = alex_order_res["order"]
    
    payment_manager.save_ap2_token_from_payment(
        user_id="user_alex",
        razorpay_payment_id="pay_alex_verified_99",
        razorpay_order_id=card_pay_res["razorpay_order_id"],
        card_details=cart_manager.get_customer_payment_details("user_alex")
    )
    
    # Check that customer details schema in users.json is updated
    saved_card = cart_manager.get_customer_payment_details("user_alex")
    assert saved_card is not None, "Customer schema does not contain payment_details!"
    assert saved_card["card_holder_name"] == "Alex Rivera"
    assert saved_card["card_last4"] == "1111"
    assert saved_card["card_network"] == "Visa"
    print(f"  [PASS] Order #{alex_created_order['order_id']} placed via Razorpay (Order ID: {card_pay_res['razorpay_order_id']}).")
    print(f"  [PASS] Customer details schema saved: {saved_card}")

    print("\n>>> 7. Testing AI Agent Tool Execution with Groq LLM...")
    agent_output = await commerce_agent.run_prompt("Show me all Footwear in stock", user_id="user_alex")
    assert agent_output["response"], "Agent returned empty response!"
    print(f"  Agent response snippet: {agent_output['response'][:120]}...")
    print(f"  Tools called: {[t['name'] for t in agent_output.get('tool_calls', [])]}")
    assert len(agent_output.get("tool_calls", [])) > 0, "Agent did not execute any tools!"
    print("  [PASS] Groq LLM Agent executed tools and generated valid response.")

    print("\n>>> 8. Testing Agent Multi-Step Razorpay Card Authorization Workflow...")
    cart_manager.clear_cart("user_sarah")
    # Prompt with card details provided directly
    compound_output = await commerce_agent.run_prompt(
        "Find the Quantum Shield Parka, add 1 to my cart and pay with card 4111 1111 1111 1111, exp 12/30, cvv 123, Sarah Chen",
        user_id="user_sarah"
    )
    tools_used = [t["name"] for t in compound_output.get("tool_calls", [])]
    print(f"  Multi-step tools used: {tools_used}")
    assert any(t in ["process_razorpay_card_payment", "autonomous_agent_pay", "batch_add_to_cart", "add_to_cart"] for t in tools_used), "Agent failed to execute payment tools!"
    # Verify Sarah's customer schema in users.json
    sarah_card = cart_manager.get_customer_payment_details("user_sarah")
    assert sarah_card is not None, "Sarah's customer schema missing payment_details!"
    assert sarah_card["card_holder_name"] == "Sarah Chen"
    print(f"  [PASS] Customer schema updated for Sarah Chen with masked card: {sarah_card['card_number_masked']}.")

    print("\n>>> 9. Testing Razorpay Refund Engine & Inventory Restocking...")
    test_order_id = alex_created_order["order_id"]
    # Check current stock of SonicFlow Headphones (prod_006)
    headphone_before_refund = inventory_manager.get_product_by_id("prod_006")
    stock_before_refund = headphone_before_refund["STOCK_REMAINING"]

    refund_res = payment_manager.process_refund(order_id=test_order_id, reason="Customer Test Return")
    assert refund_res["success"], f"Refund failed: {refund_res}"
    assert refund_res["order"]["status"] == "Refunded", "Order status was not updated to Refunded!"
    assert "refund_id" in refund_res["refund_details"], "Missing refund_id in refund_details!"

    # Verify inventory was restocked
    headphone_after_refund = inventory_manager.get_product_by_id("prod_006")
    assert headphone_after_refund["STOCK_REMAINING"] == stock_before_refund + 1, f"Stock not restored: was {stock_before_refund}, now {headphone_after_refund['STOCK_REMAINING']}"
    print(f"  [PASS] Refund {refund_res['refund_details']['refund_id']} processed successfully via Razorpay.")
    print(f"  [PASS] Order #{test_order_id} marked as Refunded and stock restored: {stock_before_refund} -> {headphone_after_refund['STOCK_REMAINING']}.")

    print("\n>>> 10. Testing AI Agent Refund & Review Tools Automation with Groq LLM...")
    # Create an order to refund via agent
    cart_manager.clear_cart("user_alex")
    cart_manager.add_to_cart("user_alex", "prod_001", quantity=1)
    new_ord = order_manager.create_order_from_cart("user_alex", payment_method="Razorpay Gateway (Online)")
    
    agent_refund_res = await commerce_agent.run_prompt(
        f"Please refund my order {new_ord['order']['order_id']}",
        user_id="user_alex"
    )
    refund_tools = [t["name"] for t in agent_refund_res.get("tool_calls", [])]
    print(f"  Refund tools executed by agent: {refund_tools}")
    assert any(t in ["request_order_refund", "cancel_order"] for t in refund_tools), "Agent failed to execute refund/cancel tool!"
    # Verify order is refunded in orders.json
    refreshed_order = order_manager.get_order_by_id(new_ord['order']['order_id'])
    assert refreshed_order["status"] == "Refunded", "Order was not marked as Refunded!"
    print(f"  [PASS] Agent autonomously processed refund for order #{refreshed_order['order_id']} via Razorpay.")

    # Test Reviews Tool
    review_res = await commerce_agent.run_prompt("What are the customer reviews for SonicFlow Headphones?", user_id="user_alex")
    rev_tools = [t["name"] for t in review_res.get("tool_calls", [])]
    print(f"  Review tools executed: {rev_tools}")
    assert any(t in ["get_product_reviews", "get_product_details", "search_inventory"] for t in rev_tools), "Agent failed to query review tools!"
    print(f"  [PASS] Agent successfully executed review lookup tools.")

    print("\n==========================================================================")
    print("  ALL 10 TESTS PASSED! RAZORPAY PAYMENTS, REFUNDS, AGENT TOOLS & SCHEMA VERIFIED.")
    print("==========================================================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
