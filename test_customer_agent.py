from dotenv import load_dotenv
load_dotenv()

import sys
import asyncio
import os
sys.stdout.reconfigure(encoding='utf-8')
from backend.agent import commerce_agent
from backend.cart_manager import cart_manager

async def run_customer_agent_tests():
    print("=" * 65)
    print("TESTING DEDICATED CUSTOMER AI AGENT (Groq Key & Full Tool Suite)")
    print("=" * 65)

    user_id = "user_alex"
    # Ensure fresh cart
    cart_manager.clear_cart(user_id)

    # 1. Test Product Search
    print("\n--- 1. Testing Product Discovery ---", flush=True)
    res1 = await commerce_agent.run_prompt("Show me all running shoes and footwear in stock", user_id=user_id)
    print("Response:\n", res1["response"][:180], "...", flush=True)
    tools1 = [t["name"] for t in res1["tool_calls"]]
    print("Tools Executed:", tools1, flush=True)
    assert "search_inventory" in tools1, "search_inventory tool was not called!"

    # 2. Test In-Depth Product Explanation
    print("\n--- 2. Testing In-Depth Product Explanation ---", flush=True)
    res2 = await commerce_agent.run_prompt("Explain the features, materials, sizing and reviews of the CyberFlex Apex Runner in detail", user_id=user_id)
    print("Response:\n", res2["response"][:250], "...", flush=True)
    tools2 = [t["name"] for t in res2["tool_calls"]]
    print("Tools Executed:", tools2, flush=True)
    assert any(t in tools2 for t in ["get_product_details", "search_inventory", "get_product_reviews"]), "Product detail/review tools were not called!"

    # 3. Test Cart Addition
    print("\n--- 3. Testing Adding Products to Cart ---", flush=True)
    res3 = await commerce_agent.run_prompt("Add 1 CyberFlex Apex Runner size US 10 to my cart", user_id=user_id)
    print("Response:\n", res3["response"][:180], "...", flush=True)
    tools3 = [t["name"] for t in res3["tool_calls"]]
    print("Tools Executed:", tools3, flush=True)
    assert any(t in tools3 for t in ["add_to_cart", "batch_add_to_cart"]), "Add to cart tool was not called!"

    # 4. Test Trigger Razorpay Checkout Popup
    print("\n--- 4. Testing Trigger Razorpay Checkout Popup ---", flush=True)
    res4 = await commerce_agent.run_prompt("I want to checkout my cart with Razorpay popup now", user_id=user_id)
    print("Response:\n", res4["response"][:180], "...", flush=True)
    tools4 = [t["name"] for t in res4["tool_calls"]]
    print("Tools Executed:", tools4, flush=True)
    assert "trigger_razorpay_checkout" in tools4 or res4.get("checkout_payload") is not None, "Razorpay checkout trigger was not called!"

    # 5. Test Customer Reviews Lookup
    print("\n--- 5. Testing Reviews Lookup ---", flush=True)
    res5 = await commerce_agent.run_prompt("What are the customer reviews for SonicFlow ANC Pro Headphones?", user_id=user_id)
    print("Response:\n", res5["response"][:180], "...", flush=True)
    tools5 = [t["name"] for t in res5["tool_calls"]]
    print("Tools Executed:", tools5, flush=True)
    assert "get_product_reviews" in tools5 or "get_product_details" in tools5, "Reviews tool was not called!"

    # 6. Test Order Tracking
    print("\n--- 6. Testing Order Tracking ---", flush=True)
    res6 = await commerce_agent.run_prompt("Where is my order and what is the tracking number?", user_id=user_id)
    print("Response:\n", res6["response"][:180], "...", flush=True)
    tools6 = [t["name"] for t in res6["tool_calls"]]
    print("Tools Executed:", tools6, flush=True)
    assert "track_order" in tools6 or "view_order_history" in tools6, "Track order tool was not called!"

    print("\n" + "=" * 65, flush=True)
    print("ALL CUSTOMER AI AGENT VERIFICATION TESTS PASSED SUCCESSFULLY!", flush=True)
    print("=" * 65, flush=True)

if __name__ == "__main__":
    asyncio.run(run_customer_agent_tests())
