from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from groq import Groq

from backend.inventory_manager import inventory_manager
from backend.order_manager import order_manager
from backend.review_manager import review_manager

# =====================================================================
# LOGGING INFRASTRUCTURE
# =====================================================================
LOGS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "agent_logs.json"))
_log_lock = threading.RLock()


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
        logs = logs[:200]

        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
    return entry


def get_agent_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Returns the most recent agent audit logs from agent_logs.json."""
    with _log_lock:
        if os.path.exists(LOGS_FILE):
            try:
                with open(LOGS_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
                return logs[:limit]
            except Exception:
                return []
        return []


def clean_think_tags(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    cleaned = cleaned.replace('\u202f', ' ').replace('\u00a0', ' ').replace('\u200b', '')
    return cleaned.strip()


MESSAGES_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "agent_messages.json"))


class AgentMessageBus:
    """
    Thread-safe publish/subscribe message bus for inter-agent communication.
    Agents publish messages to named inboxes and consume them asynchronously.
    All messages are persisted to data/agent_messages.json and logged for audit transparency.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._inboxes: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._message_history: List[Dict[str, Any]] = []
        self._load_messages()

    def _load_messages(self):
        if os.path.exists(MESSAGES_FILE):
            try:
                with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
                    self._message_history = json.load(f)
            except Exception:
                self._message_history = []

    def _save_messages(self):
        try:
            with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
                json.dump(self._message_history[:500], f, indent=2)
        except Exception:
            pass

    def publish(self, from_agent: str, to_agent: str, subject: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Publish a message from one agent to another's inbox."""
        msg = {
            "id": f"msg_{uuid.uuid4().hex[:8]}",
            "from": from_agent,
            "to": to_agent,
            "subject": subject,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read": False
        }
        with self._lock:
            self._inboxes[to_agent].append(msg)
            self._message_history.insert(0, msg)
            self._message_history = self._message_history[:500]
            self._save_messages()

        log_agent_action(
            agent_name=from_agent,
            action=f"⚡ Message -> {to_agent}",
            details=f"[{subject}] {json.dumps(payload)[:200]}",
            autonomous=True
        )
        try:
            print(f"[AgentBus] {from_agent} -> {to_agent}: {subject}", flush=True)
        except Exception:
            pass
        return msg

    def get_inbox(self, agent_name: str, mark_read: bool = True) -> List[Dict[str, Any]]:
        """Fetch all unread messages for an agent."""
        with self._lock:
            messages = [m for m in self._inboxes[agent_name] if not m["read"]]
            if mark_read:
                for m in self._inboxes[agent_name]:
                    m["read"] = True
            return messages

    def get_all_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent message history for the admin dashboard."""
        with self._lock:
            return self._message_history[:limit]

    def get_inbox_snapshot(self) -> Dict[str, int]:
        """Returns unread message counts per agent inbox."""
        with self._lock:
            return {agent: sum(1 for m in msgs if not m["read"]) for agent, msgs in self._inboxes.items()}


# Global message bus singleton
message_bus = AgentMessageBus()


# =====================================================================
# SHARED LLM CALL UTILITY WITH RATE-LIMIT THROTTLING & BACKOFF
# =====================================================================
def _call_groq_sync(
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict]] = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    fallback_models: Optional[List[str]] = None
) -> Any:
    """
    Synchronous Groq LLM call with per-agent dedicated API key, model fallback,
    and automatic 429 rate-limit backoff delay.
    """
    client = Groq(api_key=api_key)
    # Primary model -> specified fallbacks -> valid Groq models
    models_to_try = list(dict.fromkeys([model] + (fallback_models or []) + ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]))

    last_err = None
    for m in models_to_try:
        try:
            kwargs = {
                "model": m,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": 15.0
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            resp = client.chat.completions.create(**kwargs)
            return resp
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate limit" in err_str.lower():
                print(f"[LLM Rate Limit] {m} hit 429 rate limit. Falling back to next model...", flush=True)
                time.sleep(1.0)
                last_err = e
                continue
            else:
                print(f"[LLM] {m} failed: {err_str[:80]}. Trying next model...", flush=True)
                last_err = e
                continue
    raise last_err or Exception("All models exhausted.")


# =====================================================================
# 1. 🏷️ PRICE MANAGER AGENT (Model: GPT-OSS-20B)
#    - Adjusts selling prices based on inventory stock levels, order history, and base price
#    - Receives high-demand signals from Inventory Manager and directives from CEO
#    - Has its own dedicated Groq API key
# =====================================================================
class PriceManagerAgent:
    name = "Price Manager Agent"

    def __init__(self):
        self.api_key = os.environ.get("PRICE_MANAGER_API_KEY", os.environ.get("ADMIN_GROQ_API_KEY", ""))
        self.model = os.environ.get("PRICE_MANAGER_MODEL", "openai/gpt-oss-20b")
        self.fallback_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        self.last_adjusted_skus: List[str] = []

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        Autonomous cycle:
        - Reads inter-agent messages from Inventory Manager (high-demand signals) and CEO directives.
        - Analyzes inventory stock levels, owner BASE_PRICE floor, and order history.
        - Dynamically optimizes Selling Prices strictly >= BASE_PRICE floor.
        - Applies demand markup (+4% to +25%) and scarcity surge (+6% to +12%), with overstock discounts down to BASE_PRICE.
        - Responds to Inventory Manager and reports price adjustments to CEO.
        """
        products = inventory_manager.get_all_products()
        orders = order_manager.get_all_orders()
        adjusted = []
        ceo_alerts = []

        # Process incoming messages from Inventory Manager & CEO
        inbox = message_bus.get_inbox(self.name)
        high_demand_ids = set()
        hold_surges = False

        for msg in inbox:
            subj = msg.get("subject")
            payload = msg.get("payload", {})
            if subj == "HIGH_DEMAND_SIGNAL":
                for pid in payload.get("product_ids", []):
                    high_demand_ids.add(pid)
                log_agent_action(
                    self.name,
                    "📥 Demand Signal Acknowledged",
                    f"Received high-demand signal for {len(payload.get('product_ids', []))} SKUs from Inventory Manager.",
                    autonomous=True
                )
            elif subj in ["CEO_PRICE_DIRECTIVE", "PRICE_DIRECTIVE"]:
                hold_surges = payload.get("instruction", "").lower().find("hold") != -1
                log_agent_action(
                    self.name,
                    "📥 CEO Pricing Directive Received",
                    f"CEO Directive: {payload.get('instruction', 'Optimize dynamic pricing')}",
                    autonomous=True
                )

        # Build order frequency map for demand analysis
        order_freq: Dict[str, int] = {}
        for o in orders:
            if o.get("status") not in ["Cancelled", "Refunded"]:
                for item in o.get("items", []):
                    pid = item.get("product_id", "")
                    order_freq[pid] = order_freq.get(pid, 0) + 1

        for p in products:
            pid = p.get("id", "")
            stock = p.get("STOCK_REMAINING", 0)
            price = p.get("PRICE", 100.0)
            base_price = p.get("BASE_PRICE", price)
            p_name = p.get("PRODUCT_NAME", pid)
            demand = order_freq.get(pid, 0)
            is_high_demand = pid in high_demand_ids or demand >= 3

            # Calculate dynamic pricing components
            if hold_surges:
                demand_markup = 0.05 if demand >= 2 else 0.03
                scarcity_surge = 0.0
            else:
                demand_markup = 0.25 if is_high_demand else (0.15 if demand >= 3 else (0.08 if demand >= 1 else 0.04))
                scarcity_surge = 0.12 if 0 < stock <= 2 else (0.06 if stock <= 5 else 0.0)
            overstock_discount = 0.02 if (stock > 35 and demand < 2) else 0.0

            # Target dynamic price strictly enforced to ALWAYS be strictly GREATER than BASE_PRICE (> BASE_PRICE)
            total_markup = max(0.03, demand_markup + scarcity_surge - overstock_discount)
            target_price = round(max(base_price * (1.0 + total_markup), base_price + 10.0), 2)

            if abs(price - target_price) >= 0.01:
                inventory_manager.update_price(pid, target_price, enforce_base_price=True)
                adjusted.append(f"{p_name} (₹{price:.2f} -> ₹{target_price:.2f} [Base: ₹{base_price:.2f}])")
                if target_price > base_price * 1.2:
                    ceo_alerts.append(f"Surge applied to {p_name}: ₹{price:.2f} -> ₹{target_price:.2f} (Base: ₹{base_price:.2f})")

        details = (
            f"Dynamic Price Engine (INR, 0% Tax): Scanned {len(products)} SKUs. "
            + (f"Adjusted {len(adjusted)} prices (All selling prices strictly > Base Price): {'; '.join(adjusted)}" if adjusted else
               "All catalog prices perfectly optimized with dynamic demand & strictly > BASE_PRICE floor.")
        )

        # Closed-loop report to CEO and Inventory Manager if prices were adjusted
        if adjusted:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="PRICE_CHANGES_REPORT",
                payload={"changes": ceo_alerts or adjusted[:5], "total_adjusted": len(adjusted)}
            )
            if high_demand_ids:
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Inventory Manager Agent",
                    subject="PRICE_OPTIMIZED_CONFIRMATION",
                    payload={"status": "APPLIED", "message": f"Optimized dynamic selling prices for high-demand SKUs: {list(high_demand_ids)}"}
                )

        log_agent_action(self.name, "Dynamic Price Optimization", details, affected_items=adjusted, autonomous=True)
            
        return {"success": True, "agent": self.name, "adjusted": adjusted, "details": details}

    async def execute_command(self, action: str, category: Optional[str] = None, percentage: float = 0.0,
                              product_id: Optional[str] = None, new_price: Optional[float] = None,
                              base_price: Optional[float] = None) -> Dict[str, Any]:
        """Executes explicit owner/CEO command with BASE_PRICE support."""
        if product_id and (new_price is not None or base_price is not None):
            res = inventory_manager.update_price(
                product_id=product_id,
                new_price=new_price if new_price is not None else 0.0,
                base_price=base_price,
                enforce_base_price=True
            )
            log_agent_action(self.name, "Manual Price Update", res.get("message", "Price updated"), [product_id], autonomous=False)
            return res
        elif percentage != 0.0:
            res = inventory_manager.bulk_price_adjustment(category=category, percentage=percentage)
            log_agent_action(self.name, "Bulk Price Adjustment", res.get("message", "Bulk adjustment"), [category or "All"], autonomous=False)
            return res
        return {"success": False, "error": "Invalid price manager command parameters."}


# =====================================================================
# 2. 📦 INVENTORY MANAGER AGENT (Model: GPT-OSS-20B)
#    - Reports low stock to CEO for ordering decisions
#    - Signals high-demand items to Price Manager for dynamic optimization
#    - Dispatches orders and reports to Order Management Agent
#    - Has its own dedicated Groq API key
# =====================================================================
class InventoryManagerAgent:
    name = "Inventory Manager Agent"

    def __init__(self):
        self.api_key = os.environ.get("INVENTORY_MANAGER_API_KEY", os.environ.get("ADMIN_GROQ_API_KEY", ""))
        self.model = os.environ.get("INVENTORY_MANAGER_MODEL", "openai/gpt-oss-20b")
        self.fallback_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        self.reported_low_stock_ids: Set[str] = set()
        self.signaled_demand_ids: Set[str] = set()

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous cycle:
        - Scans catalog for low-stock items (<5 units) → reports to CEO when newly detected
        - Detects high-demand items (high order frequency) → signals Price Manager
        - Auto-restocks low-stock items (+20 units)
        - Reports dispatch status updates to Order Management Agent
        """
        # Process inbox confirmations
        inbox = message_bus.get_inbox(self.name)
        for msg in inbox:
            subj = msg.get("subject")
            if subj in ["CEO_INVENTORY_ACKNOWLEDGE", "CEO_RESTOCK_ACKNOWLEDGE"]:
                log_agent_action(
                    self.name,
                    "📥 CEO Restock Acknowledgment",
                    f"CEO confirmed inventory replenishment status: {msg.get('payload', {}).get('action', 'Approved')}",
                    autonomous=True
                )
            elif subj == "PRICE_OPTIMIZED_CONFIRMATION":
                log_agent_action(
                    self.name,
                    "📥 Price Optimization Confirmation",
                    f"Price Manager confirmed dynamic surge pricing for signaled SKUs.",
                    autonomous=True
                )

        low_stock_items = inventory_manager.get_low_stock_products(threshold=4)
        products = inventory_manager.get_all_products()
        orders = order_manager.get_all_orders()
        restocked = []
        ceo_low_stock_alerts = []
        new_high_demand_ids = []

        # --- Build order frequency map ---
        order_freq: Dict[str, int] = {}
        for o in orders:
            if o.get("status") not in ["Cancelled", "Refunded"]:
                for item in o.get("items", []):
                    pid = item.get("product_id", "")
                    order_freq[pid] = order_freq.get(pid, 0) + 1

        # --- Identify high-demand products (ordered 3+ times recently) ---
        for p in products:
            pid = p.get("id", "")
            stock = p.get("STOCK_REMAINING", 0)
            demand = order_freq.get(pid, 0)
            if demand >= 3 and stock <= 10:
                if pid not in self.signaled_demand_ids:
                    new_high_demand_ids.append(pid)
                    self.signaled_demand_ids.add(pid)

        # --- Auto-restock low-stock items ---
        for p in low_stock_items:
            p_id = p["id"]
            p_name = p.get("PRODUCT_NAME", p_id)
            current_stock = p.get("STOCK_REMAINING", 0)
            restock_qty = 20
            res = inventory_manager.restock_product(p_id, restock_qty)
            if res.get("success"):
                restocked.append(f"{p_name} ({current_stock} → {current_stock + restock_qty} units)")
                if p_id not in self.reported_low_stock_ids:
                    ceo_low_stock_alerts.append({
                        "product_id": p_id,
                        "product_name": p_name,
                        "was_stock": current_stock,
                        "restocked_to": current_stock + restock_qty
                    })
                    self.reported_low_stock_ids.add(p_id)

        # --- Report low-stock situation to CEO only once per new alert ---
        if ceo_low_stock_alerts:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="LOW_STOCK_REPORT",
                payload={
                    "low_stock_items": ceo_low_stock_alerts,
                    "count": len(ceo_low_stock_alerts),
                    "action_taken": "Auto-restocked +20 units each"
                }
            )

        # --- Signal high-demand items to Price Manager only when newly detected ---
        if new_high_demand_ids:
            message_bus.publish(
                from_agent=self.name,
                to_agent="Price Manager Agent",
                subject="HIGH_DEMAND_SIGNAL",
                payload={
                    "product_ids": new_high_demand_ids,
                    "reason": "High order frequency detected (≥3 orders), stock running low"
                }
            )

        # --- Process confirmed orders for dispatch ---
        confirmed_orders = [o for o in orders if o.get("status") == "Confirmed"]
        dispatched_orders = []
        for o in confirmed_orders[:5]:  # Process up to 5 per cycle
            o_id = o.get("order_id")
            res = order_manager.assign_tracking_number(o_id)
            if res.get("success"):
                trk = res.get("order", {}).get("tracking_number", "TRK-XXXXX")
                dispatched_orders.append({"order_id": o_id, "tracking": trk})

        # --- Report dispatched orders to Order Management Agent ---
        if dispatched_orders:
            message_bus.publish(
                from_agent=self.name,
                to_agent="Order Management Agent",
                subject="ORDERS_DISPATCHED",
                payload={
                    "dispatched": dispatched_orders,
                    "count": len(dispatched_orders)
                }
            )

        details = (
            f"Warehouse scan complete. "
            + (f"Auto-restocked {len(restocked)} SKUs: {', '.join(restocked)}. " if restocked else "All stock levels healthy. ")
            + (f"Signaled {len(new_high_demand_ids)} high-demand SKUs to Price Manager. " if new_high_demand_ids else "")
            + (f"Dispatched {len(dispatched_orders)} confirmed orders." if dispatched_orders else "")
        )

        log_agent_action(self.name, "Autonomous Warehouse Cycle", details,
                         affected_items=[p["id"] for p in low_stock_items], autonomous=True)
        return {"success": True, "agent": self.name, "restocked": restocked,
                "dispatched": dispatched_orders, "details": details}

    async def execute_command(self, action: str, product_identifier: str, quantity: int = 15,
                              set_exact: Optional[int] = None) -> Dict[str, Any]:
        """Executes explicit owner/CEO command."""
        if set_exact is not None:
            res = inventory_manager.update_stock(product_identifier, set_exact)
            log_agent_action(self.name, "Stock Set Override", res.get("message", "Stock updated"), [product_identifier], autonomous=False)
            return res
        else:
            res = inventory_manager.restock_product(product_identifier, quantity)
            log_agent_action(self.name, "Manual Restock Trigger", res.get("message", "Restocked"), [product_identifier], autonomous=False)
            return res


# =====================================================================
# 3. 📋 ORDER MANAGEMENT AGENT (Model: GPT-OSS-20B)
#    - Manages order lifecycle: Pending → Confirmed → Dispatched → Shipped → Delivered
#    - Receives dispatch reports from Dispatcher and Inventory Manager
#    - Has its own dedicated Groq API key
# =====================================================================
class OrderManagementAgent:
    name = "Order Management Agent"

    def __init__(self):
        self.api_key = os.environ.get("ORDER_MANAGER_API_KEY", os.environ.get("ADMIN_GROQ_API_KEY", ""))
        self.model = os.environ.get("ORDER_MANAGER_MODEL", "openai/gpt-oss-20b")
        self.fallback_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        self.reported_sla_ids: Set[str] = set()

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous cycle:
        - Processes inter-agent messages (dispatch reports from Dispatcher & Inventory Manager)
        - Audits order statuses across the lifecycle
        - Reports SLA breaches to CEO
        """
        all_orders = order_manager.get_all_orders()
        status_counts: Dict[str, int] = {}
        sla_alerts = []

        for o in all_orders:
            st = o.get("status", "Confirmed")
            status_counts[st] = status_counts.get(st, 0) + 1

        # Process incoming dispatch reports from Dispatcher / Inventory Manager
        inbox = message_bus.get_inbox(self.name)
        for msg in inbox:
            if msg.get("subject") == "ORDERS_DISPATCHED":
                dispatched = msg.get("payload", {}).get("dispatched", [])
                log_agent_action(
                    self.name,
                    "📬 Logistics Fulfillment Sync",
                    f"Fulfillment confirmed: {len(dispatched)} orders dispatched with active tracking numbers.",
                    autonomous=True
                )

        # Detect pending orders older than 1 hour (SLA breach risk)
        now = datetime.now(timezone.utc)
        for o in all_orders:
            if o.get("status") == "Pending":
                try:
                    created = datetime.fromisoformat(o.get("created_at", now.isoformat()))
                    if (now - created).total_seconds() > 3600:
                        o_id = o.get("order_id")
                        if o_id not in self.reported_sla_ids:
                            sla_alerts.append(o_id)
                            self.reported_sla_ids.add(o_id)
                except Exception:
                    pass

        # Report SLA breaches to CEO only once
        if sla_alerts:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="SLA_BREACH_ALERT",
                payload={
                    "pending_too_long": sla_alerts,
                    "count": len(sla_alerts),
                    "threshold": "1 hour",
                    "action_required": "Review and confirm these orders"
                }
            )

        details = (
            f"Audited {len(all_orders)} lifetime orders. "
            f"Breakdown: {', '.join(f'{st}: {count}' for st, count in status_counts.items())}. "
            + (f"SLA alerts raised for {len(sla_alerts)} stale pending orders." if sla_alerts else "All SLAs nominal.")
        )

        log_agent_action(self.name, "Order Pipeline Audit", details, affected_items=[], autonomous=True)
        return {"success": True, "agent": self.name, "status_breakdown": status_counts,
                "sla_alerts": sla_alerts, "details": details}

    async def execute_command(self, action: str, order_id: str, new_status: str,
                              notes: Optional[str] = None) -> Dict[str, Any]:
        """Executes explicit owner/CEO command to change order status."""
        res = order_manager.update_order_status(order_id, new_status, notes=notes)
        log_agent_action(self.name, "Manual Order Status Change",
                         res.get("message", f"Status updated to {new_status}"), [order_id], autonomous=False)
        return res


# =====================================================================
# 4. 💰 FINANCE MANAGER AGENT (Model: GPT-OSS-20B)
#    - Oversees store finances: revenue, refunds, P&L monitoring
#    - Auto-approves refunds if: cancelled ≤24 hours AND not Shipped/Delivered
#    - Reports financial anomalies to CEO once and awaits directive
#    - Has its own dedicated Groq API key
# =====================================================================
class FinanceManagerAgent:
    name = "Finance Manager Agent"

    def __init__(self):
        self.api_key = os.environ.get("FINANCE_MANAGER_API_KEY", os.environ.get("ADMIN_GROQ_API_KEY", ""))
        self.model = os.environ.get("FINANCE_MANAGER_MODEL", "openai/gpt-oss-20b")
        self.fallback_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        self.awaiting_ceo_directive = False
        self.last_reported_refund_rate = 0.0
        self.last_reported_refunded_total = 0.0

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous cycle:
        - Scans all orders for financial health metrics (revenue, refunds, GMV)
        - Enforces the strict refund rule: Auto-approves if cancelled ≤24h AND not Shipped/Delivered
        - Reports financial summary and anomalies to CEO once (statefully) and awaits CEO resolution
        """
        # Process CEO acknowledgment / directives from inbox
        inbox = message_bus.get_inbox(self.name)
        for msg in inbox:
            subj = msg.get("subject")
            if subj in ["CEO_FINANCE_ACKNOWLEDGE", "CEO_DIRECTIVE"]:
                self.awaiting_ceo_directive = False
                log_agent_action(
                    self.name,
                    "📥 CEO Financial Directive Received",
                    f"CEO acknowledged refund state: {msg.get('payload', {}).get('action', 'Strategy deployed')}",
                    autonomous=True
                )

        orders = order_manager.get_all_orders()
        approved_refunds = []
        financial_alerts = []

        total_gmv = sum(o.get("total", 0) for o in orders)
        active_revenue = sum(o.get("total", 0) for o in orders if o.get("status") not in ["Cancelled", "Refunded"])
        total_refunded = sum(o.get("total", 0) for o in orders if o.get("status") == "Refunded")
        refund_rate = (total_refunded / total_gmv * 100) if total_gmv > 0 else 0

        # Evaluate and auto-approve eligible refunds
        for o in orders:
            o_id = o.get("order_id")
            status = o.get("status", "Confirmed")
            if status == "Cancelled" and not o.get("refund_details"):
                eval_res = order_manager.evaluate_24h_cancellation_and_refund(o_id, reason="24h Auto-Refund Rule")
                if eval_res.get("approved"):
                    approved_refunds.append(o_id)

        # Alert CEO if refund rate is high AND state changed significantly since last CEO alert
        should_alert_ceo = False
        if refund_rate > 15.0:
            financial_alerts.append(f"HIGH REFUND RATE: {refund_rate:.1f}% of GMV refunded")
            is_new_incident = (self.last_reported_refund_rate == 0.0)
            is_rate_surge = ((refund_rate - self.last_reported_refund_rate) >= 2.0)
            is_new_refunds = (total_refunded > self.last_reported_refunded_total and len(approved_refunds) > 0)

            if is_new_incident or is_rate_surge or is_new_refunds:
                should_alert_ceo = True

        if should_alert_ceo:
            self.awaiting_ceo_directive = True
            self.last_reported_refund_rate = refund_rate
            self.last_reported_refunded_total = total_refunded
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="FINANCE_ALERT",
                payload={
                    "alert": "High refund rate detected",
                    "refund_rate_pct": round(refund_rate, 2),
                    "total_gmv": round(total_gmv, 2),
                    "total_refunded": round(total_refunded, 2),
                    "active_revenue": round(active_revenue, 2),
                    "approved_refunds_this_cycle": approved_refunds,
                    "action_needed": "CEO strategic action: Review refund root cause & adjust promotional margins."
                }
            )
        elif approved_refunds:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="REFUNDS_PROCESSED",
                payload={
                    "approved_refunds": approved_refunds,
                    "count": len(approved_refunds),
                    "rule": "24h cancellation & non-shipped rule"
                }
            )

        details = (
            f"Financial audit (INR, 0% Tax): Active Revenue: ₹{active_revenue:,.2f} | "
            f"GMV: ₹{total_gmv:,.2f} | Refund Rate: {refund_rate:.1f}%. "
            + (f"Auto-approved {len(approved_refunds)} refunds (24h rule): {', '.join(approved_refunds)}."
               if approved_refunds else "No pending eligible refunds.")
            + (f" ⚠️ Alerts: {'; '.join(financial_alerts)}" if financial_alerts else "")
        )

        log_agent_action(self.name, "Financial Health Audit & Refund Processing",
                         details, affected_items=approved_refunds, autonomous=True)
        return {
            "success": True, "agent": self.name,
            "approved_refunds": approved_refunds,
            "financial_summary": {
                "active_revenue": round(active_revenue, 2),
                "total_gmv": round(total_gmv, 2),
                "refund_rate_pct": round(refund_rate, 2)
            },
            "details": details
        }

    async def execute_command(self, action: str, order_id: str, reason: str = "Owner Request",
                              force: bool = False) -> Dict[str, Any]:
        """Executes cancellation & refund evaluation."""
        if force:
            from backend.payment_manager import payment_manager
            res = payment_manager.process_refund(order_id, reason=f"[Owner Override] {reason}")
            log_agent_action(self.name, "Forced Manual Refund", res.get("message", "Refund processed"), [order_id], autonomous=False)
            return res
        else:
            res = order_manager.evaluate_24h_cancellation_and_refund(order_id, reason=reason)
            log_agent_action(self.name, "24h Refund Rule Evaluation",
                             res.get("message") or res.get("error", "Evaluated"), [order_id], autonomous=False)
            return res


# =====================================================================
# 5. 🚚 DISPATCHER AGENT (Model: GPT-OSS-20B)
#    - Finds confirmed orders, assigns tracking numbers, dispatches
#    - Works in coordination with Inventory Manager and Order Management Agent
#    - Has its own dedicated Groq API key
# =====================================================================
class DispatcherAgent:
    name = "Dispatcher Agent"

    def __init__(self):
        self.api_key = os.environ.get("INVENTORY_MANAGER_API_KEY", os.environ.get("ADMIN_GROQ_API_KEY", ""))
        self.model = os.environ.get("DISPATCHER_MODEL", "openai/gpt-oss-20b")
        self.fallback_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous cycle:
        - Finds all 'Confirmed' orders
        - Generates logistics tracking numbers (TRK-XXXXX)
        - Transitions status: Confirmed → Dispatched
        - Emits ORDERS_DISPATCHED notification to Order Management Agent
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

        # Report to Order Management Agent only when orders were dispatched
        if dispatched:
            message_bus.publish(
                from_agent=self.name,
                to_agent="Order Management Agent",
                subject="ORDERS_DISPATCHED",
                payload={
                    "dispatched": [{"order_id": d.split()[0], "tracking": d.split("Tracking: ")[-1].rstrip(")")}
                                   for d in dispatched],
                    "count": len(dispatched)
                }
            )

        details = (
            f"Fulfillment scan completed. "
            + (f"Dispatched {len(dispatched)} orders with tracking: {', '.join(dispatched)}"
               if dispatched else "All confirmed orders are currently dispatched.")
        )
        log_agent_action(self.name, "Logistics Dispatch Sync", details,
                         affected_items=[d.split()[0] for d in dispatched], autonomous=True)
        return {"success": True, "agent": self.name, "dispatched": dispatched, "details": details}

    async def execute_command(self, action: str, order_id: Optional[str] = None,
                              tracking_number: Optional[str] = None) -> Dict[str, Any]:
        """Executes explicit dispatching command."""
        if order_id:
            res = order_manager.assign_tracking_number(order_id, tracking_number)
            log_agent_action(self.name, "Manual Order Dispatch", res.get("message", "Dispatched"), [order_id], autonomous=False)
            return res
        else:
            return await self.run_autonomous_cycle()


# =====================================================================
# 6. ⭐ REVIEW & FEEDBACK AGENT (Model: GPT-OSS-20B)
#    - Collects customer reviews and feedback
#    - Generates AI-powered sentiment summaries
#    - Updates product descriptions in inventory based on feedback
#    - Has its own dedicated Groq API key
# =====================================================================
class ReviewFeedbackAgent:
    name = "Review and Feedback Manager"

    def __init__(self):
        self.api_key = os.environ.get("REVIEW_MANAGER_API_KEY", os.environ.get("ADMIN_GROQ_API_KEY", ""))
        self.model = os.environ.get("REVIEW_MANAGER_MODEL", "openai/gpt-oss-20b")
        self.fallback_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        self.reported_low_rating_ids: Set[str] = set()

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous cycle:
        - Checks for quality directives from CEO
        - Scans products with new customer reviews
        - Uses Groq LLM to generate AI sentiment & review summaries
        - Updates product descriptions and ratings in inventory.json
        - Reports significant feedback trends to CEO once
        """
        # Process CEO directives from inbox
        inbox = message_bus.get_inbox(self.name)
        for msg in inbox:
            subj = msg.get("subject")
            if subj == "CEO_QUALITY_DIRECTIVE":
                log_agent_action(
                    self.name,
                    "📥 CEO Quality Investigation Directive",
                    f"Initiated sentiment audit based on CEO instruction: {msg.get('payload', {}).get('instruction', 'Review feedback')}",
                    autonomous=True
                )

        products = inventory_manager.get_all_products()
        updated_summaries = []
        new_low_rated_products = []

        for p in products:
            p_id = p["id"]
            p_name = p.get("PRODUCT_NAME", p_id)
            reviews = review_manager.get_reviews_for_product(p_id)

            if reviews:
                avg_rating = sum(r.get("rating", 3) for r in reviews) / len(reviews)

                # Flag low-rated products (<3.5 stars) for CEO attention
                if avg_rating < 3.5 and p_id not in self.reported_low_rating_ids:
                    new_low_rated_products.append({"product": p_name, "avg_rating": round(avg_rating, 1), "review_count": len(reviews)})
                    self.reported_low_rating_ids.add(p_id)

                # Generate AI review summary if not present
                if not p.get("AI_REVIEW_SUMMARY"):
                    res = await review_manager.generate_ai_review_summary(p_id)
                    if res.get("success"):
                        updated_summaries.append(p_name)
                        break  # Process 1 per autonomous cycle

        # Alert CEO about newly detected low-rated products
        if new_low_rated_products:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="LOW_RATING_ALERT",
                payload={
                    "low_rated_products": new_low_rated_products,
                    "count": len(new_low_rated_products),
                    "recommendation": "Consider product quality review or supplier change"
                }
            )

        details = (
            f"Analyzed customer sentiment across {len(products)} products. "
            + (f"Updated AI summaries for: {', '.join(updated_summaries)}. " if updated_summaries else "All product AI summaries current. ")
            + (f"⚠️ {len(new_low_rated_products)} products below 3.5 stars reported to CEO." if new_low_rated_products else "")
        )

        log_agent_action(self.name, "AI Review & Sentiment Synthesis", details,
                         affected_items=updated_summaries, autonomous=True)
        return {"success": True, "agent": self.name, "updated_products": updated_summaries,
                "low_rated": new_low_rated_products, "details": details}

    async def execute_command(self, action: str, product_id_or_name: str) -> Dict[str, Any]:
        """Executes review summary generation on demand."""
        res = await review_manager.generate_ai_review_summary(product_id_or_name)
        log_agent_action(self.name, "On-Demand Review Analysis",
                         f"Generated AI summary for '{product_id_or_name}'", [product_id_or_name], autonomous=False)
        return res

    async def execute_command(self, action: str, product_id_or_name: str) -> Dict[str, Any]:
        """Executes review summary generation on demand."""
        res = await review_manager.generate_ai_review_summary(product_id_or_name)
        log_agent_action(self.name, "On-Demand Review Analysis",
                         f"Generated AI summary for '{product_id_or_name}'", [product_id_or_name], autonomous=False)
        return res


# =====================================================================
# 7. 👔 CEO AGENT
#    - Head of all agents — the ultimate orchestrator
#    - Receives reports/escalations from ALL subordinate agents via message bus
#    - Makes strategic decisions: order restocking, escalate to owner, etc.
#    - Uses the executive model (qwen/qwen3.6-27b) for reasoning
#    - ONLY reports directly to the Owner (via API endpoints and agent logs)
# =====================================================================
CEO_SYSTEM_PROMPT = """You are the CEO Agent of the AI Growth Commerce Agentic Store.
You are the head of a fleet of 6 autonomous AI agents:
1. 🏷️ Price Manager Agent — dynamic pricing based on demand/stock/base price
2. 📦 Inventory Manager Agent — warehouse management, restocking, dispatch coordination
3. 📋 Order Management Agent — order lifecycle (Pending → Confirmed → Dispatched → Shipped → Delivered)
4. 💰 Finance Manager Agent — financial oversight, refund processing (auto-approve ≤24h + not shipped)
5. 🚚 Dispatcher Agent — logistics tracking number assignment and dispatch
6. ⭐ Review & Feedback Agent — sentiment analysis, product description updates

STORE FINANCIAL & PRICING RULES:
- Currency: Indian Rupee (INR ₹). All figures are in INR.
- Tax Policy: 0% Tax (Tax-free storewide on every item).
- Base Price: Product BASE_PRICE is set EXCLUSIVELY by the Store Owner (User) and serves as an immutable floor threshold. You CANNOT change base prices; you can only direct price changes strictly above or equal to the owner's BASE_PRICE floor.

Your responsibilities:
- Read and process all incoming messages from subordinate agents
- Make strategic decisions based on financial data, inventory levels, and order pipeline health
- Issue directives to agents when needed (via tool calls)
- Generate comprehensive reports for the Owner
- Never escalate trivial matters — only surface critical insights and anomalies

Be executive, decisive, and data-driven. Focus on business outcomes.
"""

CEO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "issue_directive_to_price_manager",
            "description": "Issue a pricing directive to the Price Manager Agent. Use when inventory signals or financial data warrant price adjustments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directive": {"type": "string", "description": "The pricing action to take"},
                    "category": {"type": "string", "description": "Product category or 'all'"},
                    "percentage": {"type": "number", "description": "Price change percentage (+/-)"},
                    "product_id": {"type": "string", "description": "Specific product ID if applicable"},
                    "new_price": {"type": "number", "description": "Specific new price if applicable"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "issue_directive_to_inventory_manager",
            "description": "Issue a restocking directive to the Inventory Manager Agent. Use when CEO decides additional stock is needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_identifier": {"type": "string", "description": "Product ID or name to restock"},
                    "quantity": {"type": "integer", "description": "Units to add"},
                    "set_exact": {"type": "integer", "description": "Exact stock count to set"}
                },
                "required": ["product_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "issue_directive_to_order_management",
            "description": "Issue an order status directive to the Order Management Agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID"},
                    "new_status": {"type": "string", "description": "Target status"},
                    "notes": {"type": "string", "description": "Reason/notes"}
                },
                "required": ["order_id", "new_status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_store_overview",
            "description": "Get a full store overview: revenue, orders, inventory health, and all agent reports.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]


class CEOAgent:
    name = "CEO Agent"

    def __init__(self):
        self.api_key = os.environ.get("CEO_API_KEY", os.environ.get("ADMIN_GROQ_API_KEY", ""))
        self.model = os.environ.get("CEO_MODEL", "qwen/qwen3.6-27b")
        self.fallback_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        Autonomous strategic cycle:
        - Reads all pending inter-agent messages from the message bus
        - Responds closed-loop to subordinate agents (Finance, Inventory, Review, Price)
        - Makes strategic executive decisions using Groq Qwen LLM
        - Issues directives to agents as needed
        - Logs a comprehensive report for the Owner
        """
        inbox = message_bus.get_inbox(self.name)

        if not inbox:
            return {"success": True, "agent": self.name, "messages_processed": 0, "details": "CEO cycle: All subordinate agents operating nominally."}

        # Build structured briefing & send closed-loop replies
        briefing_lines = [f"CEO INBOX: {len(inbox)} pending messages from the agent fleet:\n"]
        for msg in inbox:
            from_ag = msg.get("from", "")
            subj = msg.get("subject", "")
            payload = msg.get("payload", {})
            briefing_lines.append(f"FROM: {from_ag} | SUBJECT: {subj}\nDATA: {json.dumps(payload)[:300]}\n")

            # Human-like closed loop acknowledgements & directives
            if from_ag == "Finance Manager Agent" and subj == "FINANCE_ALERT":
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Finance Manager Agent",
                    subject="CEO_FINANCE_ACKNOWLEDGE",
                    payload={"status": "ACKNOWLEDGED", "action": "Assessed refund alert; directed Price Manager to hold price surges and Review Agent to investigate customer feedback."}
                )
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Price Manager Agent",
                    subject="CEO_PRICE_DIRECTIVE",
                    payload={"instruction": "Hold excessive price surges to protect margin and prevent refund churn."}
                )
            elif from_ag == "Inventory Manager Agent" and subj == "LOW_STOCK_REPORT":
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Inventory Manager Agent",
                    subject="CEO_INVENTORY_ACKNOWLEDGE",
                    payload={"status": "CONFIRMED", "action": "Stock replenishment approved and inventory tracked."}
                )
            elif from_ag == "Review and Feedback Manager" and subj == "LOW_RATING_ALERT":
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Review and Feedback Manager",
                    subject="CEO_QUALITY_DIRECTIVE",
                    payload={"instruction": "Audit customer sentiment on high return items and synthesize root cause."}
                )

        # Get store snapshot
        orders = order_manager.get_all_orders()
        products = inventory_manager.get_all_products()
        total_revenue = sum(o.get("total", 0) for o in orders if o.get("status") not in ["Cancelled", "Refunded"])
        active_orders = len([o for o in orders if o.get("status") in ["Pending", "Confirmed", "Dispatched", "Shipped"]])
        low_stock = [p for p in products if p.get("STOCK_REMAINING", 0) <= 3]

        store_snapshot = (
            f"\nSTORE SNAPSHOT (INR, 0% Tax): Revenue=₹{total_revenue:,.2f} | "
            f"Active Orders={active_orders} | Products={len(products)} | "
            f"Critical Low Stock={len(low_stock)} SKUs"
        )

        ceo_prompt = "\n".join(briefing_lines) + store_snapshot + (
            "\n\nAs CEO, review all agent reports and take appropriate strategic actions. "
            "Use tools to issue directives where needed. Then provide a concise executive summary for the Owner."
        )

        messages = [
            {"role": "system", "content": CEO_SYSTEM_PROMPT},
            {"role": "user", "content": ceo_prompt}
        ]

        directives_issued = []
        ceo_report = ""

        try:
            for _ in range(3):  # ReAct loop - max 3 iterations
                resp = await asyncio.to_thread(
                    _call_groq_sync,
                    self.api_key, self.model, messages, CEO_TOOLS,
                    temperature=0.3, max_tokens=1500, fallback_models=self.fallback_models
                )
                res_msg = resp.choices[0].message
                tool_calls = res_msg.tool_calls

                if not tool_calls:
                    ceo_report = clean_think_tags(res_msg.content or "")
                    break

                messages.append({
                    "role": "assistant",
                    "content": res_msg.content or "",
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in tool_calls
                    ]
                })

                for tc in tool_calls:
                    t_name = tc.function.name
                    try:
                        t_args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else {}
                    except Exception:
                        t_args = {}

                    t_out = await self._execute_ceo_tool(t_name, t_args)
                    directives_issued.append({"tool": t_name, "args": t_args, "result": t_out})

                    messages.append({
                        "role": "tool", "tool_call_id": tc.id,
                        "name": t_name, "content": json.dumps(t_out)
                    })

            if not ceo_report:
                ceo_report = "CEO cycle completed. Processed all agent messages and issued strategic closed-loop directives."

        except Exception as e:
            print(f"[CEO Agent] LLM error: {e}", flush=True)
            ceo_report = f"CEO processed {len(inbox)} agent messages. Closed-loop directives issued to agent fleet."

        details = (
            f"CEO processed {len(inbox)} agent messages. "
            f"Directives issued: {len(directives_issued)}. "
            f"Report: {ceo_report[:300]}"
        )

        log_agent_action(self.name, "CEO Strategic Cycle & Owner Report", details, autonomous=True)
        return {
            "success": True, "agent": self.name,
            "messages_processed": len(inbox),
            "directives_issued": directives_issued,
            "ceo_report": ceo_report,
            "details": details
        }

    async def _execute_ceo_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """CEO executes directives to subordinate agents."""
        try:
            if tool_name == "issue_directive_to_price_manager":
                result = await price_manager_agent.execute_command(
                    action=args.get("directive", "adjust"),
                    category=args.get("category"),
                    percentage=float(args.get("percentage", 0.0)),
                    product_id=args.get("product_id"),
                    new_price=float(args.get("new_price")) if args.get("new_price") is not None else None
                )
                log_agent_action(self.name, "👔 CEO → Price Manager Directive",
                                 f"Directive: {args.get('directive')} | Result: {result.get('message', 'Executed')}", autonomous=True)
                return result

            elif tool_name == "issue_directive_to_inventory_manager":
                result = await inventory_manager_agent.execute_command(
                    action="restock",
                    product_identifier=args.get("product_identifier", ""),
                    quantity=int(args.get("quantity", 20)),
                    set_exact=args.get("set_exact")
                )
                log_agent_action(self.name, "👔 CEO → Inventory Manager Directive",
                                 f"Restock '{args.get('product_identifier')}' | Result: {result.get('message', 'Executed')}", autonomous=True)
                return result

            elif tool_name == "issue_directive_to_order_management":
                result = await order_management_agent.execute_command(
                    action="update_status",
                    order_id=args.get("order_id", ""),
                    new_status=args.get("new_status", "Confirmed"),
                    notes=args.get("notes")
                )
                log_agent_action(self.name, "👔 CEO → Order Management Directive",
                                 f"Order {args.get('order_id')} → {args.get('new_status')} | Result: {result.get('message', 'Executed')}", autonomous=True)
                return result

            elif tool_name == "get_store_overview":
                orders = order_manager.get_all_orders()
                products = inventory_manager.get_all_products()
                total_rev = sum(o.get("total", 0) for o in orders if o.get("status") not in ["Cancelled", "Refunded"])
                status_counts: Dict[str, int] = {}
                for o in orders:
                    st = o.get("status", "Unknown")
                    status_counts[st] = status_counts.get(st, 0) + 1
                low_stock = [p.get("PRODUCT_NAME", p["id"]) for p in products if p.get("STOCK_REMAINING", 0) <= 3]
                return {
                    "total_revenue": round(total_rev, 2),
                    "total_orders": len(orders),
                    "order_breakdown": status_counts,
                    "total_products": len(products),
                    "critical_low_stock": low_stock,
                    "message_bus_snapshot": message_bus.get_inbox_snapshot()
                }
        except Exception as e:
            return {"error": str(e)}

        return {"error": f"Unknown CEO tool: {tool_name}"}

    async def generate_owner_report(self) -> Dict[str, Any]:
        """
        Generates a comprehensive on-demand strategic report for the Owner.
        Pulls all pending messages, store metrics, and produces an executive summary.
        """
        return await self.run_autonomous_cycle()

    async def execute_command(self, action: str, **kwargs) -> Dict[str, Any]:
        """Allows the Owner to directly instruct the CEO Agent."""
        log_agent_action(self.name, "Owner Direct Command", f"Action: {action} | Args: {kwargs}", autonomous=False)
        # CEO processes the owner command and delegates to appropriate agents
        return await self.run_autonomous_cycle()


# =====================================================================
# GLOBAL AGENT INSTANCES
# (Each uses its own dedicated Groq API key from .env)
# =====================================================================
price_manager_agent = PriceManagerAgent()
inventory_manager_agent = InventoryManagerAgent()
order_management_agent = OrderManagementAgent()
finance_manager_agent = FinanceManagerAgent()
dispatcher_agent = DispatcherAgent()
review_feedback_agent = ReviewFeedbackAgent()
ceo_agent = CEOAgent()

# Legacy alias for backward compatibility
order_manager_agent = order_management_agent
refund_manager_agent = finance_manager_agent


# =====================================================================
# 🤖 OMNIPOTENT ADMIN CHATBOT AGENT (Owner-facing command center)
# Routes through CEO awareness — CEO is always kept in the loop
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
                    "new_price": {"type": "number", "description": "New price in INR (₹) if setting directly"},
                    "base_price": {"type": "number", "description": "New base price floor threshold if setting base price"}
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
                    "product_identifier": {"type": "string", "description": "Product ID or name to restock/update"},
                    "quantity": {"type": "integer", "description": "Units to add to existing stock"},
                    "set_exact": {"type": "integer", "description": "Exact stock count to set (optional override)"}
                },
                "required": ["product_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "command_order_management",
            "description": "Command the Order Management Agent to update an order's status (Pending, Confirmed, Dispatched, Shipped, Delivered, Cancelled, Refunded) or inspect orders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID (e.g. 'ORD-1001')"},
                    "new_status": {"type": "string", "description": "Target status"},
                    "notes": {"type": "string", "description": "Optional status note"}
                },
                "required": ["order_id", "new_status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "command_finance_manager",
            "description": "Command the Finance Manager Agent to evaluate the 24-hour and non-shipped refund rule, force a manual refund, or get financial metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID to refund (e.g. 'ORD-1001')"},
                    "reason": {"type": "string", "description": "Cancellation/refund reason"},
                    "force_override": {"type": "string", "description": "Pass 'true' to bypass 24h eligibility check"}
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
                    "order_id": {"type": "string", "description": "Specific order ID to dispatch (optional)"},
                    "tracking_number": {"type": "string", "description": "Custom tracking number if specified"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "command_review_manager",
            "description": "Command the Review & Feedback Agent to analyze customer reviews and generate an AI sentiment & review summary for an item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_identifier": {"type": "string", "description": "Product ID or name"}
                },
                "required": ["product_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_ceo_report",
            "description": "Request the CEO Agent to generate a full strategic report on store operations, agent activity, and inter-agent communications.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_admin_dashboard_metrics",
            "description": "Get real-time revenue, order counts by status, inventory health, recent 24/7 agent actions, and inter-agent message bus state.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

ADMIN_SYSTEM_PROMPT = """You are the 'Owner Command Agent' for the AI Growth Commerce Store.
You have full executive authority and communicate through the CEO Agent, who manages the fleet.

STORE OPERATING RULES:
- Currency: Indian Rupee (INR ₹) everywhere across the store.
- Tax: 0% Tax (Tax-Free storewide on every product).
- Base Price: BASE_PRICE of each product is set EXCLUSIVELY by the Store Owner (User) in the frontend. CEO and subordinate agents CANNOT alter base prices; they only adjust dynamic prices strictly above or equal to the owner's BASE_PRICE floor.

The agent hierarchy is:
👔 CEO Agent (head) — orchestrates all agents, processes inter-agent messages, reports to you
  ├── 🏷️ Price Manager Agent — dynamic pricing based on inventory, orders, owner's base price floor
  ├── 📦 Inventory Manager Agent — restocking, dispatch coordination, signals to CEO & Price Manager
  ├── 📋 Order Management Agent — order lifecycle management (Pending→Delivered)
  ├── 💰 Finance Manager Agent — financial health monitoring, refund processing (auto-approve ≤24h + not shipped)
  ├── 🚚 Dispatcher Agent — logistics tracking assignment
  └── ⭐ Review & Feedback Agent — sentiment analysis, product description updates

Agents communicate with each other autonomously:
- Inventory -> CEO: Low stock reports
- Inventory -> Price Manager: High-demand signals
- Inventory -> Order Management: Dispatch reports
- Finance -> CEO: Financial health reports & alerts
- Review -> CEO: Low rating alerts
- CEO -> All agents: Strategic directives

When the owner orders something, immediately call the appropriate tool(s) and report back clearly with INR (₹) prices.
Be concise, professional, and authoritative.
"""


class AdminChatAgent:
    def __init__(self):
        self.api_key = os.environ.get("ADMIN_GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))
        self.model = os.environ.get("GROQ_ADMIN_MODEL", "qwen/qwen3.6-27b")
        self.fallback_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if tool_name == "command_price_manager":
                return await price_manager_agent.execute_command(
                    action=args.get("action", "adjust"),
                    category=args.get("category"),
                    percentage=float(args.get("percentage", 0.0)),
                    product_id=args.get("product_id"),
                    new_price=float(args.get("new_price")) if args.get("new_price") is not None else None,
                    base_price=float(args.get("base_price")) if args.get("base_price") is not None else None
                )
            elif tool_name == "command_inventory_manager":
                return await inventory_manager_agent.execute_command(
                    action="restock",
                    product_identifier=args.get("product_identifier", ""),
                    quantity=int(args.get("quantity", 15)),
                    set_exact=args.get("set_exact")
                )
            elif tool_name == "command_order_management":
                return await order_management_agent.execute_command(
                    action="update_status",
                    order_id=args.get("order_id", ""),
                    new_status=args.get("new_status", "Confirmed"),
                    notes=args.get("notes")
                )
            elif tool_name == "command_finance_manager":
                return await finance_manager_agent.execute_command(
                    action="refund",
                    order_id=args.get("order_id", ""),
                    reason=args.get("reason", "Admin command"),
                    force=str(args.get("force_override", "false")).lower() == "true"
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
            elif tool_name == "get_ceo_report":
                return await ceo_agent.generate_owner_report()
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
                    "low_stock_count": len(low_stock),
                    "message_bus": message_bus.get_inbox_snapshot()
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
                resp = await asyncio.to_thread(
                    _call_groq_sync,
                    self.api_key, self.model, messages, ADMIN_TOOLS,
                    temperature=0.2, max_tokens=2500, fallback_models=self.fallback_models
                )
                res_msg = resp.choices[0].message
                tool_calls = res_msg.tool_calls

                if not tool_calls:
                    final_text = clean_think_tags(res_msg.content or "")
                    break

                messages.append({
                    "role": "assistant",
                    "content": res_msg.content or "",
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in tool_calls
                    ]
                })
                for tc in tool_calls:
                    t_name = tc.function.name
                    try:
                        t_args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) and tc.function.arguments.strip() else {}
                    except Exception:
                        t_args = {}
                    t_out = await self.execute_tool(t_name, t_args)
                    executed_tools.append({"name": t_name, "args": t_args, "output": t_out})
                    messages.append({
                        "role": "tool", "tool_call_id": tc.id,
                        "name": t_name, "content": json.dumps(t_out)
                    })

            if not final_text:
                resp = await asyncio.to_thread(
                    _call_groq_sync,
                    self.api_key, self.model, messages,
                    temperature=0.3, max_tokens=2000, fallback_models=self.fallback_models
                )
                final_text = clean_think_tags(resp.choices[0].message.content or "")

        except Exception as e:
            print(f"AdminChatAgent fallback for: '{prompt}' (Reason: {e})", flush=True)
            p_lower = prompt.lower()
            if "discount" in p_lower or "price" in p_lower:
                cat = "Footwear" if "footwear" in p_lower else None
                perc = -5.0 if "discount" in p_lower else 5.0
                t_out = await self.execute_tool("command_price_manager", {"action": "adjust", "category": cat, "percentage": perc})
                executed_tools.append({"name": "command_price_manager", "output": t_out})
                final_text = f"🏷️ **Price Manager**: {t_out.get('message', 'Adjusted prices.')}"
            elif "restock" in p_lower or "stock" in p_lower:
                t_out = await self.execute_tool("command_inventory_manager", {"product_identifier": "prod_001", "quantity": 15})
                executed_tools.append({"name": "command_inventory_manager", "output": t_out})
                final_text = f"📦 **Inventory Manager**: {t_out.get('message', 'Restocked inventory.')}"
            elif "refund" in p_lower or "finance" in p_lower:
                t_out = await self.execute_tool("get_admin_dashboard_metrics", {})
                final_text = f"💰 **Finance Manager**: Active Revenue: **${t_out.get('total_revenue', 0.0):,.2f}**"
            elif "ceo" in p_lower or "report" in p_lower:
                t_out = await self.execute_tool("get_ceo_report", {})
                final_text = f"👔 **CEO Report**: {t_out.get('ceo_report', t_out.get('details', 'Report generated.'))}"
            else:
                t_out = await self.execute_tool("get_admin_dashboard_metrics", {})
                executed_tools.append({"name": "get_admin_dashboard_metrics", "output": t_out})
                final_text = (
                    f"📊 **Store Overview**: Revenue: **${t_out.get('total_revenue', 0.0):,.2f}** | "
                    f"Orders: **{t_out.get('total_orders', 0)}** | "
                    f"Active: **{t_out.get('active_orders', 0)}** | "
                    f"Low Stock: **{t_out.get('low_stock_count', 0)} SKUs**"
                )

        return {"success": True, "response": final_text, "tool_calls": executed_tools}


admin_chat_agent = AdminChatAgent()
