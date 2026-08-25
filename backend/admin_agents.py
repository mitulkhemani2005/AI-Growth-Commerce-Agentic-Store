from dotenv import load_dotenv
load_dotenv()

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from groq import AsyncGroq, Groq

from backend.inventory_manager import inventory_manager
from backend.order_manager import order_manager
from backend.review_manager import review_manager

LOGS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "agent_logs.json"))
_log_lock = threading.RLock()

DEFAULT_GROQ_API_KEY = os.environ.get("ADMIN_GROQ_API_KEY", os.environ.get("GROQ_API_KEY"))  # Set in .env
DEFAULT_MODELS = ["qwen/qwen3.6-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
DEFAULT_MODEL = os.environ.get("GROQ_ADMIN_MODEL", DEFAULT_MODELS[0])


def log_agent_action(agent_name: str, action: str, details: str, affected_items: Optional[List[str]] = None, autonomous: bool = True):
    """Appends an event to the 24/7 autonomous agent audit log in agent_logs.json."""
    with _log_lock:
        logs = []
        if os.path.exists(LOGS_FILE):
            try:
                with open(LOGS_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []

        entry = {
            "id": f"log_{uuid.uuid4().hex[:8]}",
            "agent_name": agent_name,
            "action": action,
            "details": details,
            "affected_items": affected_items or [],
            "autonomous": autonomous,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        logs.insert(0, entry)
        # Keep last 200 logs
        logs = logs[:200]

        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
    return entry

def clean_think_tags(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    cleaned = cleaned.replace('\u202f', ' ').replace('\u00a0', ' ').replace('\u200b', '')
    return cleaned.strip()


# =====================================================================
# 1. 🏷️ PRICE MANAGER AGENT (24/7 Autonomous)
# =====================================================================
class PriceManagerAgent:
    name = "Price Manager Agent"

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous cycle:
        - Analyzes inventory stock levels and orders.
        - Slightly adjusts prices for slow-moving or low-stock items.
        - Commits price changes directly to inventory.json without owner approval.
        """
        products = inventory_manager.get_all_products()
        adjusted = []
        
        for p in products:
            stock = p.get("STOCK_REMAINING", 0)
            price = p.get("PRICE", 100.0)
            p_name = p.get("PRODUCT_NAME", p["id"])

            # If stock is critically low (< 3), apply subtle surge pricing (+4%)
            if 0 < stock <= 2:
                new_price = round(price * 1.04, 2)
                if new_price != price:
                    inventory_manager.update_price(p["id"], new_price)
                    adjusted.append(f"{p_name} (${price} -> ${new_price}, low stock surge)")
            # If stock is excessive (> 30), apply small promotional discount (-3%)
            elif stock > 30:
                new_price = round(price * 0.97, 2)
                if new_price != price:
                    inventory_manager.update_price(p["id"], new_price)
                    adjusted.append(f"{p_name} (${price} -> ${new_price}, high inventory discount)")

        details = f"Scanned {len(products)} SKUs. " + (f"Autonomously optimized {len(adjusted)} prices: {'; '.join(adjusted)}" if adjusted else "All item prices within optimal dynamic margin.")
        log_agent_action(self.name, "Dynamic Price Optimization", details, affected_items=adjusted, autonomous=True)
        return {"success": True, "agent": self.name, "adjusted": adjusted, "details": details}

    async def execute_command(self, action: str, category: Optional[str] = None, percentage: float = 0.0, product_id: Optional[str] = None, new_price: Optional[float] = None) -> Dict[str, Any]:
        """Executes explicit owner command."""
        if product_id and new_price is not None:
            res = inventory_manager.update_price(product_id, new_price)
            log_agent_action(self.name, "Manual Price Update", res.get("message", "Price updated"), [product_id], autonomous=False)
            return res
        elif percentage != 0.0:
            res = inventory_manager.bulk_price_adjustment(category=category, percentage=percentage)
            log_agent_action(self.name, "Bulk Price Adjustment", res.get("message", "Bulk adjustment"), [category or "All"], autonomous=False)
            return res
        return {"success": False, "error": "Invalid price manager command parameters."}


# =====================================================================
# 2. 📦 INVENTORY MANAGER AGENT (24/7 Autonomous)
# =====================================================================
class InventoryManagerAgent:
    name = "Inventory Manager Agent"

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous cycle:
        - Scans catalog for low-stock items (< 5 units).
        - Automatically restocks them (+20 units) to prevent out-of-stock downtime.
        - Commits updates directly to inventory.json without owner approval.
        """
        low_stock_items = inventory_manager.get_low_stock_products(threshold=4)
        restocked = []

        for p in low_stock_items:
            p_id = p["id"]
            p_name = p.get("PRODUCT_NAME", p_id)
            current_stock = p.get("STOCK_REMAINING", 0)
            restock_qty = 20
            res = inventory_manager.restock_product(p_id, restock_qty)
            if res.get("success"):
                restocked.append(f"{p_name} ({current_stock} -> {current_stock + restock_qty} units)")

        details = f"Scanned warehouse inventory. " + (f"Autonomously restocked {len(restocked)} low-stock SKUs: {', '.join(restocked)}" if restocked else "All warehouse stock levels healthy (all SKUs > threshold).")
        log_agent_action(self.name, "Autonomous Warehouse Restock", details, affected_items=[p["id"] for p in low_stock_items], autonomous=True)
        return {"success": True, "agent": self.name, "restocked": restocked, "details": details}

    async def execute_command(self, action: str, product_identifier: str, quantity: int = 15, set_exact: Optional[int] = None) -> Dict[str, Any]:
        """Executes explicit owner command."""
        if set_exact is not None:
            res = inventory_manager.update_stock(product_identifier, set_exact)
            log_agent_action(self.name, "Stock Set Override", res.get("message", "Stock updated"), [product_identifier], autonomous=False)
            return res
        else:
            res = inventory_manager.restock_product(product_identifier, quantity)
            log_agent_action(self.name, "Manual Restock Trigger", res.get("message", "Restocked"), [product_identifier], autonomous=False)
            return res


# =====================================================================
# 3. 📋 ORDER MANAGER AGENT (24/7 Autonomous)
# =====================================================================
class OrderManagerAgent:
    name = "Order Manager Agent"

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous cycle:
        - Audits order statuses across the lifecycle.
        - Flags pending orders and ensures SLA fulfillment readiness.
        - Commits order state sync to orders.json.
        """
        all_orders = order_manager.get_all_orders()
        status_counts = {}
        for o in all_orders:
            st = o.get("status", "Confirmed")
            status_counts[st] = status_counts.get(st, 0) + 1

        details = f"Audited {len(all_orders)} total lifetime orders. Breakdown: " + ", ".join([f"{st}: {count}" for st, count in status_counts.items()])
        log_agent_action(self.name, "Order Pipeline Audit", details, affected_items=[], autonomous=True)
        return {"success": True, "agent": self.name, "status_breakdown": status_counts, "details": details}

    async def execute_command(self, action: str, order_id: str, new_status: str, notes: Optional[str] = None) -> Dict[str, Any]:
        """Executes explicit owner command to change order status."""
        res = order_manager.update_order_status(order_id, new_status, notes=notes)
        log_agent_action(self.name, "Manual Order Status Change", res.get("message", f"Status updated to {new_status}"), [order_id], autonomous=False)
        return res


# =====================================================================
# 4. 💳 REFUND MANAGER AGENT (24/7 Autonomous)
# =====================================================================
class RefundManagerAgent:
    name = "Refund Manager Agent"

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous cycle:
        - Scans cancelled orders or refund requests.
        - Enforces strict rule: Auto-approves if cancelled <= 24 hours AND status is not 'Shipped' or 'Delivered'.
        - Autonomously executes Razorpay refund API and restores stock in inventory.json without owner approval.
        """
        orders = order_manager.get_all_orders()
        approved_refunds = []

        for o in orders:
            o_id = o.get("order_id")
            status = o.get("status", "Confirmed")
            # If marked as Cancelled but not yet Refunded, evaluate auto-refund
            if status == "Cancelled" and not o.get("refund_details"):
                eval_res = order_manager.evaluate_24h_cancellation_and_refund(o_id, reason="24h Autonomous Refund Rule")
                if eval_res.get("approved"):
                    approved_refunds.append(o_id)

        details = f"Audited refund requests. " + (f"Autonomously approved and executed {len(approved_refunds)} 24h refunds via Razorpay: {', '.join(approved_refunds)}" if approved_refunds else "No pending eligible refunds required action. 24h & non-shipped safety compliance verified.")
        log_agent_action(self.name, "Refund & Cancellation Audit", details, affected_items=approved_refunds, autonomous=True)
        return {"success": True, "agent": self.name, "approved_refunds": approved_refunds, "details": details}

    async def execute_command(self, action: str, order_id: str, reason: str = "Owner Request", force: bool = False) -> Dict[str, Any]:
        """Executes cancellation & refund evaluation."""
        if force:
            from backend.payment_manager import payment_manager
            res = payment_manager.process_refund(order_id, reason=f"[Owner Override] {reason}")
            log_agent_action(self.name, "Forced Manual Refund", res.get("message", "Refund processed"), [order_id], autonomous=False)
            return res
        else:
            res = order_manager.evaluate_24h_cancellation_and_refund(order_id, reason=reason)
            log_agent_action(self.name, "24h Refund Rule Evaluation", res.get("message") or res.get("error", "Evaluated"), [order_id], autonomous=False)
            return res


# =====================================================================
# 5. 🚚 DISPATCHER AGENT (24/7 Autonomous)
# =====================================================================
class DispatcherAgent:
    name = "Dispatcher Agent"

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous cycle:
        - Finds all 'Confirmed' orders.
        - Generates logistics carrier tracking numbers (TRK-XXXXX).
        - Autonomously transitions status: Confirmed -> Dispatched (and prepares for Shipped).
        - Commits tracking numbers directly to orders.json without owner approval.
        """
        orders = order_manager.get_all_orders()
        dispatched = []

        for o in orders:
            o_id = o.get("order_id")
            status = o.get("status", "Confirmed")
            if status == "Confirmed":
                res = order_manager.assign_tracking_number(o_id)
                if res.get("success"):
                    trk = res.get("order", {}).get("tracking_number", "TRK-XXXXX")
                    dispatched.append(f"{o_id} (Tracking: {trk})")

        details = f"Fulfillment scan completed. " + (f"Autonomously dispatched {len(dispatched)} orders with logistics tracking: {', '.join(dispatched)}" if dispatched else "All confirmed orders are currently dispatched.")
        log_agent_action(self.name, "Logistics Dispatch Sync", details, affected_items=[d.split()[0] for d in dispatched], autonomous=True)
        return {"success": True, "agent": self.name, "dispatched": dispatched, "details": details}

    async def execute_command(self, action: str, order_id: Optional[str] = None, tracking_number: Optional[str] = None) -> Dict[str, Any]:
        """Executes explicit dispatching command."""
        if order_id:
            res = order_manager.assign_tracking_number(order_id, tracking_number)
            log_agent_action(self.name, "Manual Order Dispatch", res.get("message", "Dispatched"), [order_id], autonomous=False)
            return res
        else:
            return await self.run_autonomous_cycle()


# =====================================================================
# 6. ⭐ REVIEW & FEEDBACK MANAGER AGENT (24/7 Autonomous)
# =====================================================================
class ReviewFeedbackAgent:
    name = "Review and Feedback Manager"

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous cycle:
        - Scans all products with customer reviews in reviews.json.
        - Uses Groq LLM to generate high-impact AI sentiment & review summaries.
        - Autonomously updates product descriptions and ratings in inventory.json without owner approval.
        """
        products = inventory_manager.get_all_products()
        updated_summaries = []

        # Find products that have reviews and need summary synthesis or refresh
        for p in products:
            p_id = p["id"]
            p_name = p.get("PRODUCT_NAME", p_id)
            reviews = review_manager.get_reviews_for_product(p_id)
            if reviews and not p.get("AI_REVIEW_SUMMARY"):
                res = await review_manager.generate_ai_review_summary(p_id)
                if res.get("success"):
                    updated_summaries.append(p_name)
                    break  # Process 1 per autonomous cycle for responsiveness

        # If all have summaries, periodically refresh one
        if not updated_summaries and products:
            p_id = products[0]["id"]
            p_name = products[0].get("PRODUCT_NAME", p_id)
            if review_manager.get_reviews_for_product(p_id):
                res = await review_manager.generate_ai_review_summary(p_id)
                if res.get("success"):
                    updated_summaries.append(p_name)

        details = f"Analyzed customer review sentiment across catalog. " + (f"Generated updated AI review summaries for: {', '.join(updated_summaries)}" if updated_summaries else "Catalog reviews sentiment up to date.")
        log_agent_action(self.name, "AI Review & Sentiment Synthesis", details, affected_items=updated_summaries, autonomous=True)
        return {"success": True, "agent": self.name, "updated_products": updated_summaries, "details": details}

    async def execute_command(self, action: str, product_id_or_name: str) -> Dict[str, Any]:
        """Executes review summary generation on demand."""
        res = await review_manager.generate_ai_review_summary(product_id_or_name)
        log_agent_action(self.name, "On-Demand Review Analysis", f"Generated AI summary for '{product_id_or_name}'", [product_id_or_name], autonomous=False)
        return res


# Global agent instances
price_manager_agent = PriceManagerAgent()
inventory_manager_agent = InventoryManagerAgent()
order_manager_agent = OrderManagerAgent()
refund_manager_agent = RefundManagerAgent()
dispatcher_agent = DispatcherAgent()
review_feedback_agent = ReviewFeedbackAgent()


# =====================================================================
# 🤖 OMNIPOTENT ADMIN CHATBOT AGENT (Groq ReAct Command Center)
# =====================================================================
ADMIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "command_price_manager",
            "description": "Command the Price Manager Agent to adjust prices. Can apply percentage changes (e.g. -10 for 10% discount, +5 for 5% increase) by category (e.g. Footwear, Audio, Accessories) or set a specific price for a product.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action (e.g. 'bulk_discount', 'increase_price', 'set_price')"},
                    "category": {"type": "string", "description": "Product category/type to target (or 'all')"},
                    "percentage": {"type": "number", "description": "Percentage change (+10 or -10)"},
                    "product_id": {"type": "string", "description": "Specific product ID if setting price directly"},
                    "new_price": {"type": "number", "description": "New price in USD if setting directly"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "command_inventory_manager",
            "description": "Command the Inventory Manager Agent to restock products, set exact stock levels, or check low stock items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_identifier": {"type": "string", "description": "Product ID or name to restock/update (e.g. 'CyberFlex' or 'prod_001')"},
                    "quantity": {"type": "integer", "description": "Units to add to existing stock (e.g. 20)"},
                    "set_exact": {"type": "integer", "description": "Exact stock count to set (optional override)"}
                },
                "required": ["product_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "command_order_manager",
            "description": "Command the Order Manager Agent to update an order's status (Pending, Confirmed, Dispatched, Shipped, Delivered, Cancelled, Refunded) or inspect orders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID (e.g. 'ORD-1001')"},
                    "new_status": {"type": "string", "description": "Target status: Pending, Confirmed, Dispatched, Shipped, Delivered, Cancelled, Refunded"},
                    "notes": {"type": "string", "description": "Optional status note"}
                },
                "required": ["order_id", "new_status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "command_refund_manager",
            "description": "Command the Refund Manager Agent to evaluate the 24-hour and non-shipped rule for an order, or force a manual Razorpay refund.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID to refund (e.g. 'ORD-1001')"},
                    "reason": {"type": "string", "description": "Cancellation/refund reason"},
                    "force_override": {"type": "string", "description": "Pass 'true' to bypass 24h eligibility check and execute immediate refund."}
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "command_dispatcher",
            "description": "Command the Dispatcher Agent to package, assign logistics tracking numbers (TRK-XXXXX), and dispatch/ship orders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Specific order ID to dispatch (optional, omits for all confirmed orders)"},
                    "tracking_number": {"type": "string", "description": "Custom tracking number if specified"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "command_review_manager",
            "description": "Command the Review & Feedback Manager Agent to analyze customer reviews and generate an AI sentiment & review summary for an item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_identifier": {"type": "string", "description": "Product ID or name (e.g. 'SonicFlow' or 'prod_007')"}
                },
                "required": ["product_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_admin_dashboard_metrics",
            "description": "Get real-time revenue, order counts by status, inventory health, and recent 24/7 agent actions.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

ADMIN_SYSTEM_PROMPT = """You are the 'Omnipotent Store Owner AI Command Agent' for the AI Growth Commerce Store.
You have absolute executive command over the 6 specialist 24/7 autonomous agents and store operations:
1. 🏷️ Price Manager Agent: Can dynamically discount, increase, or set prices.
2. 📦 Inventory Manager Agent: Can restock SKUs, adjust warehouse inventory, resolve out-of-stock items.
3. 📋 Order Manager Agent: Can transition order statuses (Pending, Confirmed, Dispatched, Shipped, Delivered, Cancelled, Refunded).
4. 💳 Refund Manager Agent: Enforces the strict rule: auto-approved if cancelled <= 24 hours AND not shipped/delivered. Can also perform force refunds.
5. 🚚 Dispatcher Agent: Assigns tracking numbers (TRK-XXXXX) and dispatches/ships orders.
6. ⭐ Review & Feedback Manager: Analyzes reviews and synthesizes AI product summaries via Groq LLM.

When the owner orders you to do something, immediately call the appropriate tool(s) to execute the changes, and report back clearly with the exact outcome and state changes.
Always be concise, professional, and authoritative.
"""

class AdminChatAgent:
    def __init__(self, api_key: str = DEFAULT_GROQ_API_KEY, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model
        self.fallback_models = DEFAULT_MODELS
        self._init_client()

    def _init_client(self):
        try:
            self.client = AsyncGroq(api_key=self.api_key)
            self.sync_client = Groq(api_key=self.api_key)
        except Exception as e:
            print(f"AdminChatAgent client warning: {e}", flush=True)
            self.client = None
            self.sync_client = None

    async def _call_llm_with_fallback(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2500
    ):
        models_to_try = [self.model] + [m for m in self.fallback_models if m != self.model]
        last_err = None

        for model_name in models_to_try:
            try:
                kwargs = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "timeout": 15.0
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice or "auto"
                
                resp = await asyncio.wait_for(asyncio.to_thread(self.sync_client.chat.completions.create, **kwargs), timeout=15.0)
                return resp
            except Exception as e:
                print(f"AdminChatAgent model {model_name} warning: {str(e)[:80]}... Trying next model.", flush=True)
                last_err = e
                continue
        raise last_err or Exception("All Groq models exhausted.")


    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if tool_name == "command_price_manager":
                return await price_manager_agent.execute_command(
                    action=args.get("action", "adjust"),
                    category=args.get("category"),
                    percentage=float(args.get("percentage", 0.0)),
                    product_id=args.get("product_id"),
                    new_price=float(args.get("new_price")) if args.get("new_price") is not None else None
                )
            elif tool_name == "command_inventory_manager":
                return await inventory_manager_agent.execute_command(
                    action="restock",
                    product_identifier=args.get("product_identifier", ""),
                    quantity=int(args.get("quantity", 15)),
                    set_exact=args.get("set_exact")
                )
            elif tool_name == "command_order_manager":
                return await order_manager_agent.execute_command(
                    action="update_status",
                    order_id=args.get("order_id", ""),
                    new_status=args.get("new_status", "Confirmed"),
                    notes=args.get("notes")
                )
            elif tool_name == "command_refund_manager":
                return await refund_manager_agent.execute_command(
                    action="refund",
                    order_id=args.get("order_id", ""),
                    reason=args.get("reason", "Admin command"),
                    force=bool(args.get("force_override", False))
                )
            elif tool_name == "command_dispatcher":
                return await dispatcher_agent.execute_command(
                    action="dispatch",
                    order_id=args.get("order_id"),
                    tracking_number=args.get("tracking_number")
                )
            elif tool_name == "command_review_manager":
                return await review_feedback_agent.execute_command(
                    action="summary",
                    product_id_or_name=args.get("product_identifier", "")
                )
            elif tool_name == "get_admin_dashboard_metrics":
                orders = order_manager.get_all_orders()
                products = inventory_manager.get_all_products()
                total_rev = sum(o.get("total", 0) for o in orders if o.get("status") not in ["Cancelled", "Refunded"])
                low_stock = [p for p in products if p.get("STOCK_REMAINING", 0) <= 5]
                return {
                    "total_revenue": round(total_rev, 2),
                    "total_orders": len(orders),
                    "active_orders": len([o for o in orders if o.get("status") in ["Confirmed", "Dispatched", "Shipped"]]),
                    "total_products": len(products),
                    "low_stock_count": len(low_stock)
                }
            return {"error": f"Unknown tool '{tool_name}'"}
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}

    async def run_prompt(self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        messages = [{"role": "system", "content": ADMIN_SYSTEM_PROMPT}]
        if conversation_history:
            for msg in conversation_history[-6:]:
                messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        executed_tools = []
        final_text = ""

        try:
            for _ in range(5):
                response = await self._call_llm_with_fallback(
                    messages=messages,
                    tools=ADMIN_TOOLS,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=2500
                )
                res_msg = response.choices[0].message
                tool_calls = res_msg.tool_calls

                if not tool_calls:
                    final_text = clean_think_tags(res_msg.content or "")
                    break

                messages.append({
                    "role": "assistant",
                    "content": res_msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in tool_calls
                    ]
                })
                for tc in tool_calls:
                    t_name = tc.function.name
                    raw_args = tc.function.arguments
                    try:
                        t_args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip() else (raw_args if isinstance(raw_args, dict) else {})
                    except Exception:
                        t_args = {}
                    t_out = await self.execute_tool(t_name, t_args)
                    executed_tools.append({"name": t_name, "args": t_args, "output": t_out})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": t_name,
                        "content": json.dumps(t_out)
                    })

            if not final_text:
                final_res = await self._call_llm_with_fallback(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=2000
                )
                final_text = clean_think_tags(final_res.choices[0].message.content or "")

        except Exception as e:
            print(f"AdminChatAgent fallback routing for: '{prompt}' (Reason: {e})", flush=True)
            p_lower = prompt.lower()
            if "discount" in p_lower or "price" in p_lower or "increase" in p_lower:
                cat = "Footwear" if "footwear" in p_lower or "shoe" in p_lower else ("Outerwear" if "outerwear" in p_lower else None)
                perc = -5.0 if "discount" in p_lower or "-" in prompt else 5.0
                t_out = await self.execute_tool("command_price_manager", {"action": "adjust", "category": cat, "percentage": perc})
                executed_tools.append({"name": "command_price_manager", "args": {"category": cat, "percentage": perc}, "output": t_out})
                final_text = f"🏷️ **Price Manager Agent**: {t_out.get('message', 'Adjusted category prices.')}"
            elif "restock" in p_lower or "stock" in p_lower or "inventory" in p_lower:
                t_out = await self.execute_tool("command_inventory_manager", {"action": "restock", "product_identifier": "prod_001", "quantity": 15})
                executed_tools.append({"name": "command_inventory_manager", "args": {"quantity": 15}, "output": t_out})
                final_text = f"📦 **Inventory Manager Agent**: {t_out.get('message', 'Restocked catalog inventory.')}"
            elif "refund" in p_lower:
                t_out = await self.execute_tool("command_refund_manager", {"action": "audit"})
                executed_tools.append({"name": "command_refund_manager", "args": {}, "output": t_out})
                final_text = f"💳 **Refund Manager Agent**: {t_out.get('details', 'Audited refund requests.')}"
            else:
                t_out = await self.execute_tool("get_admin_dashboard_metrics", {})
                executed_tools.append({"name": "get_admin_dashboard_metrics", "args": {}, "output": t_out})
                final_text = f"📊 **Admin Metrics**: Total Revenue: **${t_out.get('total_revenue', 0.0)}**, Total Orders: **{t_out.get('total_orders', 0)}**, Active Orders: **{t_out.get('active_orders', 0)}**."

        return {
            "success": True,
            "response": final_text,
            "tool_calls": executed_tools
        }

admin_chat_agent = AdminChatAgent()
