import asyncio
import json
import os
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional


from backend.inventory_manager import inventory_manager
from backend.cart_manager import cart_manager
from backend.order_manager import order_manager
from backend.review_manager import review_manager
from backend.treasury_manager import treasury_manager
from backend.admin_agents import message_bus, log_agent_action, conversation_history
from backend.agent_memory import memory_manager
from backend.agent_rl import rl_manager

BUYERS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "buyer_agents.json"))
USERS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "users.json"))
_lock = threading.RLock()


DEFAULT_BUYER_PERSONAS = [
    {
        "id": "buyer_alex",
        "name": "Alex Chen",
        "persona_title": "Flagship Tech Enthusiast",
        "avatar": "🚀",
        "description": "Obsessed with top-tier flagship smartphones, high-spec M3 laptops, and RTX gaming rigs.",
        "preferred_categories": ["Mobiles", "Laptops"],
        "price_sensitivity": "Low (Unlimited Budget)",
        "return_probability": 0.05,
        "review_sentiment": "Positive & Technical",
        "total_spent": 0.0,
        "orders_count": 0,
        "returns_count": 0,
        "reviews_written": 0,
        "status": "Active & Monitoring Catalog"
    },
    {
        "id": "buyer_sophia",
        "name": "Sophia Miller",
        "persona_title": "Smart Bargain Hunter",
        "avatar": "🎯",
        "description": "Seeks highest value-to-cost ratio, discounts, and well-priced budget flagship electronics and accessories.",
        "preferred_categories": ["Mobiles", "Accessories"],
        "price_sensitivity": "High (Values Good Deals)",
        "return_probability": 0.20,
        "review_sentiment": "Value & Quality Focused",
        "total_spent": 0.0,
        "orders_count": 0,
        "returns_count": 0,
        "reviews_written": 0,
        "status": "Active & Monitoring Catalog"
    },
    {
        "id": "buyer_david",
        "name": "David Patel",
        "persona_title": "Audiophile & Gadget Geek",
        "avatar": "🎧",
        "description": "Loves noise-cancelling headphones, high-fidelity wireless audio, smart wearables, and top-rated gear.",
        "preferred_categories": ["Audio", "Accessories"],
        "price_sensitivity": "Medium",
        "return_probability": 0.15,
        "review_sentiment": "Acoustic & Feature Detailed",
        "total_spent": 0.0,
        "orders_count": 0,
        "returns_count": 0,
        "reviews_written": 0,
        "status": "Active & Monitoring Catalog"
    },
    {
        "id": "buyer_elena",
        "name": "Elena Rostova",
        "persona_title": "Executive Luxury Shopper",
        "avatar": "💎",
        "description": "Purchases executive titanium laptops, foldables, and premium lifestyle devices with zero budget hesitation.",
        "preferred_categories": ["Laptops", "Mobiles", "Audio"],
        "price_sensitivity": "Zero (Unlimited Budget)",
        "return_probability": 0.08,
        "review_sentiment": "Sophisticated & Enthusiastic",
        "total_spent": 0.0,
        "orders_count": 0,
        "returns_count": 0,
        "reviews_written": 0,
        "status": "Active & Monitoring Catalog"
    },
    {
        "id": "buyer_marcus",
        "name": "Marcus Kim",
        "persona_title": "Trendsetter & Policy Tester",
        "avatar": "⚡",
        "description": "Fast-paced digital lifestyle adopter who buys trending gadgets and frequently tests seller 24-hour return policies.",
        "preferred_categories": ["Accessories", "Audio", "Mobiles"],
        "price_sensitivity": "Low",
        "return_probability": 0.30,
        "review_sentiment": "Expressive with Emojis",
        "total_spent": 0.0,
        "orders_count": 0,
        "returns_count": 0,
        "reviews_written": 0,
        "status": "Active & Monitoring Catalog"
    }
]


class BuyerAgentsFleet:
    """
    Autonomous Fleet of 5 AI Shopper Agents.
    They continuously evaluate the live catalog, make autonomous purchases when items are in stock,
    generate verified customer reviews, and test 24-hour return and refund policies.
    """
    def __init__(self, file_path: str = BUYERS_FILE):
        self.file_path = file_path
        self._ensure_files()

    def _ensure_files(self):
        with _lock:
            # 1. Initialize buyer personas
            if not os.path.exists(self.file_path):
                self._write_buyers(DEFAULT_BUYER_PERSONAS)

            # 2. Ensure all 5 buyers exist in users.json with pre-authorized AP2 tokens
            users = []
            if os.path.exists(USERS_FILE):
                try:
                    with open(USERS_FILE, "r", encoding="utf-8") as f:
                        users = json.load(f)
                except Exception:
                    users = []

            user_ids = {u.get("user_id") for u in users}
            updated = False

            for b in DEFAULT_BUYER_PERSONAS:
                if b["id"] not in user_ids:
                    users.append({
                        "user_id": b["id"],
                        "name": b["name"],
                        "email": f"{b['id']}@growthcommerce.ai",
                        "shipping_address": f"{b['name']} Residence, Innovation Hub Blvd, Sector 4",
                        "auto_pay_enabled": True,
                        "cart": [],
                        "payment_details": {
                            "card_holder_name": b["name"],
                            "card_number_masked": "4242 •••• •••• 4242",
                            "card_last4": "4242",
                            "card_network": "Visa Infinite (Unlimited)",
                            "expiry_date": "12/32"
                        },
                        "ap2_payment_token": {
                            "razorpay_payment_id": f"pay_ap2_{uuid.uuid4().hex[:10]}",
                            "razorpay_order_id": f"order_ap2_{uuid.uuid4().hex[:10]}",
                            "card_details": {
                                "card_holder_name": b["name"],
                                "card_number_masked": "4242 •••• •••• 4242",
                                "card_last4": "4242",
                                "card_network": "Visa Infinite",
                                "expiry_date": "12/32"
                            },
                            "authorized_at": datetime.now(timezone.utc).isoformat(),
                            "key_id": "rzp_test_TU4r5qh5d7sKDu",
                            "status": "authorized"
                        }
                    })
                    updated = True

            if updated:
                try:
                    with open(USERS_FILE, "w", encoding="utf-8") as f:
                        json.dump(users, f, indent=2)
                except Exception:
                    pass

    def _read_buyers(self) -> List[Dict[str, Any]]:
        with _lock:
            if not os.path.exists(self.file_path):
                self._ensure_files()
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return DEFAULT_BUYER_PERSONAS

    def _write_buyers(self, data: List[Dict[str, Any]]) -> None:
        with _lock:
            tmp_file = f"{self.file_path}.{os.getpid()}.{threading.get_ident()}.tmp"
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp_file, self.file_path)
            except Exception:
                if os.path.exists(tmp_file):
                    try:
                        os.remove(tmp_file)
                    except Exception:
                        pass
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

    def get_all_buyers(self) -> List[Dict[str, Any]]:
        return self._read_buyers()

    def get_buyer_by_id(self, buyer_id: str) -> Optional[Dict[str, Any]]:
        buyers = self._read_buyers()
        for b in buyers:
            if b["id"] == buyer_id:
                return b
        return None

    async def execute_buyer_step(self, buyer_id: str) -> Dict[str, Any]:
        """
        Executes one autonomous lifecycle step for a specific AI Buyer Agent:
        1. Evaluates catalog and checks in-stock products.
        2. Selects matching product according to persona affinity.
        3. Adds to cart and checks out via AP2 automated pay.
        4. Credits sales revenue to CEO Treasury Bank Balance!
        5. Posts verified review with authentic feedback.
        6. Evaluates return eligibility on past orders.
        """
        buyers = self._read_buyers()
        buyer = next((b for b in buyers if b["id"] == buyer_id), None)
        if not buyer:
            return {"success": False, "error": f"Buyer '{buyer_id}' not found."}

        products = inventory_manager.get_all_products()
        in_stock_products = [p for p in products if p.get("STOCK_REMAINING", 0) > 0]

        # If zero stock storewide, buyer waits for wholesale inventory acquisition (0-5m timer)
        if not in_stock_products:
            min_int = max(15, int(os.environ.get("BUYER_MIN_INTERVAL_SECONDS", "30")))
            max_int = max(min_int + 15, int(os.environ.get("BUYER_MAX_INTERVAL_SECONDS", "300")))
            next_delay = random.randint(min_int, min(max_int, 120))
            buyer["last_action_ts"] = time.time()
            buyer["next_purchase_ts"] = time.time() + next_delay
            buyer["next_delay_seconds"] = next_delay
            buyer["status"] = f"Waiting for stock (Next check in ~{next_delay}s)"
            self._write_buyers(buyers)
            return {
                "success": True,
                "buyer_id": buyer_id,
                "buyer_name": buyer["name"],
                "action": "WAIT_FOR_STOCK",
                "next_delay_seconds": next_delay,
                "details": f"{buyer['name']} browsed the store, but all products have 0 stock. Awaiting wholesale inventory replenishment (Next check in ~{next_delay}s)."
            }

        # Check if buyer wants to test a return on an eligible recent order first
        recent_orders = order_manager.get_orders_by_user(buyer_id)
        eligible_return_orders = [
            o for o in recent_orders
            if o.get("status") in ["Confirmed", "Pending", "Cancelled"] and not o.get("refund_details")
        ]

        if eligible_return_orders and random.random() < buyer.get("return_probability", 0.15):
            target_order = eligible_return_orders[0]
            ord_id = target_order["order_id"]
            reason = random.choice([
                "Testing 24h cancellation SLA",
                "Changed mind on color/spec",
                "Found alternative model",
                "Impulse buy evaluation"
            ])
            eval_res = order_manager.evaluate_24h_cancellation_and_refund(ord_id, reason=reason)
            if eval_res.get("approved"):
                # Deduct refund from treasury & restore stock
                refund_amount = float(target_order.get("total", 0.0))
                treasury_manager.deduct_refund(refund_amount, ord_id, reason=reason, actor=f"AI Buyer ({buyer['name']})")
                min_int = max(15, int(os.environ.get("BUYER_MIN_INTERVAL_SECONDS", "30")))
                max_int = max(min_int + 15, int(os.environ.get("BUYER_MAX_INTERVAL_SECONDS", "300")))
                next_delay = random.randint(min_int, max_int)
                buyer["last_action_ts"] = time.time()
                buyer["next_purchase_ts"] = time.time() + next_delay
                buyer["next_delay_seconds"] = next_delay
                buyer["returns_count"] = buyer.get("returns_count", 0) + 1
                buyer["status"] = f"Returned #{ord_id} (Next action in ~{next_delay}s)"
                self._write_buyers(buyers)

                msg = f"🔄 AI Buyer {buyer['name']} ({buyer['persona_title']}) auto-requested return for #{ord_id}: {eval_res.get('message')}. Refund of ₹{refund_amount:,.2f} deducted from CEO Treasury and items restocked."
                log_agent_action(f"AI Buyer ({buyer['name']})", "24h Return Initiated", msg, [ord_id], autonomous=True)
                return {
                    "success": True,
                    "buyer_id": buyer_id,
                    "buyer_name": buyer["name"],
                    "action": "RETURN_REQUESTED",
                    "order_id": ord_id,
                    "refund_amount": refund_amount,
                    "next_delay_seconds": next_delay,
                    "details": msg
                }


        # Select product based on preferred category affinity
        preferred = [p for p in in_stock_products if p.get("PRODUCT_TYPE") in buyer.get("preferred_categories", [])]
        candidate_pool = preferred if preferred else in_stock_products
        selected_product = random.choice(candidate_pool)

        # Clear any stale cart and add item
        cart_manager.clear_cart(buyer_id)
        qty = 1 if buyer_id != "buyer_elena" else random.choice([1, 2])
        add_res = cart_manager.add_to_cart(
            user_id=buyer_id,
            product_identifier=selected_product["id"],
            quantity=qty,
            size=selected_product.get("PRODUCT_SIZE", "Standard")
        )
        if not add_res.get("success"):
            return {"success": False, "error": f"Failed to add to cart: {add_res.get('error')}"}

        # Obtain cart state
        cart = cart_manager.get_cart(buyer_id)
        order_total = float(cart.get("estimated_total", 0.0))

        # 3. Execute Authentic AP2 Protocol Payment with Razorpay Gateway
        from backend.payment_manager import payment_manager
        ap2_res = payment_manager.execute_ap2_agent_payment(
            user_id=buyer_id,
            amount=order_total,
            cart=cart,
            authorized_agent=f"buyer_agent_{buyer_id.replace('buyer_', '')}",
            receipt_id=f"ap2_{buyer_id}_{uuid.uuid4().hex[:8]}"
        )
        if not ap2_res.get("success"):
            return {"success": False, "error": f"AP2 payment execution failed: {ap2_res.get('error')}"}

        # Place Order via AP2 Autonomous Pay with verified Razorpay details
        order_res = order_manager.create_order_from_cart(
            user_id=buyer_id,
            shipping_address=f"{buyer['name']} Executive Suite, Floor 14, Tower Tech",
            payment_method="Razorpay Gateway (AP2 Autonomous Pay)",
            payment_details=ap2_res.get("payment_details", {}),
            initial_status="Confirmed"
        )
        if not order_res.get("success"):
            return {"success": False, "error": f"Order placement failed: {order_res.get('error')}"}

        order_data = order_res.get("order", {})
        order_id = order_data.get("order_id")

        # Deposit sales revenue into CEO Bank Balance!
        treasury_manager.deposit_sales(
            amount=order_total,
            order_id=order_id,
            items_summary=f"{qty}x '{selected_product['PRODUCT_NAME']}'",
            customer=buyer["name"]
        )

        # Update Buyer Statistics
        buyer["orders_count"] = buyer.get("orders_count", 0) + 1
        buyer["total_spent"] = round(float(buyer.get("total_spent", 0.0)) + order_total, 2)
        buyer["status"] = f"Purchased #{order_id} (₹{order_total:,.2f})"

        # Write customer review
        review_text, rating = self._generate_persona_review(buyer, selected_product)
        review_manager.add_review(
            product_id=selected_product["id"],
            customer_name=buyer["name"],
            rating=rating,
            review_text=review_text,
            product_name=selected_product["PRODUCT_NAME"]
        )
        buyer["reviews_written"] = buyer.get("reviews_written", 0) + 1

        # Schedule next random purchase strictly within 5 minutes (30s - 300s)
        min_int = max(15, int(os.environ.get("BUYER_MIN_INTERVAL_SECONDS", "30")))
        max_int = max(min_int + 15, int(os.environ.get("BUYER_MAX_INTERVAL_SECONDS", "300")))
        next_delay = random.randint(min_int, max_int)
        buyer["last_action_ts"] = time.time()
        buyer["next_purchase_ts"] = time.time() + next_delay
        buyer["next_delay_seconds"] = next_delay
        buyer["status"] = f"Browsing catalog (Next order in ~{next_delay}s)"

        self._write_buyers(buyers)

        # Audit Log
        details = (
            f"🛍️ AI Buyer {buyer['name']} ({buyer['persona_title']}) purchased {qty}x '{selected_product['PRODUCT_NAME']}' "
            f"for ₹{order_total:,.2f} via AP2 + Razorpay Gateway (Order #{order_id}, Payment #{ap2_res.get('razorpay_payment_id')}). Revenue deposited into CEO Treasury! Rated {rating}★."
        )
        log_agent_action(f"AI Buyer ({buyer['name']})", "Autonomous AP2 Purchase", details, [selected_product['id'], order_id], autonomous=True)

        # Reinforcement Learning Step & Hybrid Memory Update for AI Buyer
        reward = rl_manager.compute_buyer_reward(buyer_id, {"action": "BUY"})
        rl_manager.record_step(
            buyer_id,
            {"buyer": buyer_id, "category": selected_product.get("CATEGORY", "General")},
            "BUY",
            reward,
            {"orders_count": buyer.get("orders_count", 0)}
        )
        memory_manager.record_episode(
            buyer_id,
            action="purchase_and_review",
            outcome=f"Bought {selected_product['PRODUCT_NAME']} (₹{order_total:.2f}) and left {rating}★ review.",
            reward=reward,
            metadata={"product_id": selected_product["id"], "order_id": order_id, "rating": rating}
        )
        memory_manager.update_structured(buyer_id, "total_spent", buyer.get("total_spent", 0.0))
        memory_manager.update_structured(buyer_id, "orders_count", buyer.get("orders_count", 0))

        return {
            "success": True,
            "buyer_id": buyer_id,
            "buyer_name": buyer["name"],
            "action": "PURCHASE_COMPLETED",
            "order_id": order_id,
            "product_name": selected_product["PRODUCT_NAME"],
            "total_spent": order_total,
            "rating": rating,
            "review": review_text,
            "rl_reward": reward,
            "next_delay_seconds": next_delay,
            "details": details
        }

    def _generate_persona_review(self, buyer: Dict[str, Any], product: Dict[str, Any]) -> tuple:
        """Generates realistic persona-specific customer review."""
        b_id = buyer.get("id")
        p_name = product.get("PRODUCT_NAME", "Product")

        if b_id == "buyer_alex":
            rating = random.choice([5, 5, 4])
            text = random.choice([
                f"Incredible build quality and thermal management on the {p_name}. Zero throttling under load. 10/10 recommendation!",
                f"The display and processing velocity on {p_name} exceed expectations. Apex engineering.",
                f"Phenomenal daily driver. Hardware architecture on the {p_name} is top tier."
            ])
        elif b_id == "buyer_sophia":
            rating = random.choice([5, 4, 4])
            text = random.choice([
                f"Superb value for money! For the price paid, {p_name} punches way above its weight.",
                f"Very solid purchase. Price-to-performance ratio on {p_name} is unbeatable right now.",
                f"High quality materials without the crazy markup. Happy with this deal!"
            ])
        elif b_id == "buyer_david":
            rating = random.choice([5, 5, 4])
            text = random.choice([
                f"Soundstage and acoustic clarity on the {p_name} are pristine. Deep lows and crisp highs.",
                f"Pairs instantly, low latency, and superb ergonomics. {p_name} is a winner for audio buffs.",
                f"Battery longevity and audio frequency response are outstanding on {p_name}."
            ])
        elif b_id == "buyer_elena":
            rating = 5
            text = random.choice([
                f"Absolute executive luxury. The finish and craftsmanship of {p_name} are second to none.",
                f"Unrivaled sophistication and performance. {p_name} is pure perfection.",
                f"Extremely impressed with the premium packaging and flawless performance of {p_name}."
            ])
        else:  # Marcus
            rating = random.choice([5, 4, 5])
            text = random.choice([
                f"Super sleek and trendy! 🔥 {p_name} arrived ultra-fast. Loving the aesthetic.",
                f"Vibe check passed! ⚡ {p_name} looks fire in person. Recommended!",
                f"Top tier accessory for my setup. 🚀 {p_name} is modern, light, and durable."
            ])

        return text, rating

    async def check_due_buyers(self) -> List[Dict[str, Any]]:
        """
        Periodically invoked by the 24/7 background worker:
        Evaluates each buyer's independent randomized countdown timer (staggered 30s to 5 minutes).
        Executes at most 1 buyer per tick to prevent simultaneous burst buying.
        """
        buyers = self._read_buyers()
        now_ts = time.time()
        results = []
        executed_any = False

        min_int = max(15, int(os.environ.get("BUYER_MIN_INTERVAL_SECONDS", "30")))
        max_int = max(min_int + 15, int(os.environ.get("BUYER_MAX_INTERVAL_SECONDS", "300")))

        # Stagger initialization if missing
        for idx, b in enumerate(buyers):
            next_ts = float(b.get("next_purchase_ts") or 0.0)
            if next_ts == 0.0:
                # Stagger across 5 minutes: slot idx * 55s + random offset
                stagger_delay = int(idx * (max_int / max(len(buyers), 1)) + random.uniform(10, 40))
                b["next_purchase_ts"] = now_ts + stagger_delay
                b["next_delay_seconds"] = stagger_delay
                b["status"] = f"Browsing catalog (Next order in ~{stagger_delay}s)"
                self._write_buyers(buyers)

        for b in buyers:
            next_ts = float(b.get("next_purchase_ts") or 0.0)
            if now_ts >= next_ts:
                if not executed_any:
                    # Execute first due buyer
                    try:
                        res = await self.execute_buyer_step(b["id"])
                        results.append(res)
                        executed_any = True
                    except Exception as e:
                        results.append({"buyer_id": b["id"], "success": False, "error": str(e)})
                else:
                    # Stagger other coincidentally due buyers by +20-45s so they do not buy simultaneously
                    additional_delay = random.randint(20, 50)
                    b["next_purchase_ts"] = now_ts + additional_delay
                    b["next_delay_seconds"] = additional_delay
                    self._write_buyers(buyers)

        return results

    async def run_all_buyers_step(self) -> Dict[str, Any]:
        """Manually triggers one autonomous action step across all 5 AI buyers sequentially."""
        buyers = self._read_buyers()
        results = []
        for b in buyers:
            try:
                res = await self.execute_buyer_step(b["id"])
                results.append(res)
                # Small pause to avoid exact timestamp collision
                await asyncio.sleep(0.5)
            except Exception as e:
                results.append({"buyer_id": b["id"], "success": False, "error": str(e)})
        return {"success": True, "results": results, "buyers_count": len(results)}

    def reset_buyers(self) -> Dict[str, Any]:
        """Resets all 5 buyers stats and establishes staggered 0-5 minute purchase schedules."""
        with _lock:
            buyers = self._read_buyers()
            now_ts = time.time()
            max_window = max(60, int(os.environ.get("BUYER_MAX_INTERVAL_SECONDS", "300")))
            slot_size = max_window / max(len(buyers), 1)

            for idx, b in enumerate(buyers):
                b["total_spent"] = 0.0
                b["orders_count"] = 0
                b["returns_count"] = 0
                b["reviews_written"] = 0
                # Staggered countdowns across 5 minutes
                delay = int(idx * slot_size + random.randint(10, int(slot_size * 0.75)))
                delay = max(15, min(delay, max_window))
                b["next_purchase_ts"] = now_ts + delay
                b["next_delay_seconds"] = delay
                b["last_action_ts"] = 0.0
                b["status"] = f"Browsing catalog (Next order in ~{delay}s)"

            self._write_buyers(buyers)
            return {"success": True, "message": "All 5 AI buyers reset with staggered 0-5 min purchase countdowns."}


buyer_agents_fleet = BuyerAgentsFleet()

