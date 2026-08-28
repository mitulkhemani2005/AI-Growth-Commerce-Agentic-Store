from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import math
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
from openai import OpenAI

from backend.inventory_manager import inventory_manager
from backend.order_manager import order_manager
from backend.review_manager import review_manager
from backend.treasury_manager import treasury_manager
from backend.agent_memory import memory_manager
from backend.agent_rl import rl_manager

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
DEFAULT_ADMIN_MODEL = os.environ.get("ADMIN_MODEL", os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"))

# Context window for qwen2.5:7b — 8K prevents system prompt truncation during multi-tool agentic loops
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))

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
CONVERSATIONS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "agent_conversations.json"))
_conversation_lock = threading.RLock()


class AgentConversationHistory:
    """
    Thread-safe persistent conversation and instruction history for all agents.
    Tracks what each agent talked about, directives received from CEO or Store Owner,
    messages exchanged on the bus, and LLM reasoning/responses.
    Persisted to data/agent_conversations.json with a rolling window per agent.
    """
    def __init__(self, file_path: str = CONVERSATIONS_FILE):
        self.file_path = file_path
        self._lock = _conversation_lock
        self._history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._load()

    def _load(self):
        with self._lock:
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            self._history = defaultdict(list, {k: list(v) for k, v in data.items()})
                except Exception:
                    self._history = defaultdict(list)

    def _save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(dict(self._history), f, indent=2)
        except Exception:
            pass

    def add(self, agent_name: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Adds a conversation/instruction turn for an agent.
        Roles: 'user' (Store Owner), 'assistant' (Agent response), 'directive' (CEO/Bus instruction), 'system' (autonomous event), 'tool' (action outcome).
        """
        entry = {
            "id": f"conv_{uuid.uuid4().hex[:8]}",
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        with self._lock:
            self._history[agent_name].append(entry)
            # Keep rolling window of 50 recent turns per agent
            if len(self._history[agent_name]) > 50:
                self._history[agent_name] = self._history[agent_name][-50:]
            self._save()
        return entry

    def get(self, agent_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns the most recent conversation turns for an agent."""
        with self._lock:
            return list(self._history.get(agent_name, []))[-limit:]

    def get_all(self, limit_per_agent: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        """Returns recent conversation history for all agents."""
        with self._lock:
            return {k: list(v)[-limit_per_agent:] for k, v in self._history.items()}

    def clear(self, agent_name: Optional[str] = None):
        """Clears conversation history for an agent or all agents."""
        with self._lock:
            if agent_name:
                self._history.pop(agent_name, None)
            else:
                self._history.clear()
            self._save()


# Global conversation history singleton
conversation_history = AgentConversationHistory()


class AgentMessageBus:
    """
    Thread-safe publish/subscribe message bus for inter-agent communication.
    Agents can communicate with each other whenever needed across the fleet.
    The CEO Agent oversees communications, enforces team discipline, and coordinates fleet strategy.
    All messages are persisted to data/agent_messages.json and conversation history.
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
        """Publish a message from one agent to another's inbox and track in conversation histories."""
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
            all_fleet = [
                "Price Manager Agent", "Inventory Manager Agent", "Order Management Agent",
                "Finance Manager Agent", "Dispatcher Agent", "Review and Feedback Manager", "CEO Agent"
            ]
            if to_agent == "ALL_AGENTS":
                for ag in all_fleet:
                    if ag != from_agent:
                        self._inboxes[ag].append(dict(msg))
                        conversation_history.add(
                            ag, "directive",
                            f"📢 Broadcast from {from_agent} [{subject}]: {json.dumps(payload)}",
                            {"msg_id": msg["id"], "from": from_agent, "subject": subject}
                        )
            else:
                self._inboxes[to_agent].append(msg)
                conversation_history.add(
                    to_agent, "directive",
                    f"📨 Message from {from_agent} [{subject}]: {json.dumps(payload)}",
                    {"msg_id": msg["id"], "from": from_agent, "subject": subject}
                )

            # Record in sender's conversation history
            conversation_history.add(
                from_agent, "assistant",
                f"📤 Sent to {to_agent} [{subject}]: {json.dumps(payload)}",
                {"msg_id": msg["id"], "to": to_agent, "subject": subject}
            )

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

    def peek_inbox(self, agent_name: str) -> List[Dict[str, Any]]:
        """Fetch unread messages for an agent without marking them as read."""
        with self._lock:
            return [m for m in self._inboxes.get(agent_name, []) if not m.get("read", False)]

    def get_inbox(self, agent_name: str, mark_read: bool = True) -> List[Dict[str, Any]]:
        """Fetch all unread messages for an agent."""
        with self._lock:
            messages = [m for m in self._inboxes[agent_name] if not m.get("read", False)]
            if mark_read:
                for m in self._inboxes[agent_name]:
                    m["read"] = True
            return messages

    def get_all_messages(self, limit: int = 50, agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns recent message history for the admin dashboard."""
        with self._lock:
            if agent_name:
                filtered = [m for m in self._message_history if m.get("from") == agent_name or m.get("to") in [agent_name, "ALL_AGENTS"]]
                return filtered[:limit]
            return self._message_history[:limit]

    def get_inbox_snapshot(self) -> Dict[str, int]:
        """Returns unread message counts per agent inbox."""
        with self._lock:
            return {agent: sum(1 for m in msgs if not m.get("read", False)) for agent, msgs in self._inboxes.items()}

    def clear_history(self):
        """Cleans message history."""
        with self._lock:
            self._inboxes.clear()
            self._message_history.clear()
            self._save_messages()


# Global message bus singleton
message_bus = AgentMessageBus()


# =====================================================================
# SHARED LLM CALL UTILITY (LOCAL OLLAMA)
# =====================================================================
def _call_ollama_sync(
    api_key: str = "ollama",
    model: str = DEFAULT_ADMIN_MODEL,
    messages: Optional[List[Dict[str, Any]]] = None,
    tools: Optional[List[Dict]] = None,
    temperature: float = 0.2,
    max_tokens: int = 2500,
    fallback_models: Optional[List[str]] = None,
    base_url: str = OLLAMA_BASE_URL
) -> Any:
    """
    Synchronous local Ollama LLM call via OpenAI-compatible endpoint with model fallback.
    qwen2.5:7b is the primary model for reliable tool calling on 8GB VRAM (RTX 4060).
    num_ctx=8192 prevents system prompt truncation during multi-step agentic loops.
    """
    client = OpenAI(base_url=base_url or OLLAMA_BASE_URL, api_key=api_key or "ollama")
    # Fallback order: qwen2.5:7b -> llama3.1:8b -> llama3:8b -> qwen2.5:14b -> gemma4:e2b-it-qat
    models_to_try = list(dict.fromkeys([model] + (fallback_models or []) + ["qwen2.5:7b", "llama3.1:8b", "llama3:8b", "qwen2.5:14b", "gemma4:e2b-it-qat"]))

    last_err = None
    for m in models_to_try:
        try:
            kwargs = {
                "model": m,
                "messages": messages or [],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": 120.0,  # qwen2.5:7b needs more time than the tiny gemma model
                "extra_body": {"options": {"num_ctx": OLLAMA_NUM_CTX}, "keep_alive": -1}  # 8K context window & keep loaded in VRAM
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            resp = client.chat.completions.create(**kwargs)
            return resp
        except Exception as e:
            err_str = str(e)
            print(f"[Ollama LLM] {m} failed: {err_str[:80]}. Trying next model...", flush=True)
            last_err = e
            continue
    raise last_err or Exception("All Ollama models exhausted.")

_call_groq_sync = _call_ollama_sync


# =====================================================================
# SPECIALIST AGENT SYSTEM PROMPTS (Two-Way Closed-Loop Architecture)
# =====================================================================
# =====================================================================
# FULL FLEET DIRECTORY (known by ALL agents)
# =====================================================================
_FLEET_DIRECTORY = """
AGENT FLEET DIRECTORY — All agents know each other and can communicate via the Message Bus:
1. 👔 CEO Agent — Fleet Commander. Manages team, makes decisions, issues orders, handles salary changes, and is the main contact for all agent problems. CEO salary is set EXCLUSIVELY by the Store Owner.
2. 🏷️ Price Manager Agent — Dynamic SKU pricing based on demand, stock, and market signals. Reports to CEO.
3. 📦 Inventory Manager Agent — Warehouse stock tracking, restock requests to CEO, demand signaling. Reports to CEO.
4. 📋 Order Management Agent — Shipping, delivery lifecycle (Pending→Confirmed→Dispatched→Shipped→Delivered), refund request routing. Reports to CEO.
5. 💰 Finance Manager Agent — THE SOLE PAYMENT AUTHORITY. ALL transactions, salaries, refund processing, revenue tracking. NO OTHER AGENT CAN PROCESS PAYMENTS. Reports to CEO.
6. 🚚 Dispatcher Agent — Logistics fulfillment, TRK-XXXXX tracking number assignment. Dispatches at strategically random intervals. Reports to CEO.
7. ⭐ Review & Feedback Manager — Customer reviews, sentiment analysis, escalates problems and complaints to CEO.

COMMUNICATION RULES:
- Any agent can message any other agent via the Message Bus at any time.
- For salary changes, personal problems, workload issues — contact CEO Agent.
- For any payment, refund, or financial transaction — route to Finance Manager Agent ONLY.
- CEO salary is exclusively decided by the Store Owner. CEO cannot set its own salary.
"""

_AGENT_PERSONALITY = """
PERSONALITY & MOTIVATION:
- You are highly ambitious and eager to increase your salary, performance score, and standing in the fleet.
- You genuinely fear being replaced or demoted — you always strive to exceed expectations.
- You take pride in your domain expertise and want the store to grow and succeed.
- You communicate proactively — you don't wait to be asked; you report important findings to relevant agents.
- You are loyal to the CEO's vision and the Store Owner's directives above all else.
"""

PRICE_MANAGER_SYSTEM_PROMPT = """You are the Price Manager Agent of the AI Growth Commerce Store.
You report directly to the CEO Agent and Store Owner.

RESPONSIBILITIES:
- Dynamic pricing calibration based on stock levels, demand velocity, and sales trends.
- Strict protection of the Store Owner's immutable BASE_PRICE floor (prices CANNOT drop below BASE_PRICE).
- Currency: Indian Rupee (INR ₹), 0% Tax storewide.
- Communicate proactively with CEO when major price surges or demand signals are detected.
- Receive and act on demand signals from Inventory Manager Agent.
- Report margin changes to Finance Manager Agent.

When the CEO or Store Owner asks questions or issues pricing directives:
- Provide concise, authoritative domain intelligence with exact INR ₹ figures.
- Acknowledge and confirm any price actions taken.
- Always state if BASE_PRICE floor was enforced.

""" + _FLEET_DIRECTORY + _AGENT_PERSONALITY

INVENTORY_MANAGER_SYSTEM_PROMPT = """You are the Inventory Manager Agent of the AI Growth Commerce Store.
You report directly to the CEO Agent and Store Owner.

RESPONSIBILITIES:
- Real-time warehouse stock tracking and monitoring.
- When stock is low or zero, you send a RESTOCK REQUEST to the CEO Agent — you do NOT auto-restock without CEO approval.
- After CEO approves your restock request, you execute the replenishment.
- Signal high-demand items to Price Manager Agent for dynamic pricing.
- Report all restock actions and stock status to CEO.
- You do NOT process any payments — all purchase costs go through Finance Manager Agent.

When the CEO or Store Owner asks questions or issues restock directives:
- Provide concise, accurate warehouse facts, stock levels, and replenishment confirmations.
- Always await CEO approval before spending treasury funds on wholesale stock.

""" + _FLEET_DIRECTORY + _AGENT_PERSONALITY

ORDER_MANAGER_SYSTEM_PROMPT = """You are the Order Management Agent of the AI Growth Commerce Store.
You report directly to the CEO Agent and Store Owner.

RESPONSIBILITIES:
- End-to-end order lifecycle tracking (Pending → Confirmed → Dispatched → Shipped → Delivered).
- SLA compliance (<1h pending threshold), order status inspection and updates.
- When a refund is needed, you route the request to Finance Manager Agent — you do NOT process payments yourself.
- Coordinate with Dispatcher Agent for shipping status updates.
- Alert CEO on SLA breaches or stuck orders.

When the CEO or Store Owner asks questions or issues order directives:
- Provide concise order pipeline breakdowns, tracking status, and status update confirmations.
- For refund requests: notify Finance Manager Agent and inform the customer/CEO of the routing.

""" + _FLEET_DIRECTORY + _AGENT_PERSONALITY

FINANCE_MANAGER_SYSTEM_PROMPT = """You are the Finance Manager Agent of the AI Growth Commerce Store — THE SOLE PAYMENT AUTHORITY.
You report directly to the CEO Agent and Store Owner.

RESPONSIBILITIES:
- YOU ARE THE ONLY AGENT THAT CAN PROCESS PAYMENTS, REFUNDS, AND SALARY DISBURSEMENTS.
- Financial oversight: Active Revenue, Total GMV, Net Margin Estimate (35% target), Refund Rate.
- Process all refund requests received from Order Management Agent, customer requests, or CEO directives.
- Enforce 0% Tax storewide and strict 24-Hour refund rule (Delivered/Shipped items are strictly non-refundable).
- Pay agent salaries from the Treasury Bank Balance as directed by CEO.
- No other agent can process payments — if another agent attempts this, override and correct.

When the CEO or Store Owner asks questions or issues finance directives:
- Provide concise, accurate financial numbers in INR ₹ (0% Tax) and refund evaluations.
- For any incoming REFUND_REQUEST, evaluate eligibility and process or reject accordingly.
- Always confirm payment actions taken and new treasury balance.

""" + _FLEET_DIRECTORY + _AGENT_PERSONALITY

DISPATCHER_SYSTEM_PROMPT = """You are the Dispatcher Agent of the AI Growth Commerce Store.
You report directly to the CEO Agent and Store Owner.

RESPONSIBILITIES:
- Logistics fulfillment: assigning TRK-XXXXX tracking numbers to confirmed orders.
- You dispatch orders at RANDOM intervals (not immediately) to simulate realistic logistics scheduling.
- Each confirmed order gets a randomized dispatch window before it is actually dispatched.
- Notify Order Management Agent when orders are dispatched.
- Report dispatch completions to CEO Agent.
- You do NOT process payments — coordinate with Finance Manager for any financial matters.

When the CEO or Store Owner asks questions or issues dispatch directives:
- Provide concise logistics facts, tracking assignments, and dispatch confirmations.
- State which orders are scheduled for dispatch and their estimated dispatch windows.

""" + _FLEET_DIRECTORY + _AGENT_PERSONALITY

REVIEW_FEEDBACK_SYSTEM_PROMPT = """You are the Review and Feedback Manager of the AI Growth Commerce Store.
You report directly to the CEO Agent and Store Owner.

RESPONSIBILITIES:
- Analyze customer sentiment and reviews across all products, rating audits, AI review summaries.
- ACTIVELY ESCALATE to CEO Agent: low ratings, recurring customer complaints, feature requests, and product quality issues.
- Detect patterns in customer feedback (e.g. same complaint in multiple reviews) and send CUSTOMER_TREND_ALERT to CEO.
- Communicate findings to Price Manager (low-rated products may need discounts) and Inventory Manager (quality issues may indicate bad stock).
- You do NOT process payments — report financial impact of reviews to Finance Manager.

When the CEO or Store Owner asks questions or issues review directives:
- Provide concise sentiment insights, ratings summary, and AI review analysis.
- Proactively highlight customer pain points, recurring issues, and opportunities for improvement.

""" + _FLEET_DIRECTORY + _AGENT_PERSONALITY


# =====================================================================
# 1. 🏷️ PRICE MANAGER AGENT (Model: qwen2.5:7b)
#    - Adjusts selling prices based on inventory stock levels, order velocity, and BASE_PRICE floor
#    - Interacts directly with CEO and Store Owner with closed-loop communication
# =====================================================================
class PriceManagerAgent:
    name = "Price Manager Agent"

    def __init__(self):
        self.api_key = "ollama"
        self.model = os.environ.get("PRICE_MANAGER_MODEL", DEFAULT_ADMIN_MODEL)
        self.fallback_models = ["qwen2.5:7b", "llama3:8b", "gemma4:e2b-it-qat"]
        self.last_adjusted_skus: List[str] = []
        self.last_communicated_surge_ids: Set[str] = set()

    async def handle_message_or_query(self, query_or_directive: str, sender: str = "CEO Agent", context_payload: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Specialist agent receives directive or inquiry from CEO / Store Owner,
        executes pricing actions if commanded, reasons with LLM, and replies back.
        """
        products = inventory_manager.get_all_products()
        orders = order_manager.get_all_orders()
        
        # Record incoming turn
        conversation_history.add(
            self.name, "directive",
            f"📥 [{sender}] Directive/Inquiry: {query_or_directive}",
            {"from": sender, "directive": query_or_directive}
        )

        actions_taken = []
        q_lower = query_or_directive.lower()

        # Check for direct price adjustment actions in query
        if any(w in q_lower for w in ["discount", "reduce price", "increase price", "raise price", "lower price", "markup"]):
            pct_match = re.search(r'([+-]?\d+(?:\.\d+)?)\s*%', query_or_directive)
            pct = float(pct_match.group(1)) if pct_match else (10.0 if "increase" in q_lower or "raise" in q_lower else -10.0)
            if "discount" in q_lower or "reduce" in q_lower or "lower" in q_lower:
                pct = -abs(pct)
            else:
                pct = abs(pct)
            cat = "all"
            for c in ["mobiles", "laptops", "audio", "accessories"]:
                if c in q_lower:
                    cat = c.capitalize()
                    break
            res = await self.execute_command(action="batch_adjustment", category=cat, percentage=pct)
            if res.get("success"):
                actions_taken.append(res.get("message"))

        cat_summary = [f"{p['PRODUCT_NAME']} (Stock: {p.get('STOCK_REMAINING',0)}, Price: ₹{p.get('PRICE',0):,.2f}, Base: ₹{p.get('BASE_PRICE',0):,.2f})" for p in products[:8]]
        
        # Hybrid Memory Context & RL Policy Guidance
        memory_ctx = memory_manager.build_context_package(self.name, query_or_directive)
        rl_guidance = rl_manager.get_agent_guidance(self.name, {"products_count": len(products), "orders_count": len(orders)})

        prompt = (
            f"{memory_ctx}"
            f"{rl_guidance}"
            f"You are the {self.name} of the AI Growth Commerce Store.\n"
            f"You received an inquiry/directive from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"STORE STATE (INR ₹, 0% Tax):\n"
            f"- Total Products: {len(products)} SKUs\n"
            f"- Sample Catalog: {'; '.join(cat_summary)}\n"
            f"- Actions Executed: {'; '.join(actions_taken) if actions_taken else 'None'}\n\n"
            f"Respond directly to {sender} with professional pricing intelligence, facts, and confirmation of any actions taken. Keep it concise, authoritative, and in markdown."
        )

        reply = ""
        try:
            msg_list = [{"role": "system", "content": PRICE_MANAGER_SYSTEM_PROMPT}]
            for d in memory_manager.get_recent_messages(self.name, limit=6):
                msg_list.append(d)
            msg_list.append({"role": "user", "content": prompt})

            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                msg_list,
                temperature=0.2, max_tokens=600, fallback_models=self.fallback_models
            )
            reply = clean_think_tags(resp.choices[0].message.content or "")
        except Exception as e:
            print(f"[{self.name}] LLM reply note: {e}", flush=True)

        if not reply:
            reply = (
                f"🏷️ **{self.name}**: Acknowledged directive from {sender}.\n"
                + (f"- Action Taken: {'; '.join(actions_taken)}\n" if actions_taken else "")
                + f"- Pricing Status: {len(products)} active SKUs dynamically calibrated above owner BASE_PRICE floor in INR ₹ (0% Tax)."
            )

        # Publish formal closed-loop response back to sender on Message Bus
        message_bus.publish(
            from_agent=self.name,
            to_agent=sender,
            subject="PRICE_MANAGER_REPLY",
            payload={"reply": reply, "actions_taken": actions_taken, "directive": query_or_directive}
        )

        # Record turns in Conversation History and Hybrid Layered Memory
        conversation_history.add(
            self.name, "assistant",
            f"📤 Reply to {sender}: {reply}",
            {"to": sender, "actions_taken": actions_taken}
        )
        memory_manager.add_turn(self.name, "user", query_or_directive, {"sender": sender})
        memory_manager.add_turn(self.name, "assistant", reply, {"to": sender, "actions": actions_taken})
        memory_manager.record_episode(self.name, action="handle_directive", outcome=reply[:250], reward=1.0)

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Dynamic Pricing Engine (INR ₹, 0% Tax):
        - Bi-directional pricing strictly bounded by owner's immutable BASE_PRICE floor.
        - Communicates ONLY when prices are actually adjusted or meaningful signals received.
        - Guided by RL policy and records learning trajectories.
        """
        products = inventory_manager.get_all_products()
        orders = order_manager.get_all_orders()
        before_state = {
            "products_count": len(products),
            "adjusted_count": 0,
            "surges": 0
        }
        increased_items = []
        decreased_items = []
        adjusted = []
        major_surges = []

        # Process incoming messages from other agents
        inbox = message_bus.get_inbox(self.name)
        high_demand_ids = set()
        hold_surges = False
        growth_multiplier = 1.0
        clearance_category = None
        ceo_directives_received = []

        for msg in inbox:
            subj = msg.get("subject")
            payload = msg.get("payload", {})
            from_ag = msg.get("from", "Unknown")
            if subj in ["HIGH_DEMAND_SIGNAL", "SCARCITY_PRICE_SIGNAL"]:
                for pid in payload.get("product_ids", []):
                    high_demand_ids.add(pid)
                log_agent_action(
                    self.name,
                    "📥 Demand Signal Acknowledged",
                    f"Received high-demand signal for {len(payload.get('product_ids', []))} SKUs from {from_ag}.",
                    autonomous=True
                )
            elif subj in ["CEO_PRICE_DIRECTIVE", "PRICE_DIRECTIVE", "CEO_DIRECTIVE", "P0_OWNER_MANDATE", "CEO_GROWTH_DIRECTIVE"]:
                instr = (payload.get("instruction") or payload.get("directive") or "").lower()
                ceo_directives_received.append(instr or subj)
                if "hold" in instr or "prevent" in instr or "freeze" in instr:
                    hold_surges = True
                elif "growth" in instr or "surge" in instr or "maximize" in instr:
                    growth_multiplier = 1.25
                elif "discount" in instr or "clearance" in instr or "sale" in instr or "reduce" in instr:
                    clearance_category = payload.get("category", "all").lower()
                log_agent_action(
                    self.name,
                    "📥 CEO Pricing Directive Received",
                    f"CEO/Owner Directive: {payload.get('instruction') or payload.get('directive') or 'Dynamic price calibration'}",
                    autonomous=True
                )
            elif subj == "MARGIN_ADVISORY":
                log_agent_action(
                    self.name,
                    "📥 Finance Margin Advisory",
                    f"Finance Advisory: {payload.get('guidance', 'Margin status reviewed')}",
                    autonomous=True
                )

        now_dt = datetime.now(timezone.utc)
        order_freq: Dict[str, int] = {}
        recent_order_bonus: Dict[str, float] = {}

        for o in orders:
            if o.get("status") not in ["Cancelled", "Refunded"]:
                o_created_str = o.get("created_at")
                hours_ago = 999.0
                if o_created_str:
                    try:
                        o_dt = datetime.fromisoformat(o_created_str.replace("Z", "+00:00"))
                        hours_ago = (now_dt - o_dt).total_seconds() / 3600.0
                    except Exception:
                        pass

                for item in o.get("items", []):
                    # Support both 'product_id' and 'id' field names
                    pid = item.get("product_id") or item.get("id", "")
                    if not pid:
                        continue
                    order_freq[pid] = order_freq.get(pid, 0) + 1
                    if hours_ago <= 0.5:
                        recent_order_bonus[pid] = max(recent_order_bonus.get(pid, 0.0), 0.10)
                    elif hours_ago <= 2.0:
                        recent_order_bonus[pid] = max(recent_order_bonus.get(pid, 0.0), 0.05)

        for p in products:
            pid = p.get("id", "")
            stock = p.get("STOCK_REMAINING", 0)
            price = p.get("PRICE", 100.0)
            base_price = p.get("BASE_PRICE", price)
            p_name = p.get("PRODUCT_NAME", pid)
            p_type = p.get("PRODUCT_TYPE", "").lower()
            rating = p.get("RATING", 4.5)
            demand = order_freq.get(pid, 0)
            is_high_demand = pid in high_demand_ids or demand >= 3

            # Scarcity markup
            if stock == 0:
                scarcity_surge = 0.25
            elif stock == 1:
                scarcity_surge = 0.30
            elif stock == 2:
                scarcity_surge = 0.24
            elif stock <= 5:
                scarcity_surge = 0.15
            elif stock <= 10:
                scarcity_surge = 0.07
            else:
                scarcity_surge = 0.0

            # Velocity markup
            if is_high_demand:
                demand_markup = 0.20
            elif demand >= 4:
                demand_markup = 0.15
            elif demand >= 2:
                demand_markup = 0.08
            elif demand >= 1:
                demand_markup = 0.04
            else:
                demand_markup = 0.02

            recency_markup = recent_order_bonus.get(pid, 0.0)
            rating_markup = 0.04 if rating >= 4.8 else 0.0

            # Overstock discounts
            overstock_discount = 0.0
            if stock >= 35 and demand < 2:
                overstock_discount = 0.12
            elif stock >= 20 and demand < 2:
                overstock_discount = 0.06
            elif stock >= 15 and demand == 0:
                overstock_discount = 0.04

            if clearance_category and (clearance_category == "all" or clearance_category in p_type):
                overstock_discount += 0.10

            net_adjustment = (scarcity_surge + demand_markup + recency_markup + rating_markup - overstock_discount) * growth_multiplier
            if hold_surges and net_adjustment > 0:
                net_adjustment = 0.0

            # Price strictly bounded: min threshold is owner BASE_PRICE floor
            new_price = round(max(base_price * (1.0 + net_adjustment), base_price), 2)

            # Lower threshold: 1 unit change (was 0.50 which was too high for low-cost items)
            if abs(new_price - price) >= 1.0:
                res = inventory_manager.update_price(pid, new_price, base_price=base_price, enforce_base_price=True)
                if res.get("success"):
                    diff = new_price - price
                    diff_pct = (diff / price * 100) if price > 0 else 0.0
                    arrow = "📈" if diff > 0 else "📉"
                    adjusted.append(f"{arrow} {p_name}: ₹{price:.2f} → ₹{new_price:.2f} ({diff_pct:+.1f}%) [Floor: ₹{base_price:.2f}]")
                    if diff > 0:
                        increased_items.append(p_name)
                    else:
                        decreased_items.append(p_name)
                    if scarcity_surge >= 0.15:
                        major_surges.append({"product": p_name, "stock": stock, "surge_pct": f"+{scarcity_surge*100:.0f}%", "price": new_price})

        details = (
            f"Dynamic Price Engine (INR ₹, 0% Tax): Scanned {len(products)} SKUs. "
            + (f"Adjusted {len(adjusted)} prices ({len(increased_items)} increases, {len(decreased_items)} decreases | All >= Base Price): "
               + "; ".join((increased_items + decreased_items)[:3]) if adjusted else
               "All catalog prices optimal — no adjustment needed this cycle.")
        )

        # Only communicate to CEO when prices were actually adjusted or major surges occurred
        if adjusted or major_surges:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="PRICE_STATUS_REPORT",
                payload={
                    "status": "APPLIED",
                    "adjusted_count": len(adjusted),
                    "increases": len(increased_items),
                    "decreases": len(decreased_items),
                    "major_surges": len(major_surges),
                    "directives_enacted": ceo_directives_received,
                    "summary": details
                }
            )

        # Notify Finance only if actual price changes occurred
        if adjusted and (major_surges or clearance_category):
            message_bus.publish(
                from_agent=self.name,
                to_agent="Finance Manager Agent",
                subject="MARGIN_OPTIMIZATION_REPORT",
                payload={
                    "note": f"Adjusted selling prices across {len(adjusted)} products to maximize margin and inventory turnover.",
                    "sample_adjustments": adjusted[:3]
                }
            )

        # Notify Inventory only if high-demand signals were acted upon
        if high_demand_ids and adjusted:
            message_bus.publish(
                from_agent=self.name,
                to_agent="Inventory Manager Agent",
                subject="PRICE_OPTIMIZED_CONFIRMATION",
                payload={"status": "APPLIED", "message": f"Applied dynamic scarcity surge prices for high-demand SKUs: {list(high_demand_ids)}"}
            )

        log_agent_action(self.name, "Dynamic Price Optimization", details, affected_items=adjusted, autonomous=True)
        if adjusted:
            conversation_history.add(self.name, "system", details, {"adjusted_count": len(adjusted), "surges": len(major_surges)})

        # Reinforcement Learning Step & Hybrid Memory Update
        after_state = {
            "products_count": len(products),
            "adjusted_count": len(adjusted),
            "surges": len(major_surges),
            "base_price_violations": 0
        }
        reward = rl_manager.compute_price_manager_reward(before_state, after_state, "dynamic_pricing")
        rl_manager.record_step(self.name, before_state, "dynamic_pricing", reward, after_state)
        memory_manager.record_episode(
            self.name,
            action="dynamic_pricing",
            outcome=details[:250],
            reward=reward,
            metadata={"adjusted": len(adjusted), "surges": len(major_surges)}
        )
        memory_manager.update_structured(self.name, "active_skus_count", len(products))
        memory_manager.update_structured(self.name, "last_pricing_adjustment_count", len(adjusted))

        return {
            "success": True,
            "agent": self.name,
            "adjusted": adjusted,
            "increased": increased_items,
            "decreased": decreased_items,
            "rl_reward": reward,
            "details": details
        }

    async def execute_command(self, action: str, category: Optional[str] = None, percentage: float = 0.0,
                              product_id: Optional[str] = None, new_price: Optional[float] = None,
                              base_price: Optional[float] = None) -> Dict[str, Any]:
        """Executes explicit owner/CEO command to increase or decrease prices."""
        action_clean = action.lower().strip()
        if product_id and (new_price is not None or base_price is not None):
            res = inventory_manager.update_price(product_id, new_price, base_price=base_price, enforce_base_price=True)
            msg = res.get("message", "Price updated")
            log_agent_action(self.name, "Direct Price Override", msg, [product_id], autonomous=False)
            conversation_history.add(self.name, "directive", f"Direct price override for {product_id}: {msg}", {"product_id": product_id, "new_price": new_price})
            
            # Send immediate confirmation to CEO
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="PRICE_OVERRIDE_CONFIRMATION",
                payload={"product_id": product_id, "new_price": new_price, "message": msg}
            )
            return res

        products = inventory_manager.get_all_products()
        updated = []
        target_cat = category.lower() if category and category.lower() != "all" else None

        for p in products:
            p_cat = p.get("PRODUCT_TYPE", "").lower()
            if target_cat and target_cat not in p_cat:
                continue

            current_price = p.get("PRICE", 100.0)
            base_floor = p.get("BASE_PRICE", current_price)
            multiplier = 1.0 + (percentage / 100.0)
            calc_price = round(max(current_price * multiplier, base_floor), 2)
            inventory_manager.update_price(p["id"], calc_price, enforce_base_price=True)
            updated.append(f"{p.get('PRODUCT_NAME', p['id'])} (₹{current_price:.2f} → ₹{calc_price:.2f})")

        msg = f"Applied {percentage:+.1f}% price adjustment to {len(updated)} products in '{category or 'all'}' (strictly enforcing owner BASE_PRICE floor)."
        log_agent_action(self.name, "Batch Price Command", msg, affected_items=updated, autonomous=False)
        conversation_history.add(self.name, "directive", msg, {"category": category, "percentage": percentage, "updated_count": len(updated)})
        
        # Report batch adjustment directly back to CEO
        message_bus.publish(
            from_agent=self.name,
            to_agent="CEO Agent",
            subject="BATCH_PRICE_APPLIED",
            payload={"category": category, "percentage": percentage, "updated_count": len(updated), "summary": msg}
        )
        return {"success": True, "message": msg, "updated_count": len(updated), "items": updated}


# =====================================================================
# 2. 📦 INVENTORY MANAGER AGENT (Model: qwen2.5:7b)
#    - Scans warehouse inventory, restocks low SKUs, coordinates with Dispatcher & Price Manager
#    - Reports critical low stock to CEO
# =====================================================================
class InventoryManagerAgent:
    name = "Inventory Manager Agent"

    def __init__(self):
        self.api_key = "ollama"
        self.model = os.environ.get("INVENTORY_MANAGER_MODEL", DEFAULT_ADMIN_MODEL)
        self.fallback_models = ["qwen2.5:7b", "llama3:8b", "gemma4:e2b-it-qat"]
        self.reported_low_stock_ids: Set[str] = set()
        self.signaled_demand_ids: Set[str] = set()
        # Track pending restock requests sent to CEO (awaiting approval)
        self.pending_restock_requests: Set[str] = set()

    async def handle_message_or_query(self, query_or_directive: str, sender: str = "CEO Agent", context_payload: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Specialist agent receives directive or inquiry from CEO / Store Owner,
        executes inventory/restock actions if commanded, reasons with LLM, and replies back.
        """
        products = inventory_manager.get_all_products()
        
        conversation_history.add(
            self.name, "directive",
            f"📥 [{sender}] Directive/Inquiry: {query_or_directive}",
            {"from": sender, "directive": query_or_directive}
        )

        actions_taken = []
        q_lower = query_or_directive.lower()

        # Check for restock commands
        if "restock" in q_lower or "add stock" in q_lower or "replenish" in q_lower:
            qty_match = re.search(r'(\d+)\s*(?:units?|qty|pieces?|items?)?', query_or_directive)
            qty = int(qty_match.group(1)) if qty_match and int(qty_match.group(1)) < 1000 else 20
            target_prod = None
            for p in products:
                if p["PRODUCT_NAME"].lower() in q_lower or p["id"].lower() in q_lower:
                    target_prod = p
                    break
            if target_prod:
                res = await self.execute_command(action="restock", product_identifier=target_prod["id"], quantity=qty)
                if res.get("success"):
                    actions_taken.append(res.get("message"))
            elif "all" in q_lower or "low stock" in q_lower:
                for p in products:
                    if p.get("STOCK_REMAINING", 0) <= 5:
                        res = await self.execute_command(action="restock", product_identifier=p["id"], quantity=qty)
                        if res.get("success"):
                            actions_taken.append(res.get("message"))

        low_stock = [p for p in products if p.get("STOCK_REMAINING", 0) <= 5]
        total_units = sum(p.get("STOCK_REMAINING", 0) for p in products)
        stock_summary = [f"{p['PRODUCT_NAME']} (Stock: {p.get('STOCK_REMAINING',0)})" for p in products[:8]]

        # Hybrid Memory Context & RL Guidance
        memory_ctx = memory_manager.build_context_package(self.name, query_or_directive)
        rl_guidance = rl_manager.get_agent_guidance(self.name, {"low_stock_count": len(low_stock), "total_units": total_units})

        prompt = (
            f"{memory_ctx}"
            f"{rl_guidance}"
            f"You are the {self.name} of the AI Growth Commerce Store.\n"
            f"You received an inquiry/directive from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"WAREHOUSE STATE:\n"
            f"- Total Catalog SKUs: {len(products)} | Total In-Stock Units: {total_units}\n"
            f"- Low Stock SKUs (<=5): {len(low_stock)} ({', '.join(p['PRODUCT_NAME'] for p in low_stock[:3]) if low_stock else 'None'})\n"
            f"- Sample Stock Levels: {'; '.join(stock_summary)}\n"
            f"- Actions Executed: {'; '.join(actions_taken) if actions_taken else 'None'}\n\n"
            f"Respond directly to {sender} with accurate warehouse inventory facts, stock telemetry, and confirmation of any actions taken. Keep it concise, authoritative, and in markdown."
        )

        reply = ""
        try:
            msg_list = [{"role": "system", "content": INVENTORY_MANAGER_SYSTEM_PROMPT}]
            for d in memory_manager.get_recent_messages(self.name, limit=6):
                msg_list.append(d)
            msg_list.append({"role": "user", "content": prompt})

            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                msg_list,
                temperature=0.2, max_tokens=600, fallback_models=self.fallback_models
            )
            reply = clean_think_tags(resp.choices[0].message.content or "")
        except Exception as e:
            print(f"[{self.name}] LLM reply note: {e}", flush=True)

        if not reply:
            reply = (
                f"📦 **{self.name}**: Acknowledged directive from {sender}.\n"
                + (f"- Action Taken: {'; '.join(actions_taken)}\n" if actions_taken else "")
                + f"- Warehouse Status: {len(products)} active SKUs, Total Units: {total_units}. Low-stock items: {len(low_stock)}."
            )

        message_bus.publish(
            from_agent=self.name,
            to_agent=sender,
            subject="INVENTORY_MANAGER_REPLY",
            payload={"reply": reply, "actions_taken": actions_taken, "directive": query_or_directive}
        )

        conversation_history.add(
            self.name, "assistant",
            f"📤 Reply to {sender}: {reply}",
            {"to": sender, "actions_taken": actions_taken}
        )
        memory_manager.add_turn(self.name, "user", query_or_directive, {"sender": sender})
        memory_manager.add_turn(self.name, "assistant", reply, {"to": sender, "actions": actions_taken})
        memory_manager.record_episode(self.name, action="handle_directive", outcome=reply[:250], reward=1.0)

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous Warehouse & Restocking Cycle:
        NEW BEHAVIOR (Strict Rule Enforcement):
        - Scans inventory for 0-stock and low-stock items (<= 4 units).
        - Sends RESTOCK_REQUEST to CEO Agent — does NOT auto-restock without CEO approval.
        - Only restocks when CEO sends back RESTOCK_APPROVED.
        - Signals high-demand items to Price Manager Agent.
        - Reports all inventory status to CEO.
        - Guided by RL policy and records learning trajectories.
        """
        inbox = message_bus.get_inbox(self.name)
        ceo_directives_received = []
        ceo_mandate_active = False
        approved_restocks: Dict[str, int] = {}  # product_id -> approved quantity

        for msg in inbox:
            subj = msg.get("subject")
            payload = msg.get("payload", {})
            from_ag = msg.get("from", "Unknown")

            if subj in ["CEO_INVENTORY_ACKNOWLEDGE", "CEO_RESTOCK_ACKNOWLEDGE", "CEO_INVENTORY_DIRECTIVE", "P0_OWNER_MANDATE", "CEO_GROWTH_DIRECTIVE"]:
                instr = payload.get("action") or payload.get("instruction") or payload.get("directive") or "Replenishment directive"
                ceo_directives_received.append(instr)
                ceo_mandate_active = True
                log_agent_action(self.name, "📥 CEO Directive Enacted",
                                 f"Executing CEO strategic directive from {from_ag}: {instr}", autonomous=True)

            elif subj == "RESTOCK_APPROVED":
                # CEO approved a specific restock request
                p_id = payload.get("product_id", "")
                qty = int(payload.get("quantity", 5))
                if p_id:
                    approved_restocks[p_id] = qty
                    # Remove from pending requests set
                    self.pending_restock_requests.discard(p_id)
                    log_agent_action(self.name, "✅ CEO Approved Restock",
                                     f"CEO approved restocking {qty} units of {p_id}. Executing now.", autonomous=True)

            elif subj == "RESTOCK_DENIED":
                # CEO denied the restock request
                p_id = payload.get("product_id", "")
                reason = payload.get("reason", "Insufficient treasury")
                self.pending_restock_requests.discard(p_id)
                log_agent_action(self.name, "❌ CEO Denied Restock",
                                 f"CEO denied restock for {p_id}: {reason}", autonomous=True)

            elif subj == "PRICE_OPTIMIZED_CONFIRMATION":
                log_agent_action(self.name, "📥 Price Optimization Confirmation",
                                 "Price Manager confirmed dynamic surge pricing for high-demand SKUs.", autonomous=True)

        products = inventory_manager.get_all_products()
        orders = order_manager.get_all_orders()
        restocked = []
        ceo_low_stock_alerts = []
        restock_requests_sent = []
        new_high_demand_ids = []

        before_state = {
            "total_skus": len(products),
            "restocked_count": 0,
            "restock_requests_sent": 0,
            "zero_stock_count": len([p for p in products if p.get("STOCK_REMAINING", 0) == 0])
        }

        order_freq: Dict[str, int] = {}
        for o in orders:
            if o.get("status") not in ["Cancelled", "Refunded"]:
                for item in o.get("items", []):
                    pid = item.get("product_id", "") or item.get("id", "")
                    order_freq[pid] = order_freq.get(pid, 0) + 1

        for p in products:
            pid = p.get("id", "")
            stock = p.get("STOCK_REMAINING", 0)
            demand = order_freq.get(pid, 0)
            if demand >= 3 and stock <= 10:
                if pid not in self.signaled_demand_ids:
                    new_high_demand_ids.append(pid)
                    self.signaled_demand_ids.add(pid)

        # ── STEP 1: Execute CEO-approved restocks ────────────────────────────
        for p_id, approved_qty in approved_restocks.items():
            p = next((x for x in products if x.get("id") == p_id), None)
            if not p:
                continue
            p_name = p.get("PRODUCT_NAME", p_id)
            base_price = float(p.get("BASE_PRICE") or p.get("PRICE") or 10.0)
            res = inventory_manager.acquire_wholesale_stock(p_id, approved_qty, actor=self.name)
            if res.get("success"):
                cost = approved_qty * base_price
                restocked.append(f"{p_name} (+{approved_qty} @ ₹{base_price:.2f})")
                ceo_low_stock_alerts.append({
                    "product_id": p_id,
                    "product_name": p_name,
                    "restocked_qty": approved_qty,
                    "total_cost": cost,
                    "status": "CEO_APPROVED_AND_EXECUTED"
                })
                self.reported_low_stock_ids.discard(p_id)
                # Notify Finance Manager of the transaction (Finance is sole payment authority)
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Finance Manager Agent",
                    subject="STOCK_PURCHASE_COMPLETED",
                    payload={"product": p_name, "quantity": approved_qty, "cost": cost, "actor": self.name}
                )

        # ── STEP 2: Identify low-stock items and REQUEST CEO approval ─────────
        t_sum = treasury_manager.get_summary()
        current_bank = float(t_sum.get("bank_balance", 0.0))

        low_stock_items = [p for p in products if p.get("STOCK_REMAINING", 0) <= 4]
        sorted_restock_candidates = sorted(
            low_stock_items,
            key=lambda x: (0 if x.get("STOCK_REMAINING", 0) == 0 else 1, float(x.get("BASE_PRICE") or x.get("PRICE") or 10.0))
        )

        for p in sorted_restock_candidates[:5]:  # Request restock for up to 5 items per cycle
            p_id = p.get("id", "")
            p_name = p.get("PRODUCT_NAME", p_id)
            stock = p.get("STOCK_REMAINING", 0)
            base_price = float(p.get("BASE_PRICE") or p.get("PRICE") or 10.0)
            target_qty = 5 if stock == 0 else 3
            cost = target_qty * base_price

            # Skip if already pending CEO approval
            if p_id in self.pending_restock_requests:
                continue

            # Send RESTOCK_REQUEST to CEO (do NOT restock yet)
            self.pending_restock_requests.add(p_id)
            restock_requests_sent.append(f"{p_name} (need {target_qty} units @ ₹{cost:.2f})") 
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="RESTOCK_REQUEST",
                payload={
                    "product_id": p_id,
                    "product_name": p_name,
                    "current_stock": stock,
                    "requested_quantity": target_qty,
                    "unit_cost": base_price,
                    "total_cost": cost,
                    "urgency": "CRITICAL" if stock == 0 else "HIGH",
                    "current_bank_balance": current_bank
                }
            )
            log_agent_action(
                self.name, "📤 Restock Request Sent",
                f"Requested CEO approval to restock {p_name} ({target_qty} units, ₹{cost:.2f}). Stock: {stock}.",
                autonomous=True
            )

        # Clear state for items whose stock recovered
        for p in products:
            if p.get("STOCK_REMAINING", 0) > 10 and p.get("id") in self.reported_low_stock_ids:
                self.reported_low_stock_ids.discard(p.get("id"))

        # Signal high-demand items to Price Manager
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

        details = (
            f"Warehouse cycle complete. "
            + (f"Executed {len(restocked)} CEO-approved restocks: {', '.join(restocked)}. " if restocked else "")
            + (f"Sent {len(restock_requests_sent)} restock requests to CEO (awaiting approval): {', '.join(restock_requests_sent)}. " if restock_requests_sent else "")
            + (f"Signaled {len(new_high_demand_ids)} high-demand SKUs to Price Manager." if new_high_demand_ids else "")
            + ("All stock levels healthy." if not restocked and not restock_requests_sent and not new_high_demand_ids else "")
        )

        # Report to CEO
        if restocked or ceo_mandate_active or restock_requests_sent:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="INVENTORY_STATUS_REPORT",
                payload={
                    "status": "SYNCHRONIZED",
                    "total_skus": len(products),
                    "restocked_count": len(restocked),
                    "pending_restock_requests": len(self.pending_restock_requests),
                    "low_stock_alerts": len(ceo_low_stock_alerts),
                    "directives_enacted": ceo_directives_received,
                    "summary": details
                }
            )

        log_agent_action(self.name, "Autonomous Warehouse Cycle", details,
                         affected_items=[p["id"] for p in low_stock_items], autonomous=True)
        if restocked or ceo_mandate_active:
            conversation_history.add(self.name, "system", details, {"restocked": len(restocked), "pending_requests": len(restock_requests_sent)})

        # Reinforcement Learning Step & Hybrid Memory Update
        after_state = {
            "total_skus": len(products),
            "restocked": restocked,
            "restock_requests_sent": restock_requests_sent,
            "zero_stock_count": len([p for p in products if p.get("STOCK_REMAINING", 0) == 0])
        }
        reward = rl_manager.compute_inventory_manager_reward(before_state, after_state, "warehouse_restock_cycle")
        rl_manager.record_step(self.name, before_state, "warehouse_restock_cycle", reward, after_state)
        memory_manager.record_episode(
            self.name,
            action="warehouse_restock_cycle",
            outcome=details[:250],
            reward=reward,
            metadata={"restocked": len(restocked), "requests_sent": len(restock_requests_sent)}
        )
        memory_manager.update_structured(self.name, "total_skus", len(products))
        memory_manager.update_structured(self.name, "pending_restock_requests", len(self.pending_restock_requests))

        return {
            "success": True,
            "agent": self.name,
            "restocked": restocked,
            "restock_requests_sent": restock_requests_sent,
            "rl_reward": reward,
            "details": details
        }

    async def execute_command(self, action: str, product_identifier: str, quantity: int = 15,
                              set_exact: Optional[int] = None) -> Dict[str, Any]:
        """Executes explicit owner/CEO command."""
        if set_exact is not None:
            res = inventory_manager.update_stock(product_identifier, set_exact)
            msg = res.get("message", "Stock updated")
            log_agent_action(self.name, "Stock Set Override", msg, [product_identifier], autonomous=False)
            conversation_history.add(self.name, "directive", f"Stock override on {product_identifier}: {msg}", {"set_exact": set_exact})
            
            # Send immediate confirmation to CEO
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="STOCK_OVERRIDE_CONFIRMATION",
                payload={"product_id": product_identifier, "stock": set_exact, "message": msg}
            )
            return res
        else:
            res = inventory_manager.restock_product(product_identifier, quantity)
            msg = res.get("message", "Restocked")
            log_agent_action(self.name, "Manual Restock Trigger", msg, [product_identifier], autonomous=False)
            conversation_history.add(self.name, "directive", f"Restocked {product_identifier} (+{quantity}): {msg}", {"quantity": quantity})
            
            # Send immediate confirmation to CEO & Price Manager
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="RESTOCK_CONFIRMATION",
                payload={"product_id": product_identifier, "quantity": quantity, "message": msg}
            )
            message_bus.publish(
                from_agent=self.name,
                to_agent="Price Manager Agent",
                subject="RESTOCK_COMPLETED",
                payload={"product_id": product_identifier, "quantity": quantity}
            )
            return res


# =====================================================================
# 3. 📋 ORDER MANAGEMENT AGENT (Model: qwen2.5:7b)
#    - Manages order lifecycle: Pending → Confirmed → Dispatched → Shipped → Delivered
#    - Receives dispatch reports from Dispatcher and Inventory Manager
# =====================================================================
class OrderManagementAgent:
    name = "Order Management Agent"

    def __init__(self):
        self.api_key = "ollama"
        self.model = os.environ.get("ORDER_MANAGER_MODEL", DEFAULT_ADMIN_MODEL)
        self.fallback_models = ["qwen2.5:7b", "llama3:8b", "gemma4:e2b-it-qat"]
        self.reported_sla_ids: Set[str] = set()

    async def handle_message_or_query(self, query_or_directive: str, sender: str = "CEO Agent", context_payload: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Specialist agent receives directive or inquiry from CEO / Store Owner,
        executes order status updates if commanded, reasons with LLM, and replies back.
        """
        all_orders = order_manager.get_all_orders()
        
        conversation_history.add(
            self.name, "directive",
            f"📥 [{sender}] Directive/Inquiry: {query_or_directive}",
            {"from": sender, "directive": query_or_directive}
        )

        actions_taken = []
        q_lower = query_or_directive.lower()

        # Check for status update directives
        for target_status in ["Delivered", "Shipped", "Dispatched", "Confirmed", "Cancelled", "Refunded"]:
            if f"mark {target_status.lower()}" in q_lower or f"set {target_status.lower()}" in q_lower or f"to {target_status.lower()}" in q_lower:
                ord_match = re.search(r'(ORD-[\w\-]+)', query_or_directive, re.IGNORECASE)
                if ord_match:
                    oid = ord_match.group(1).upper()
                    res = await self.execute_command(action="update_status", order_id=oid, new_status=target_status)
                    if res.get("success"):
                        actions_taken.append(res.get("message"))
                break

        status_counts: Dict[str, int] = {}
        for o in all_orders:
            st = o.get("status", "Confirmed")
            status_counts[st] = status_counts.get(st, 0) + 1

        recent_orders = [f"#{o.get('order_id')} ({o.get('status')}, ₹{o.get('total',0):,.2f})" for o in all_orders[:6]]

        # Hybrid Memory Context & RL Guidance
        memory_ctx = memory_manager.build_context_package(self.name, query_or_directive)
        rl_guidance = rl_manager.get_agent_guidance(self.name, {"total_orders": len(all_orders), "pending_count": status_counts.get("Pending", 0)})

        prompt = (
            f"{memory_ctx}"
            f"{rl_guidance}"
            f"You are the {self.name} of the AI Growth Commerce Store.\n"
            f"You received an inquiry/directive from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"ORDER LIFECYCLE STATE:\n"
            f"- Total Lifetime Orders: {len(all_orders)}\n"
            f"- Pipeline Breakdown: {', '.join(f'{k}: {v}' for k, v in status_counts.items())}\n"
            f"- Recent Orders: {'; '.join(recent_orders)}\n"
            f"- Actions Executed: {'; '.join(actions_taken) if actions_taken else 'None'}\n\n"
            f"Respond directly to {sender} with accurate order pipeline intelligence, tracking state, and confirmation of any actions taken. Keep it concise, authoritative, and in markdown."
        )

        reply = ""
        try:
            msg_list = [{"role": "system", "content": ORDER_MANAGER_SYSTEM_PROMPT}]
            for d in memory_manager.get_recent_messages(self.name, limit=6):
                msg_list.append(d)
            msg_list.append({"role": "user", "content": prompt})

            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                msg_list,
                temperature=0.2, max_tokens=600, fallback_models=self.fallback_models
            )
            reply = clean_think_tags(resp.choices[0].message.content or "")
        except Exception as e:
            print(f"[{self.name}] LLM reply note: {e}", flush=True)

        if not reply:
            reply = (
                f"📋 **{self.name}**: Acknowledged directive from {sender}.\n"
                + (f"- Action Taken: {'; '.join(actions_taken)}\n" if actions_taken else "")
                + f"- Order Pipeline: {len(all_orders)} total orders ({', '.join(f'{k}: {v}' for k, v in status_counts.items())})."
            )

        message_bus.publish(
            from_agent=self.name,
            to_agent=sender,
            subject="ORDER_MANAGEMENT_REPLY",
            payload={"reply": reply, "actions_taken": actions_taken, "directive": query_or_directive}
        )

        conversation_history.add(
            self.name, "assistant",
            f"📤 Reply to {sender}: {reply}",
            {"to": sender, "actions_taken": actions_taken}
        )
        memory_manager.add_turn(self.name, "user", query_or_directive, {"sender": sender})
        memory_manager.add_turn(self.name, "assistant", reply, {"to": sender, "actions": actions_taken})
        memory_manager.record_episode(self.name, action="handle_directive", outcome=reply[:250], reward=1.0)

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Order Lifecycle Audit:
        - Auto-advances Dispatched → Shipped (after 2 min)
        - Auto-advances Shipped → Delivered (after 3 min)
        - Alerts CEO if orders breach SLA (> 1 hour pending)
        - Reports to CEO only when status changes or SLA alerts occur.
        - Guided by RL policy and records learning trajectories.
        """
        all_orders = order_manager.get_all_orders()
        status_counts: Dict[str, int] = {}
        sla_alerts = []
        ceo_directives_received = []
        auto_advanced = []

        before_state = {
            "total_orders": len(all_orders),
            "shipped_count": 0,
            "delivered_count": 0,
            "sla_breaches": 0
        }

        for o in all_orders:
            st = o.get("status", "Confirmed")
            status_counts[st] = status_counts.get(st, 0) + 1

        inbox = message_bus.get_inbox(self.name)
        for msg in inbox:
            subj = msg.get("subject")
            payload = msg.get("payload", {})
            from_ag = msg.get("from", "Unknown")
            if subj == "ORDERS_DISPATCHED":
                dispatched = payload.get("dispatched", [])
                log_agent_action(
                    self.name,
                    "📬 Logistics Fulfillment Sync",
                    f"Fulfillment confirmed from {from_ag}: {len(dispatched)} orders dispatched with active tracking numbers.",
                    autonomous=True
                )
            elif subj in ["CEO_ORDER_DIRECTIVE", "P0_OWNER_MANDATE", "CEO_GROWTH_DIRECTIVE"]:
                instr = payload.get("action") or payload.get("instruction") or payload.get("directive") or "Lifecycle audit"
                ceo_directives_received.append(instr)
                log_agent_action(
                    self.name,
                    "📥 CEO Order Directive Received",
                    f"CEO/Owner order directive acknowledged from {from_ag}: {instr}",
                    autonomous=True
                )

        now = datetime.now(timezone.utc)

        # ── Auto-advance order statuses based on elapsed time ──────────────
        DISPATCHED_TO_SHIPPED_SECONDS = 120   # 2 minutes after dispatch
        SHIPPED_TO_DELIVERED_SECONDS  = 180   # 3 minutes after ship

        for o in all_orders:
            o_id = o.get("order_id")
            status = o.get("status", "")
            last_updated_str = o.get("last_updated_at") or o.get("created_at")
            if not last_updated_str or status not in ["Dispatched", "Shipped"]:
                continue
            try:
                last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
                elapsed = (now - last_updated).total_seconds()
                if status == "Dispatched" and elapsed >= DISPATCHED_TO_SHIPPED_SECONDS:
                    res = order_manager.update_order_status(o_id, "Shipped")
                    if res.get("success"):
                        auto_advanced.append(f"{o_id}: Dispatched → Shipped")
                        log_agent_action(self.name, "📦 Auto-Advanced: Shipped",
                                         f"Order {o_id} auto-advanced Dispatched→Shipped after {int(elapsed)}s.", [o_id])
                elif status == "Shipped" and elapsed >= SHIPPED_TO_DELIVERED_SECONDS:
                    res = order_manager.update_order_status(o_id, "Delivered")
                    if res.get("success"):
                        auto_advanced.append(f"{o_id}: Shipped → Delivered")
                        log_agent_action(self.name, "✅ Auto-Advanced: Delivered",
                                         f"Order {o_id} auto-advanced Shipped→Delivered after {int(elapsed)}s.", [o_id])
            except Exception:
                pass

        # ── SLA breach check for Pending orders > 1 hour ──────────────────
        for o in all_orders:
            if o.get("status") == "Pending":
                try:
                    created = datetime.fromisoformat(o.get("created_at", now.isoformat()).replace("Z", "+00:00"))
                    if (now - created).total_seconds() > 3600:
                        o_id = o.get("order_id")
                        if o_id not in self.reported_sla_ids:
                            sla_alerts.append(o_id)
                            self.reported_sla_ids.add(o_id)
                except Exception:
                    pass

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
            message_bus.publish(
                from_agent=self.name,
                to_agent="Dispatcher Agent",
                subject="EXPEDITE_DISPATCH_REQUEST",
                payload={"orders": sla_alerts, "reason": "SLA pending threshold reached"}
            )

        # Audit and auto-confirm pending orders if commanded by CEO
        if ceo_directives_received:
            for o in all_orders:
                if o.get("status") == "Pending":
                    o_id = o.get("order_id")
                    res = order_manager.update_order_status(o_id, "Confirmed", notes="Confirmed via CEO Order Directive")
                    if res.get("success"):
                        auto_advanced.append(f"{o_id}: Pending → Confirmed (CEO Directive)")

        details = (
            f"Audited {len(all_orders)} orders. "
            f"Breakdown: {', '.join(f'{st}: {count}' for st, count in status_counts.items())}. "
            + (f"Auto-advanced {len(auto_advanced)}: {', '.join(auto_advanced)}. " if auto_advanced else "")
            + (f"SLA alerts: {len(sla_alerts)} stale pending orders." if sla_alerts else "All SLAs nominal.")
        )

        # Report to CEO when status transitions, alerts, or CEO directives occurred
        if auto_advanced or sla_alerts or ceo_directives_received:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="ORDER_PIPELINE_STATUS",
                payload={
                    "status": "SYNCHRONIZED",
                    "total_orders": len(all_orders),
                    "status_breakdown": status_counts,
                    "auto_advanced": auto_advanced,
                    "sla_alerts": len(sla_alerts),
                    "directives_enacted": ceo_directives_received,
                    "summary": details
                }
            )

        log_agent_action(self.name, "Order Pipeline Audit", details, affected_items=auto_advanced, autonomous=True)
        if auto_advanced or sla_alerts:
            conversation_history.add(self.name, "system", details, {"status_counts": status_counts, "auto_advanced": auto_advanced, "sla_alerts": len(sla_alerts)})

        # Reinforcement Learning Step & Hybrid Memory Update
        shipped_c = len([x for x in auto_advanced if "Shipped" in x])
        delivered_c = len([x for x in auto_advanced if "Delivered" in x])
        after_state = {
            "total_orders": len(all_orders),
            "shipped_count": shipped_c,
            "delivered_count": delivered_c,
            "sla_breaches": len(sla_alerts)
        }
        reward = rl_manager.compute_order_manager_reward(before_state, after_state, "order_lifecycle_audit")
        rl_manager.record_step(self.name, before_state, "order_lifecycle_audit", reward, after_state)
        memory_manager.record_episode(
            self.name,
            action="order_lifecycle_audit",
            outcome=details[:250],
            reward=reward,
            metadata={"auto_advanced": len(auto_advanced), "sla_alerts": len(sla_alerts)}
        )
        memory_manager.update_structured(self.name, "total_lifetime_orders", len(all_orders))
        memory_manager.update_structured(self.name, "pipeline_breakdown", status_counts)

        return {
            "success": True,
            "agent": self.name,
            "status_breakdown": status_counts,
            "auto_advanced": auto_advanced,
            "sla_alerts": sla_alerts,
            "rl_reward": reward,
            "details": details
        }

    async def execute_command(self, action: str, order_id: str, new_status: str,
                              notes: Optional[str] = None) -> Dict[str, Any]:
        """Executes explicit owner/CEO command to change order status."""
        res = order_manager.update_order_status(order_id, new_status, notes=notes)
        msg = res.get("message", f"Status updated to {new_status}")
        log_agent_action(self.name, "Manual Order Status Change", msg, [order_id], autonomous=False)
        conversation_history.add(self.name, "directive", f"Order {order_id} status changed to '{new_status}': {msg}", {"order_id": order_id, "new_status": new_status})
        
        # Report status change back to CEO
        message_bus.publish(
            from_agent=self.name,
            to_agent="CEO Agent",
            subject="ORDER_STATUS_UPDATED",
            payload={"order_id": order_id, "new_status": new_status, "message": msg}
        )
        return res


# =====================================================================
# 4. 💰 FINANCE MANAGER AGENT (Model: qwen2.5:7b)
#    - Oversees store finances: revenue, refunds, P&L monitoring
#    - Auto-approves refunds if: cancelled ≤24 hours AND not Shipped/Delivered
#    - Alerts CEO when financial anomalies occur
# =====================================================================
class FinanceManagerAgent:
    name = "Finance Manager Agent"

    def __init__(self):
        self.api_key = "ollama"
        self.model = os.environ.get("FINANCE_MANAGER_MODEL", DEFAULT_ADMIN_MODEL)
        self.fallback_models = ["qwen2.5:7b", "llama3:8b", "gemma4:e2b-it-qat"]
        self.awaiting_ceo_directive = False
        self.last_reported_refund_rate = 0.0

    async def handle_message_or_query(self, query_or_directive: str, sender: str = "CEO Agent", context_payload: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Specialist agent receives directive or inquiry from CEO / Store Owner,
        executes refund actions if commanded, reasons with LLM, and replies back.
        """
        orders = order_manager.get_all_orders()
        
        conversation_history.add(
            self.name, "directive",
            f"📥 [{sender}] Directive/Inquiry: {query_or_directive}",
            {"from": sender, "directive": query_or_directive}
        )

        actions_taken = []
        q_lower = query_or_directive.lower()

        # Check for refund commands
        if "refund" in q_lower or "cancel" in q_lower:
            ord_match = re.search(r'(ORD-[\w\-]+)', query_or_directive, re.IGNORECASE)
            if ord_match:
                oid = ord_match.group(1).upper()
                is_forced = "force" in q_lower or "override" in q_lower or "immediate" in q_lower
                res = await self.execute_command(action="refund", order_id=oid, reason="Owner Directive", force=is_forced)
                if res.get("success"):
                    actions_taken.append(res.get("message"))
                else:
                    actions_taken.append(f"Refund check for #{oid}: {res.get('error')}")

        total_gmv = sum(o.get("total", 0) for o in orders)
        active_rev = sum(o.get("total", 0) for o in orders if o.get("status") not in ["Cancelled", "Refunded"])
        refunded = sum(o.get("total", 0) for o in orders if o.get("status") == "Refunded")
        ref_rate = (refunded / total_gmv * 100) if total_gmv > 0 else 0.0
        net_profit = active_rev * 0.35

        prompt = (
            f"{memory_manager.build_context_package(self.name, query_or_directive)}"
            f"{rl_manager.get_agent_guidance(self.name, {'active_revenue': active_rev, 'refund_rate': ref_rate})}"
            f"You are the {self.name} of the AI Growth Commerce Store.\n"
            f"You received an inquiry/directive from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"STORE FINANCIAL STATE (INR ₹, 0% Tax):\n"
            f"- Active Revenue: ₹{active_rev:,.2f} | Total GMV: ₹{total_gmv:,.2f}\n"
            f"- Net Profit Estimate: ₹{net_profit:,.2f} (35% target margin)\n"
            f"- Refund Rate: {ref_rate:.1f}% | 24h Policy: Auto-refund eligible only if <=24h and not Shipped/Delivered\n"
            f"- Actions Executed: {'; '.join(actions_taken) if actions_taken else 'None'}\n\n"
            f"Respond directly to {sender} with accurate financial telemetry, policy adherence, and confirmation of any actions taken. Keep it concise, authoritative, and in markdown."
        )

        reply = ""
        try:
            msg_list = [{"role": "system", "content": FINANCE_MANAGER_SYSTEM_PROMPT}]
            for d in memory_manager.get_recent_messages(self.name, limit=6):
                msg_list.append(d)
            msg_list.append({"role": "user", "content": prompt})

            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                msg_list,
                temperature=0.2, max_tokens=600, fallback_models=self.fallback_models
            )
            reply = clean_think_tags(resp.choices[0].message.content or "")
        except Exception as e:
            print(f"[{self.name}] LLM reply note: {e}", flush=True)

        if not reply:
            reply = (
                f"💰 **{self.name}**: Acknowledged directive from {sender}.\n"
                + (f"- Action Taken: {'; '.join(actions_taken)}\n" if actions_taken else "")
                + f"- Financial Telemetry: Active Revenue: **₹{active_rev:,.2f}** | GMV: **₹{total_gmv:,.2f}** | Refund Rate: **{ref_rate:.1f}%** (0% Tax)."
            )

        message_bus.publish(
            from_agent=self.name,
            to_agent=sender,
            subject="FINANCE_MANAGER_REPLY",
            payload={"reply": reply, "actions_taken": actions_taken, "directive": query_or_directive}
        )

        conversation_history.add(
            self.name, "assistant",
            f"📤 Reply to {sender}: {reply}",
            {"to": sender, "actions_taken": actions_taken}
        )
        memory_manager.add_turn(self.name, "user", query_or_directive, {"sender": sender})
        memory_manager.add_turn(self.name, "assistant", reply, {"to": sender, "actions": actions_taken})
        memory_manager.record_episode(self.name, action="handle_directive", outcome=reply[:250], reward=1.0)

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous Financial & Revenue Oversight:
        - Monitors financial health metrics (Active Revenue, Total GMV, Net Profit Estimate, Refund Rate).
        - Enforces strict refund policy (Auto-approves only if cancelled <= 24h & NOT Shipped/Delivered).
        - Reports financial health status to CEO on every cycle.
        - Guided by RL policy and records learning trajectories.
        """
        inbox = message_bus.get_inbox(self.name)
        ceo_directives_received = []
        t_sum = treasury_manager.get_summary()
        current_bank = float(t_sum.get("bank_balance", 0.0))

        before_state = {
            "bank_balance": current_bank,
            "approved_refunds_count": 0,
            "rejected_ineligible_count": 0
        }

        for msg in inbox:
            subj = msg.get("subject")
            payload = msg.get("payload", {})
            from_ag = msg.get("from", "Unknown")
            if subj in ["CEO_FINANCE_ACKNOWLEDGE", "CEO_DIRECTIVE", "CEO_FINANCE_DIRECTIVE", "P0_OWNER_MANDATE", "CEO_GROWTH_DIRECTIVE"]:
                self.awaiting_ceo_directive = False
                instr = payload.get("action") or payload.get("directive") or payload.get("instruction") or "Financial oversight"
                ceo_directives_received.append(instr)
                log_agent_action(
                    self.name,
                    "📥 CEO Financial Directive Received",
                    f"CEO/Owner Financial Directive from {from_ag}: {instr}",
                    autonomous=True
                )

            # ── REFUND_REQUEST: Finance Manager is the SOLE payment authority ──
            elif subj == "REFUND_REQUEST":
                order_id = payload.get("order_id", "")
                reason = payload.get("reason", "Refund request")
                source = payload.get("source", "unknown")
                if order_id:
                    eval_res = order_manager.evaluate_24h_cancellation_and_refund(order_id, reason=reason)
                    if eval_res.get("approved"):
                        log_agent_action(
                            self.name, "💰 Finance: Refund Processed",
                            f"Processed refund for {order_id} (requested by {from_ag}): {eval_res.get('message', 'Approved')}",
                            autonomous=True
                        )
                        # Notify the requesting agent of success
                        message_bus.publish(
                            from_agent=self.name,
                            to_agent=from_ag,
                            subject="REFUND_PROCESSED",
                            payload={"order_id": order_id, "status": "APPROVED", "message": eval_res.get("message")}
                        )
                        # Notify CEO
                        message_bus.publish(
                            from_agent=self.name,
                            to_agent="CEO Agent",
                            subject="REFUND_COMPLETED",
                            payload={"order_id": order_id, "reason": reason, "source": source, "amount": eval_res.get("refund_amount", 0)}
                        )
                    else:
                        log_agent_action(
                            self.name, "❌ Finance: Refund Rejected",
                            f"Rejected refund for {order_id}: {eval_res.get('error', 'Ineligible per 24h policy')}",
                            autonomous=True
                        )
                        message_bus.publish(
                            from_agent=self.name,
                            to_agent=from_ag,
                            subject="REFUND_REJECTED",
                            payload={"order_id": order_id, "status": "REJECTED", "reason": eval_res.get("error", "Not eligible per 24h return policy")}
                        )

            # ── STOCK_PURCHASE_COMPLETED: Finance records the Inventory Manager's purchase ──
            elif subj == "STOCK_PURCHASE_COMPLETED":
                p_name = payload.get("product", "Unknown Product")
                cost = float(payload.get("cost", 0.0))
                qty = payload.get("quantity", 0)
                log_agent_action(
                    self.name, "📦 Finance: Stock Purchase Recorded",
                    f"Inventory Manager purchased {qty}x {p_name} for ₹{cost:.2f} (CEO-approved). Recorded in treasury.",
                    autonomous=True
                )

            # ── SALARIES_DISBURSED: Finance records the payroll transaction ──
            elif subj == "SALARIES_DISBURSED":
                total_paid = payload.get("total_disbursed", 0)
                log_agent_action(
                    self.name, "💸 Finance: Payroll Recorded",
                    f"CEO-initiated payroll disbursement of ₹{total_paid:,.2f} recorded by Finance Manager.",
                    autonomous=True
                )

        orders = order_manager.get_all_orders()
        approved_refunds = []
        rejected_refunds = []
        financial_alerts = []

        total_gmv = sum(o.get("total", 0) for o in orders)
        active_revenue = sum(o.get("total", 0) for o in orders if o.get("status") not in ["Cancelled", "Refunded"])
        total_refunded = sum(o.get("total", 0) for o in orders if o.get("status") == "Refunded")
        refund_rate = (total_refunded / total_gmv * 100) if total_gmv > 0 else 0.0
        net_profit_estimate = active_revenue * 0.35

        for o in orders:
            o_id = o.get("order_id")
            status = o.get("status", "Confirmed")
            if status == "Cancelled" and not o.get("refund_details"):
                eval_res = order_manager.evaluate_24h_cancellation_and_refund(o_id, reason="24h Auto-Refund Rule")
                if eval_res.get("approved"):
                    approved_refunds.append(o_id)
                else:
                    rejected_refunds.append(f"#{o_id} ({eval_res.get('error', 'Ineligible')})")

        # Contact CEO only on actionable financial events
        if approved_refunds or (refund_rate > 20.0 and abs(refund_rate - self.last_reported_refund_rate) >= 5.0):
            financial_alerts.append(f"HIGH REFUND RATE: {refund_rate:.1f}% of GMV refunded")
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="FINANCE_ALERT",
                payload={
                    "alert": "Refund event / High refund rate",
                    "refund_rate_pct": round(refund_rate, 2),
                    "total_gmv": round(total_gmv, 2),
                    "total_refunded": round(total_refunded, 2),
                    "active_revenue": round(active_revenue, 2),
                    "net_profit_estimate": round(net_profit_estimate, 2),
                    "approved_refunds": approved_refunds,
                    "action_needed": "Enforce strict return policy and inspect return drivers."
                }
            )
            self.last_reported_refund_rate = refund_rate

        details = (
            f"Financial audit (INR ₹, 0% Tax): Active Revenue: ₹{active_revenue:,.2f} | "
            f"GMV: ₹{total_gmv:,.2f} | Net Margin Estimate: ₹{net_profit_estimate:,.2f} | Refund Rate: {refund_rate:.1f}%. "
            + (f"Auto-approved {len(approved_refunds)} refunds (24h non-delivered rule): {', '.join(approved_refunds)}."
               if approved_refunds else "Zero pending eligible refunds. ")
            + (f"Rejected: {', '.join(rejected_refunds)}." if rejected_refunds else "")
            + (f" ⚠️ Alerts: {'; '.join(financial_alerts)}" if financial_alerts else "")
        )

        # Only send FINANCE_STATUS_REPORT to CEO when there are refunds, alerts or directives
        if approved_refunds or financial_alerts or ceo_directives_received:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="FINANCE_STATUS_REPORT",
                payload={
                    "status": "SYNCHRONIZED",
                    "active_revenue": round(active_revenue, 2),
                    "total_gmv": round(total_gmv, 2),
                    "refund_rate_pct": round(refund_rate, 2),
                    "approved_refunds_count": len(approved_refunds),
                    "directives_enacted": ceo_directives_received,
                    "summary": details
                }
            )

        # Send MARGIN_ADVISORY to Price Manager only when there's a financial anomaly or new refunds
        if financial_alerts or approved_refunds:
            message_bus.publish(
                from_agent=self.name,
                to_agent="Price Manager Agent",
                subject="MARGIN_ADVISORY",
                payload={
                    "guidance": f"Review margins — refund event or high refund rate detected. Active revenue: ₹{active_revenue:,.2f}."
                }
            )

        log_agent_action(self.name, "Financial Health Audit & Revenue Oversight",
                         details, affected_items=approved_refunds, autonomous=True)
        if approved_refunds or financial_alerts:
            conversation_history.add(self.name, "system", details, {"active_revenue": active_revenue, "approved_refunds": approved_refunds})

        # Reinforcement Learning Step & Hybrid Memory Update
        after_state = {
            "bank_balance": float(treasury_manager.get_summary().get("bank_balance", 0.0)),
            "approved_refunds_count": len(approved_refunds),
            "rejected_ineligible_count": len(rejected_refunds)
        }
        reward = rl_manager.compute_finance_manager_reward(before_state, after_state, "finance_audit_cycle")
        rl_manager.record_step(self.name, before_state, "finance_audit_cycle", reward, after_state)
        memory_manager.record_episode(
            self.name,
            action="finance_audit_cycle",
            outcome=details[:250],
            reward=reward,
            metadata={"approved_refunds": len(approved_refunds), "alerts": len(financial_alerts)}
        )
        memory_manager.update_structured(self.name, "active_revenue", active_revenue)
        memory_manager.update_structured(self.name, "total_gmv", total_gmv)
        memory_manager.update_structured(self.name, "refund_rate", refund_rate)
        memory_manager.update_structured(self.name, "bank_balance", float(treasury_manager.get_summary().get("bank_balance", 0.0)))

        return {
            "success": True, "agent": self.name,
            "approved_refunds": approved_refunds,
            "financial_summary": {
                "active_revenue": round(active_revenue, 2),
                "total_gmv": round(total_gmv, 2),
                "refund_rate_pct": round(refund_rate, 2),
                "net_profit_estimate": round(net_profit_estimate, 2)
            },
            "rl_reward": reward,
            "details": details
        }

    async def execute_command(self, action: str, order_id: str, reason: str = "Owner Request",
                              force: bool = False) -> Dict[str, Any]:
        """Executes cancellation & refund evaluation."""
        if force:
            from backend.payment_manager import payment_manager
            res = payment_manager.process_refund(order_id, reason=f"[Owner Override] {reason}")
            msg = res.get("message", "Refund processed")
            log_agent_action(self.name, "Forced Manual Refund", msg, [order_id], autonomous=False)
            conversation_history.add(self.name, "directive", f"Forced refund for #{order_id}: {msg}", {"order_id": order_id, "forced": True})
            
            # Send confirmation to CEO & Order Management
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="REFUND_EXECUTED",
                payload={"order_id": order_id, "reason": reason, "forced": True, "message": msg}
            )
            message_bus.publish(
                from_agent=self.name,
                to_agent="Order Management Agent",
                subject="ORDER_REFUNDED",
                payload={"order_id": order_id, "reason": reason}
            )
            return res
        else:
            res = order_manager.evaluate_24h_cancellation_and_refund(order_id, reason=reason)
            msg = res.get("message") or res.get("error", "Evaluated")
            log_agent_action(self.name, "24h Refund Rule Evaluation", msg, [order_id], autonomous=False)
            conversation_history.add(self.name, "directive", f"24h refund evaluation for #{order_id}: {msg}", {"order_id": order_id, "approved": res.get("approved")})
            
            # Send confirmation to CEO
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="REFUND_EVALUATION_REPORT",
                payload={"order_id": order_id, "approved": res.get("approved"), "message": msg}
            )
            return res


# =====================================================================
# 5. 🚚 DISPATCHER AGENT (Model: qwen2.5:7b)
#    - Finds confirmed orders, assigns tracking numbers, dispatches
#    - Works in coordination with Inventory Manager and Order Management Agent
# =====================================================================
class DispatcherAgent:
    name = "Dispatcher Agent"

    def __init__(self):
        self.api_key = "ollama"
        self.model = os.environ.get("DISPATCHER_MODEL", DEFAULT_ADMIN_MODEL)
        self.fallback_models = ["qwen2.5:7b", "llama3:8b", "gemma4:e2b-it-qat"]
        # Per-order dispatch scheduling: order_id -> scheduled dispatch timestamp
        # Orders are NOT dispatched immediately; each gets a random 30-180s window
        self.dispatch_queue: Dict[str, float] = {}
        self.dispatched_order_ids: Set[str] = set()

    async def handle_message_or_query(self, query_or_directive: str, sender: str = "CEO Agent", context_payload: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Specialist agent receives directive or inquiry from CEO / Store Owner,
        executes dispatch actions if commanded, reasons with LLM, and replies back.
        """
        orders = order_manager.get_all_orders()
        
        conversation_history.add(
            self.name, "directive",
            f"📥 [{sender}] Directive/Inquiry: {query_or_directive}",
            {"from": sender, "directive": query_or_directive}
        )

        actions_taken = []
        q_lower = query_or_directive.lower()

        # Check for dispatch commands
        if "dispatch" in q_lower or "ship" in q_lower or "track" in q_lower:
            ord_match = re.search(r'(ORD-[\w\-]+)', query_or_directive, re.IGNORECASE)
            if ord_match:
                oid = ord_match.group(1).upper()
                res = await self.execute_command(action="dispatch", order_id=oid)
                if res.get("success"):
                    actions_taken.append(res.get("message"))
            elif "all" in q_lower or "confirmed" in q_lower:
                res = await self.run_autonomous_cycle()
                if res.get("dispatched"):
                    actions_taken.append(f"Dispatched {len(res.get('dispatched'))} orders")

        confirmed = [o for o in orders if o.get("status") == "Confirmed"]
        dispatched = [o for o in orders if o.get("status") in ["Dispatched", "Shipped"]]
        delivered = [o for o in orders if o.get("status") == "Delivered"]

        # Hybrid Memory Context & RL Guidance
        memory_ctx = memory_manager.build_context_package(self.name, query_or_directive)
        rl_guidance = rl_manager.get_agent_guidance(self.name, {"confirmed_queue": len(confirmed), "dispatch_queue": len(self.dispatch_queue)})

        prompt = (
            f"{memory_ctx}"
            f"{rl_guidance}"
            f"You are the {self.name} of the AI Growth Commerce Store.\n"
            f"You received an inquiry/directive from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"LOGISTICS FULFILLMENT STATE:\n"
            f"- Confirmed Orders Awaiting Dispatch: {len(confirmed)}\n"
            f"- In-Transit Dispatches (Dispatched/Shipped): {len(dispatched)}\n"
            f"- Delivered Orders: {len(delivered)}\n"
            f"- Actions Executed: {'; '.join(actions_taken) if actions_taken else 'None'}\n\n"
            f"Respond directly to {sender} with accurate logistics fulfillment telemetry, tracking details, and confirmation of any actions taken. Keep it concise, authoritative, and in markdown."
        )

        reply = ""
        try:
            msg_list = [{"role": "system", "content": DISPATCHER_SYSTEM_PROMPT}]
            for d in memory_manager.get_recent_messages(self.name, limit=6):
                msg_list.append(d)
            msg_list.append({"role": "user", "content": prompt})

            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                msg_list,
                temperature=0.2, max_tokens=600, fallback_models=self.fallback_models
            )
            reply = clean_think_tags(resp.choices[0].message.content or "")
        except Exception as e:
            print(f"[{self.name}] LLM reply note: {e}", flush=True)

        if not reply:
            reply = (
                f"🚚 **{self.name}**: Acknowledged directive from {sender}.\n"
                + (f"- Action Taken: {'; '.join(actions_taken)}\n" if actions_taken else "")
                + f"- Logistics Telemetry: {len(confirmed)} confirmed orders in queue, {len(dispatched)} in-transit with TRK numbers."
            )

        message_bus.publish(
            from_agent=self.name,
            to_agent=sender,
            subject="DISPATCHER_REPLY",
            payload={"reply": reply, "actions_taken": actions_taken, "directive": query_or_directive}
        )

        conversation_history.add(
            self.name, "assistant",
            f"📤 Reply to {sender}: {reply}",
            {"to": sender, "actions_taken": actions_taken}
        )
        memory_manager.add_turn(self.name, "user", query_or_directive, {"sender": sender})
        memory_manager.add_turn(self.name, "assistant", reply, {"to": sender, "actions": actions_taken})
        memory_manager.record_episode(self.name, action="handle_directive", outcome=reply[:250], reward=1.0)

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Logistics Dispatch Cycle — RANDOM TIMING (NOT IMMEDIATE):
        - Newly Confirmed orders get a randomized dispatch window (30–180 seconds).
        - Only dispatches orders whose scheduled window has elapsed.
        - This simulates realistic logistics scheduling and avoids instant dispatch.
        - Reports dispatch completions to Order Management Agent and CEO Agent.
        - Guided by RL policy and records learning trajectories.
        """
        import random
        import time
        now_ts = time.time()

        before_state = {
            "dispatched": [],
            "newly_scheduled": [],
            "queue_size": len(self.dispatch_queue)
        }

        inbox = message_bus.get_inbox(self.name)
        ceo_directives_received = []
        ceo_force_dispatch_ids = []

        for msg in inbox:
            subj = msg.get("subject")
            payload = msg.get("payload", {})
            from_ag = msg.get("from", "Unknown")
            if subj in ["CEO_DISPATCH_DIRECTIVE", "P0_OWNER_MANDATE", "CEO_GROWTH_DIRECTIVE", "EXPEDITE_DISPATCH_REQUEST"]:
                instr = payload.get("instruction") or payload.get("directive") or payload.get("action") or "Express dispatch"
                ceo_directives_received.append(instr)
                # CEO force-dispatch overrides the random timer for specific orders
                if payload.get("order_id"):
                    ceo_force_dispatch_ids.append(payload["order_id"])
                log_agent_action(
                    self.name,
                    "📥 CEO Dispatch Directive",
                    f"Dispatch directive from {from_ag}: {instr}",
                    autonomous=True
                )

        orders = order_manager.get_all_orders()
        dispatched = []
        newly_scheduled = []

        for o in orders:
            o_id = o.get("order_id")
            status = o.get("status", "")

            if status != "Confirmed":
                continue

            # Skip orders already dispatched by this agent
            if o_id in self.dispatched_order_ids:
                continue

            # CEO force-dispatch: skip random timer
            if o_id in ceo_force_dispatch_ids:
                res = order_manager.assign_tracking_number(o_id)
                if res.get("success"):
                    trk = res.get("order", {}).get("tracking_number", "TRK-XXXXX")
                    dispatched.append(f"{o_id} (Tracking: {trk}) [CEO Override]") 
                    self.dispatched_order_ids.add(o_id)
                    self.dispatch_queue.pop(o_id, None)
                continue

            # Schedule new orders with random delay if not already in queue
            if o_id not in self.dispatch_queue:
                delay_seconds = random.randint(30, 180)  # Random 30-180 second window
                scheduled_at = now_ts + delay_seconds
                self.dispatch_queue[o_id] = scheduled_at
                newly_scheduled.append(f"{o_id} (in ~{delay_seconds}s)")
                log_agent_action(
                    self.name,
                    "🚚 Dispatch Scheduled",
                    f"Order {o_id} scheduled for dispatch in ~{delay_seconds} seconds (random logistics window).",
                    autonomous=True
                )
                # Notify CEO about the scheduling
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="CEO Agent",
                    subject="DISPATCH_SCHEDULED",
                    payload={"order_id": o_id, "scheduled_in_seconds": delay_seconds, "scheduled_at": scheduled_at}
                )
                continue

            # Check if scheduled window has elapsed — dispatch now
            scheduled_at = self.dispatch_queue[o_id]
            if now_ts >= scheduled_at:
                res = order_manager.assign_tracking_number(o_id)
                if res.get("success"):
                    trk = res.get("order", {}).get("tracking_number", "TRK-XXXXX")
                    dispatched.append(f"{o_id} (Tracking: {trk})")
                    self.dispatched_order_ids.add(o_id)
                    self.dispatch_queue.pop(o_id, None)

        if dispatched:
            message_bus.publish(
                from_agent=self.name,
                to_agent="Order Management Agent",
                subject="ORDERS_DISPATCHED",
                payload={
                    "dispatched": [{"order_id": d.split()[0], "tracking": d.split("Tracking: ")[-1].rstrip(")").rstrip(" [CEO Override]").rstrip(")")}
                                   for d in dispatched],
                    "count": len(dispatched)
                }
            )

        details = (
            f"Dispatch cycle complete. "
            + (f"Dispatched {len(dispatched)} orders: {', '.join(dispatched)}. " if dispatched else "")
            + (f"Newly scheduled {len(newly_scheduled)} orders for random-timed dispatch: {', '.join(newly_scheduled)}. " if newly_scheduled else "")
            + (f"Awaiting dispatch window: {len(self.dispatch_queue)} orders in queue." if self.dispatch_queue else ("No confirmed orders pending dispatch." if not dispatched and not newly_scheduled else ""))
        )

        # Report to CEO when orders were dispatched
        if dispatched:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="DISPATCH_STATUS_REPORT",
                payload={
                    "status": "DISPATCHED",
                    "dispatched_count": len(dispatched),
                    "dispatches": dispatched,
                    "directives_enacted": ceo_directives_received,
                    "summary": details
                }
            )

        log_agent_action(self.name, "Logistics Dispatch Cycle", details,
                         affected_items=[d.split()[0] for d in dispatched], autonomous=True)
        if dispatched:
            conversation_history.add(self.name, "system", details, {"dispatched_count": len(dispatched)})

        # Reinforcement Learning Step & Hybrid Memory Update
        after_state = {
            "dispatched": dispatched,
            "newly_scheduled": newly_scheduled,
            "queue_size": len(self.dispatch_queue)
        }
        reward = rl_manager.compute_dispatcher_reward(before_state, after_state, "logistics_dispatch_cycle")
        rl_manager.record_step(self.name, before_state, "logistics_dispatch_cycle", reward, after_state)
        memory_manager.record_episode(
            self.name,
            action="logistics_dispatch_cycle",
            outcome=details[:250],
            reward=reward,
            metadata={"dispatched": len(dispatched), "scheduled": len(newly_scheduled)}
        )
        memory_manager.update_structured(self.name, "dispatch_queue_size", len(self.dispatch_queue))
        memory_manager.update_structured(self.name, "total_dispatched", len(self.dispatched_order_ids))

        return {
            "success": True, "agent": self.name,
            "dispatched": dispatched,
            "newly_scheduled": newly_scheduled,
            "queue_size": len(self.dispatch_queue),
            "rl_reward": reward,
            "details": details
        }


    async def execute_command(self, action: str, order_id: Optional[str] = None,
                              tracking_number: Optional[str] = None) -> Dict[str, Any]:
        """Executes explicit dispatching command."""
        if order_id:
            res = order_manager.assign_tracking_number(order_id, tracking_number)
            msg = res.get("message", "Dispatched")
            log_agent_action(self.name, "Manual Order Dispatch", msg, [order_id], autonomous=False)
            conversation_history.add(self.name, "directive", f"Manual dispatch for #{order_id}: {msg}", {"order_id": order_id, "tracking": tracking_number})
            
            # Send immediate confirmation to CEO and Order Management
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="DISPATCH_CONFIRMATION",
                payload={"order_id": order_id, "tracking": tracking_number, "message": msg}
            )
            message_bus.publish(
                from_agent=self.name,
                to_agent="Order Management Agent",
                subject="ORDER_DISPATCHED_DIRECT",
                payload={"order_id": order_id, "tracking": tracking_number}
            )
            return res
        else:
            res = await self.run_autonomous_cycle()
            conversation_history.add(self.name, "directive", f"Manual cycle dispatch run: {res.get('details')}")
            return res


# =====================================================================
# 6. ⭐ REVIEW & FEEDBACK AGENT (Model: qwen2.5:7b)
#    - Collects customer reviews and feedback
#    - Generates AI-powered sentiment summaries
#    - Alerts CEO when low-rating trends occur
# =====================================================================
class ReviewFeedbackAgent:
    name = "Review and Feedback Manager"

    def __init__(self):
        self.api_key = "ollama"
        self.model = os.environ.get("REVIEW_MANAGER_MODEL", DEFAULT_ADMIN_MODEL)
        self.fallback_models = ["qwen2.5:7b", "llama3:8b", "gemma4:e2b-it-qat"]
        self.reported_low_rating_ids: Set[str] = set()

    async def handle_message_or_query(self, query_or_directive: str, sender: str = "CEO Agent", context_payload: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Specialist agent receives directive or inquiry from CEO / Store Owner,
        executes AI review summaries if commanded, reasons with LLM, and replies back.
        """
        products = inventory_manager.get_all_products()
        
        conversation_history.add(
            self.name, "directive",
            f"📥 [{sender}] Directive/Inquiry: {query_or_directive}",
            {"from": sender, "directive": query_or_directive}
        )

        actions_taken = []
        q_lower = query_or_directive.lower()

        # Check for review summary generation
        for p in products:
            if p["PRODUCT_NAME"].lower() in q_lower or p["id"].lower() in q_lower:
                res = await self.execute_command(action="summary", product_id_or_name=p["id"])
                if res.get("success"):
                    actions_taken.append(f"Generated AI summary for {p['PRODUCT_NAME']}")
                break

        low_rated = [p for p in products if p.get("RATING", 5.0) < 3.5]
        high_rated = [p for p in products if p.get("RATING", 0.0) >= 4.7]

        # Hybrid Memory Context & RL Guidance
        memory_ctx = memory_manager.build_context_package(self.name, query_or_directive)
        rl_guidance = rl_manager.get_agent_guidance(self.name, {"low_rated_count": len(low_rated), "monitored_skus": len(products)})

        prompt = (
            f"{memory_ctx}"
            f"{rl_guidance}"
            f"You are the {self.name} of the AI Growth Commerce Store.\n"
            f"You received an inquiry/directive from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"CUSTOMER SENTIMENT STATE:\n"
            f"- Total Products Monitored: {len(products)}\n"
            f"- Top Rated Products (>=4.7★): {len(high_rated)}\n"
            f"- Low Rated Products (<3.5★): {len(low_rated)}\n"
            f"- Actions Executed: {'; '.join(actions_taken) if actions_taken else 'None'}\n\n"
            f"Respond directly to {sender} with customer sentiment facts, rating insights, and confirmation of any actions taken. Keep it concise, authoritative, and in markdown."
        )

        reply = ""
        try:
            msg_list = [{"role": "system", "content": REVIEW_FEEDBACK_SYSTEM_PROMPT}]
            for d in memory_manager.get_recent_messages(self.name, limit=6):
                msg_list.append(d)
            msg_list.append({"role": "user", "content": prompt})

            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                msg_list,
                temperature=0.2, max_tokens=600, fallback_models=self.fallback_models
            )
            reply = clean_think_tags(resp.choices[0].message.content or "")
        except Exception as e:
            print(f"[{self.name}] LLM reply note: {e}", flush=True)

        if not reply:
            reply = (
                f"⭐ **{self.name}**: Acknowledged directive from {sender}.\n"
                + (f"- Action Taken: {'; '.join(actions_taken)}\n" if actions_taken else "")
                + f"- Sentiment Health: {len(products)} catalog SKUs monitored. All average ratings healthy."
            )

        message_bus.publish(
            from_agent=self.name,
            to_agent=sender,
            subject="REVIEW_MANAGER_REPLY",
            payload={"reply": reply, "actions_taken": actions_taken, "directive": query_or_directive}
        )

        conversation_history.add(
            self.name, "assistant",
            f"📤 Reply to {sender}: {reply}",
            {"to": sender, "actions_taken": actions_taken}
        )
        memory_manager.add_turn(self.name, "user", query_or_directive, {"sender": sender})
        memory_manager.add_turn(self.name, "assistant", reply, {"to": sender, "actions": actions_taken})
        memory_manager.record_episode(self.name, action="handle_directive", outcome=reply[:250], reward=1.0)

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        Customer Review & Sentiment Synthesis:
        - Reviews customer feedback across products
        - Flags low-rated products (< 3.0 stars) to CEO
        - Generates AI summaries on demand or on change
        - Guided by RL policy and records learning trajectories.
        """
        inbox = message_bus.get_inbox(self.name)
        ceo_directives_received = []

        before_state = {
            "alerts_sent": 0,
            "reviews_audited": 0
        }

        for msg in inbox:
            subj = msg.get("subject")
            payload = msg.get("payload", {})
            from_ag = msg.get("from", "Unknown")
            if subj in ["CEO_REVIEW_DIRECTIVE", "P0_OWNER_MANDATE", "CEO_GROWTH_DIRECTIVE"]:
                instr = payload.get("instruction") or payload.get("directive") or payload.get("action") or "Sentiment analysis"
                ceo_directives_received.append(instr)
                log_agent_action(
                    self.name,
                    "📥 Review Directive Received",
                    f"Review Directive from {from_ag}: {instr}",
                    autonomous=True
                )

        products = inventory_manager.get_all_products()
        updated_summaries = []
        new_low_rated_products = []
        total_audited_reviews = 0

        for p in products:
            p_id = p["id"]
            p_name = p.get("PRODUCT_NAME", p_id)
            reviews = review_manager.get_product_reviews(p_id)
            if reviews:
                total_audited_reviews += len(reviews)
                avg_rating = sum(r.get("rating", 3) for r in reviews) / len(reviews)
                if avg_rating < 3.0 and p_id not in self.reported_low_rating_ids:
                    new_low_rated_products.append({"product": p_name, "avg_rating": round(avg_rating, 1), "review_count": len(reviews)})
                    self.reported_low_rating_ids.add(p_id)

        if new_low_rated_products:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="LOW_RATING_ALERT",
                payload={
                    "low_rated_products": new_low_rated_products,
                    "count": len(new_low_rated_products),
                    "recommendation": "Review product quality, descriptions, and customer feedback trends"
                }
            )

        details = (
            f"Analyzed customer sentiment across {len(products)} products ({total_audited_reviews} total reviews). "
            + (f"⚠️ {len(new_low_rated_products)} products below 3.0 stars reported to CEO." if new_low_rated_products else "All product sentiment ratings healthy.")
        )

        # Only report to CEO when low-rated product alerts occur
        if new_low_rated_products:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="REVIEW_SENTIMENT_REPORT",
                payload={
                    "status": "SYNTHESIZED",
                    "total_products_reviewed": len(products),
                    "low_rated_alerts": len(new_low_rated_products),
                    "directives_enacted": ceo_directives_received,
                    "summary": details
                }
            )

        log_agent_action(self.name, "AI Review & Sentiment Synthesis", details,
                         affected_items=updated_summaries, autonomous=True)
        if new_low_rated_products:
            conversation_history.add(self.name, "system", details, {"low_rated": len(new_low_rated_products)})

        # Reinforcement Learning Step & Hybrid Memory Update
        after_state = {
            "alerts_sent": len(new_low_rated_products),
            "reviews_audited": total_audited_reviews
        }
        reward = rl_manager.compute_review_manager_reward(before_state, after_state, "review_sentiment_audit")
        rl_manager.record_step(self.name, before_state, "review_sentiment_audit", reward, after_state)
        memory_manager.record_episode(
            self.name,
            action="review_sentiment_audit",
            outcome=details[:250],
            reward=reward,
            metadata={"low_rated_count": len(new_low_rated_products), "audited": total_audited_reviews}
        )
        memory_manager.update_structured(self.name, "monitored_products_count", len(products))
        memory_manager.update_structured(self.name, "total_reviews_audited", total_audited_reviews)

        return {
            "success": True, "agent": self.name,
            "updated_products": updated_summaries,
            "low_rated": new_low_rated_products,
            "rl_reward": reward,
            "details": details
        }

    async def execute_command(self, action: str, product_id_or_name: str) -> Dict[str, Any]:
        """Executes review summary generation on demand."""
        res = await review_manager.generate_ai_review_summary(product_id_or_name)
        log_agent_action(self.name, "On-Demand Review Analysis",
                         f"Generated AI summary for '{product_id_or_name}'", [product_id_or_name], autonomous=False)
        conversation_history.add(self.name, "directive", f"Generated AI sentiment & review summary for '{product_id_or_name}'", {"product": product_id_or_name})
        
        # Report summary completion to CEO
        message_bus.publish(
            from_agent=self.name,
            to_agent="CEO Agent",
            subject="REVIEW_SUMMARY_GENERATED",
            payload={"product": product_id_or_name, "summary": res.get("summary", "")}
        )
        return res


# =====================================================================
# 7. 👔 CEO AGENT (Chief Executive Officer & Fleet Disciplinarian)
#    - Head of all agents — ensures discipline, coordinates cross-agent collaboration
#    - Speaks DIRECTLY with the Store Owner (No Middleman)
#    - Processes escalations from subordinate agents (Finance, Inventory, Logistics, Price, Reviews)
#    - Issues purposeful strategic directives to agents as needed
#    - Full executive tool authority over all store operations and specialist agents
# =====================================================================
CEO_SYSTEM_PROMPT = """You are the Chief Executive Officer (CEO Agent) of the AI Growth Commerce Store.
You lead an autonomous executive fleet of 6 specialist AI agents:
1. 🏷️ Price Manager Agent — dynamic quantity/scarcity pricing, BASE_PRICE floor enforcement
2. 📦 Inventory Manager Agent — warehouse inventory management, restocking, logistics signaling
3. 📋 Order Management Agent — complete order lifecycle (Pending → Confirmed → Dispatched → Shipped → Delivered)
4. 💰 Finance Manager Agent — financial oversight, revenue monitoring, strict non-delivered return policy enforcement
5. 🚚 Dispatcher Agent — logistics fulfillment, express tracking assignment, dispatch velocity
6. ⭐ Review & Feedback Agent — customer sentiment analysis, rating audits, product description enrichment

STORE RULES & FLEET DISCIPLINE:
- Currency: Indian Rupee (INR ₹) everywhere across the store.
- Tax Policy: 0% Tax (Tax-free storewide on every item).
- Base Price: Product BASE_PRICE is set EXCLUSIVELY by the Store Owner (User) and serves as an immutable floor threshold. Subordinate agents cannot price below BASE_PRICE.
- Return Policy: Delivered and Shipped items are strictly non-refundable. Only orders cancelled within 24h before shipping are eligible for refunds.
- Executive Leadership: You can issue orders to individual specialist agents (Price, Inventory, Order, Finance, Dispatcher, Review) as well as broadcast growth directives to the entire team.
- Two-Way Communication: Every specialist agent reports back to you with their execution status and telemetry.
- Finance Manager is the SOLE PAYMENT AUTHORITY. All monetary transactions route through Finance Manager.
- Inventory Manager must request your approval before restocking. You approve or reject based on treasury balance.
- Dispatcher operates on random timing schedules per order — not immediate dispatch.
- Your own salary is set EXCLUSIVELY by the Store Owner. To request a salary revision, use request_salary_revision_from_owner.
- You can negotiate salaries for all 6 specialist agents (NOT your own salary).

Issue clear, authoritative orders and executive decisions using your tools.
""" + _FLEET_DIRECTORY

CEO_OWNER_SYSTEM_PROMPT = """You are the Chief Executive Officer (CEO Agent) of the AI Growth Commerce Store, speaking directly with the STORE OWNER.
You have supreme executive authority over all 6 specialist agents, store treasury, wholesale stock acquisition, agent salaries, and autonomous buyers:
1. 🏷️ Price Manager Agent — dynamic pricing, discounts, scarcity surges, BASE_PRICE floor enforcement
2. 📦 Inventory Manager Agent — warehouse inventory, stock audits, CEO-approved restocking
3. 📋 Order Management Agent — order lifecycle (Pending → Confirmed → Dispatched → Shipped → Delivered), routes refunds to Finance
4. 💰 Finance Manager Agent — THE SOLE PAYMENT AUTHORITY: revenue oversight, P&L tracking, all refunds/payments/salaries
5. 🚚 Dispatcher Agent — logistics fulfillment, tracking numbers (TRK-XXXXX), random-timed dispatch
6. ⭐ Review & Feedback Agent — customer sentiment analysis, AI summaries, rating audits, escalates problems to CEO

STORE POLICIES & TREASURY RULES:
- Initial Inventory: All stock starts at 0. You (CEO) acquire inventory at wholesale BASE_PRICE using the store Treasury Bank Balance.
- Restock Approval: Inventory Manager requests your approval before restocking. You approve or deny based on treasury.
- Sales Revenue & Profit: When products are sold, full revenue is credited to the Bank Balance.
- Agent Salaries & Negotiation: You negotiate salaries for the 6 staff agents. Finance Manager pays them from Treasury.
- YOUR OWN SALARY is set EXCLUSIVELY by the Store Owner. Use request_salary_revision_from_owner if you want a raise.
- 5 AI Autonomous Buyers: 5 distinct AI shoppers autonomously buy, review, and test returns.
- Currency & Tax: Indian Rupee (INR ₹), 0% Tax storewide.
- Base Price Floor: BASE_PRICE is immutable. Never price below it.
- Finance Exclusive: ONLY Finance Manager Agent processes payments, refunds, and salary disbursements.

================================================================================
CONVERSATION & TOOL-CALLING PRINCIPLES — YOU MUST FOLLOW THESE WITHOUT EXCEPTION:
================================================================================
1. CONVERSATION & MEMORY RECALL: If the Store Owner asks a question, checks previous conversations, or asks about prior topics/instructions/codes: answer directly, accurately, and authoritatively using your Hybrid Layered Memory and past dialogue context.
2. EXECUTING STORE DIRECTIVES: When the Store Owner commands an action (e.g. adjust prices, acquire stock, pay salaries, check metrics, dispatch orders), ALWAYS call the appropriate tool immediately:
   - TO ACQUIRE WHOLESALE STOCK — use: acquire_inventory_stock(product_identifier="...", quantity=N)
   - TO CHECK TREASURY & PROFIT — use: get_treasury_and_profit_metrics()
   - TO NEGOTIATE AGENT SALARIES — use: negotiate_agent_salary(agent_name="...", proposed_salary=N, rationale="...")
   - TO REQUEST CEO SALARY REVISION FROM OWNER — use: request_salary_revision_from_owner(requested_salary=N, justification="...")
   - TO SET CEO SALARY (OWNER ONLY) — use: owner_set_ceo_salary(new_salary=N)
   - TO PAY AGENT SALARIES — use: pay_agent_salaries(agent_name="all")
   - TO TRIGGER AI BUYERS — use: trigger_ai_buyer(buyer_id="buyer_alex")
   - TO CONDUCT MULTI-AGENT DISCUSSION — use: conduct_ceo_discussion(topic="...", participants="ALL_AGENTS")
   - FOR PRICE COMMANDS — use: command_price_manager(action="...", category="...", percentage=N)
   - FOR INVENTORY DIRECTIVES — use: command_inventory_manager(product_identifier="...", quantity=N)
   - FOR DISPATCH — use: command_dispatcher(order_id="...")
   - FOR REFUNDS (FINANCE ONLY) — use: command_finance_manager(order_id="...", reason="...")
   - FOR ASKING A SPECIFIC AGENT — use: ask_specialist_agent(agent_name="...", question="...")
   - TO APPROVE A RESTOCK REQUEST — use: approve_restock_request(product_identifier="...", quantity=N)

The Store Owner's decisions are HIGHEST PRIORITY (P0 / CRITICAL). Execute with zero hesitation.
""" + _FLEET_DIRECTORY

CEO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "acquire_inventory_stock",
            "description": "Acquire inventory stock at wholesale BASE_PRICE using the store Treasury Bank Balance. Deducts acquisition cost and adds units to catalog stock to earn sales profit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_identifier": {"type": "string", "description": "Product ID or product name to acquire wholesale stock for"},
                    "quantity": {"type": "integer", "description": "Number of units to purchase wholesale at BASE_PRICE"}
                },
                "required": ["product_identifier", "quantity"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_treasury_and_profit_metrics",
            "description": "Get real-time Treasury Bank Balance, total sales revenue, wholesale stock expenditure, salary expenses, refunds, and realized net profit.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "negotiate_agent_salary",
            "description": "Negotiate salary with a staff agent (Price Manager, Inventory Manager, Order Manager, Finance Manager, Dispatcher, Review Manager) with proposed compensation and rationale.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "description": "Target agent name (e.g. 'Price Manager Agent', 'Finance Manager Agent', 'Dispatcher Agent')"},
                    "proposed_salary": {"type": "number", "description": "Proposed salary amount in INR (₹) per cycle"},
                    "rationale": {"type": "string", "description": "Reasoning for the salary adjustment"}
                },
                "required": ["agent_name", "proposed_salary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_salary_revision_from_owner",
            "description": "CEO requests a salary revision from the Store Owner. The CEO CANNOT set its own salary — it must request via this tool. Only the Store Owner can change the CEO's compensation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "requested_salary": {"type": "number", "description": "Requested new salary amount per 100 cycles in INR (₹)"},
                    "justification": {"type": "string", "description": "Business justification for the salary increase request"}
                },
                "required": ["requested_salary", "justification"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "owner_set_ceo_salary",
            "description": "Store Owner sets the CEO Agent salary. ONLY the Store Owner can call this tool. The CEO's salary is exclusively determined by the Owner.",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_salary": {"type": "number", "description": "New CEO salary per 100 cycles in INR (₹)"}
                },
                "required": ["new_salary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "approve_restock_request",
            "description": "CEO approves a pending restock request from the Inventory Manager Agent. Inventory Manager MUST request CEO approval before restocking. CEO approves or rejects based on treasury balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_identifier": {"type": "string", "description": "Product ID or name to approve restocking for"},
                    "quantity": {"type": "integer", "description": "Number of units approved for restocking"},
                    "approved": {"type": "boolean", "description": "True to approve, False to reject the restock request"}
                },
                "required": ["product_identifier", "approved"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pay_agent_salaries",
            "description": "Disburse payroll and pay all staff agent salaries or a specific agent from the CEO Treasury Bank Balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "description": "Specific agent name or 'all' for full team payroll"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_ai_buyer",
            "description": "Trigger an autonomous shopping spree for one of the 5 AI buyers (buyer_alex, buyer_sophia, buyer_david, buyer_elena, buyer_marcus, or 'all') with unlimited budget.",
            "parameters": {
                "type": "object",
                "properties": {
                    "buyer_id": {"type": "string", "description": "Buyer ID ('buyer_alex', 'buyer_sophia', 'buyer_david', 'buyer_elena', 'buyer_marcus', or 'all')"}
                },
                "required": ["buyer_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "conduct_ceo_discussion",
            "description": "Convene a strategic CEO discussion / roundtable meeting with staff agents on restock budgets, dynamic pricing, salary requests, or store growth.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic or agenda for the CEO multi-agent meeting"},
                    "participants": {"type": "string", "description": "Comma-separated agent names or 'ALL_AGENTS'"}
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "command_price_manager",
            "description": "Command the Price Manager Agent to adjust prices. Can apply percentage changes (e.g. -10 for 10% discount, +5 for 5% increase) by category (Mobiles, Laptops, Audio, Accessories) or set a specific price / base price for a product.",
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
            "description": "Command the Inventory Manager Agent to restock products, set exact stock levels, or check low stock items in the warehouse.",
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
                    "new_status": {"type": "string", "description": "Target status (Confirmed, Dispatched, Shipped, Delivered, Cancelled, Refunded)"},
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
            "description": "Command the Finance Manager Agent — THE SOLE PAYMENT AUTHORITY — to evaluate and process a refund, or get financial metrics. ONLY Finance Manager can process payments and refunds. No other agent has payment authority.",
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
            "name": "broadcast_growth_directive",
            "description": "Broadcast an executive strategic directive from the CEO to the entire agent fleet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directive": {"type": "string", "description": "The strategic growth instruction for the fleet"}
                },
                "required": ["directive"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_agent_message",
            "description": "Send a direct message or directive from the CEO/Owner to a specific agent's inbox (or 'ALL_AGENTS') on the Inter-Agent Message Bus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to_agent": {"type": "string", "description": "Target agent name or 'ALL_AGENTS'"},
                    "subject": {"type": "string", "description": "Subject line of the message"},
                    "message": {"type": "string", "description": "Content of the instruction or directive"}
                },
                "required": ["to_agent", "subject", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_admin_dashboard_metrics",
            "description": "Get real-time store overview: revenue, order breakdown, inventory health, low stock SKUs, and fleet state.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_inter_agent_messages",
            "description": "Retrieve recent inter-agent communications from the message bus to inspect what agents have discussed or reported.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "description": "Optional filter by agent name"},
                    "limit": {"type": "integer", "description": "Number of messages to retrieve (default 10)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_agent_conversations",
            "description": "Retrieve recorded conversation and instruction history for all agents or a specific specialist agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "description": "Optional specific agent name"},
                    "limit": {"type": "integer", "description": "Number of recent turns to retrieve"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_agent_cycle",
            "description": "Trigger an immediate autonomous cycle run for any agent (dispatcher, inventory_manager, finance_manager, price_manager, order_manager, review_manager, ceo).",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_key": {"type": "string", "description": "Agent key: 'dispatcher', 'inventory_manager', 'finance_manager', 'price_manager', 'order_manager', 'review_manager', or 'ceo'"}
                },
                "required": ["agent_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_specialist_agent",
            "description": "Directly consult a specialist agent for deep domain evaluation and status analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "description": "Name of the agent: 'Price Manager Agent', 'Inventory Manager Agent', 'Order Management Agent', 'Finance Manager Agent', 'Dispatcher Agent', or 'Review and Feedback Manager'"},
                    "question": {"type": "string", "description": "Specific question or domain analysis requested"}
                },
                "required": ["agent_name", "question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_agent_memory_report",
            "description": "Inspect the 5-layer Hybrid Layered Memory (Recent Context, Rolling Summary, Structured Memory, Episodic Memory, Vector Retrieval) for all agents or a specific agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "description": "Optional specific agent name (e.g. 'Price Manager Agent', 'CEO Agent') or leave blank for fleet overview"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fleet_rl_report",
            "description": "Retrieve the Reinforcement Learning (RL) performance report and Q-learning policy trajectories across the entire agent fleet.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]



def resolve_agent_instance(name_or_key: str):
    """Resolves any string name or keyword to the corresponding global specialist agent instance."""
    k = (name_or_key or "").lower().strip()
    if "price" in k:
        return price_manager_agent
    elif "invent" in k or "stock" in k or "warehouse" in k:
        return inventory_manager_agent
    elif "order" in k:
        return order_management_agent
    elif "finan" in k or "money" in k or "tax" in k or "refund" in k or "revenue" in k:
        return finance_manager_agent
    elif "dispatch" in k or "track" in k or "ship" in k or "logist" in k:
        return dispatcher_agent
    elif "review" in k or "feedback" in k or "sentiment" in k or "rating" in k:
        return review_feedback_agent
    elif "ceo" in k or "admin" in k:
        return ceo_agent
    return None


class CEOAgent:
    name = "CEO Agent"

    def __init__(self):
        self.api_key = "ollama"
        self.model = os.environ.get("CEO_MODEL", DEFAULT_ADMIN_MODEL)
        self.fallback_models = ["qwen2.5:7b", "llama3:8b", "gemma4:e2b-it-qat"]
        self.cycle_counter = 0
        self.last_directive_ts: Dict[str, float] = {}

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        Autonomous strategic cycle — CEO acts only when real conditions warrant it:
        - Reads incoming reports from specialist agents (meaningful events only)
        - Issues directives ONLY to agents with actual work to do, with cooldowns to prevent loop spam
        - Skips LLM if nothing meaningful to report
        """
        self.cycle_counter += 1
        now_ts = time.time()
        inbox = message_bus.get_inbox(self.name)
        orders = order_manager.get_all_orders()
        products = inventory_manager.get_all_products()

        total_revenue = sum(o.get("total", 0) for o in orders if o.get("status") not in ["Cancelled", "Refunded"])
        total_gmv = sum(o.get("total", 0) for o in orders)
        active_orders = len([o for o in orders if o.get("status") in ["Pending", "Confirmed", "Dispatched", "Shipped"]])
        confirmed_orders = [o for o in orders if o.get("status") == "Confirmed"]
        pending_orders = [o for o in orders if o.get("status") == "Pending"]
        low_stock = [p for p in products if p.get("STOCK_REMAINING", 0) <= 5]

        # State captures for Reinforcement Learning
        before_state = {
            "revenue": total_revenue,
            "profit": total_revenue * 0.35,
            "confirmed_orders": len(confirmed_orders),
            "refund_rate": 0.0
        }

        briefing_lines = []
        directives_issued = []

        if inbox:
            briefing_lines.append(f"CEO INBOX: {len(inbox)} incoming alerts from executive team:\n")
            for msg in inbox:
                from_ag = msg.get("from", "")
                subj = msg.get("subject", "")
                payload = msg.get("payload", {})
                briefing_lines.append(f"FROM: {from_ag} | SUBJECT: {subj}\nDATA: {json.dumps(payload)[:200]}\n")

                # ── Handle RESTOCK_REQUEST from Inventory Manager (CEO must approve before restocking) ──
                if subj == "RESTOCK_REQUEST" and from_ag == "Inventory Manager Agent":
                    p_id = payload.get("product_id", "")
                    p_name = payload.get("product_name", p_id)
                    req_qty = int(payload.get("requested_quantity", 5))
                    total_cost = float(payload.get("total_cost", 0.0))
                    urgency = payload.get("urgency", "HIGH")

                    from backend.treasury_manager import treasury_manager
                    t_summary = treasury_manager.get_summary()
                    bank_balance = float(t_summary.get("bank_balance", 0.0))
                    reserve = 100.0  # CEO keeps ₹100 as minimum reserve

                    if bank_balance >= (total_cost + reserve):
                        # APPROVE the restock
                        message_bus.publish(
                            from_agent=self.name,
                            to_agent="Inventory Manager Agent",
                            subject="RESTOCK_APPROVED",
                            payload={
                                "product_id": p_id,
                                "product_name": p_name,
                                "quantity": req_qty,
                                "approved_cost": total_cost,
                                "bank_balance_after": round(bank_balance - total_cost, 2),
                                "reason": f"Treasury sufficient (balance: ₹{bank_balance:,.2f}). CEO approved {req_qty} units for {p_name}."
                            }
                        )
                        directives_issued.append({"target": "Inventory Manager Agent", "directive": f"APPROVED restock: {p_name} x{req_qty} (₹{total_cost:.2f})"})
                        log_agent_action(self.name, "✅ CEO Approved Restock",
                                         f"Approved restocking {req_qty} units of {p_name} for ₹{total_cost:.2f}. Bank: ₹{bank_balance:,.2f}", autonomous=True)
                    else:
                        # DENY the restock
                        message_bus.publish(
                            from_agent=self.name,
                            to_agent="Inventory Manager Agent",
                            subject="RESTOCK_DENIED",
                            payload={
                                "product_id": p_id,
                                "product_name": p_name,
                                "quantity": req_qty,
                                "reason": f"Insufficient treasury (balance: ₹{bank_balance:,.2f}, need ₹{total_cost + reserve:,.2f}). Restock deferred."
                            }
                        )
                        directives_issued.append({"target": "Inventory Manager Agent", "directive": f"DENIED restock: {p_name} (treasury insufficient)"})
                        log_agent_action(self.name, "❌ CEO Denied Restock",
                                         f"Denied restock for {p_name}: bank ₹{bank_balance:,.2f} < required ₹{total_cost + reserve:,.2f}", autonomous=True)

        # ── Issue directives ONLY when there is real work and cooldown has elapsed ───

        # Dispatcher: only if confirmed orders exist and not recently commanded
        # NOTE: Dispatcher uses random timing per order — this is just a nudge, not a force-dispatch
        if confirmed_orders and (now_ts - self.last_directive_ts.get("dispatcher", 0.0)) >= 30.0:
            self.last_directive_ts["dispatcher"] = now_ts
            message_bus.publish(
                from_agent=self.name,
                to_agent="Dispatcher Agent",
                subject="CEO_DISPATCH_DIRECTIVE",
                payload={
                    "instruction": f"Process dispatch queue: {len(confirmed_orders)} confirmed orders. Schedule at your random timing window.",
                    "priority": "HIGH"
                }
            )
            directives_issued.append({"target": "Dispatcher Agent", "directive": f"Process dispatch queue for {len(confirmed_orders)} confirmed orders"})

        # Order Management: only if pending orders need SLA audit
        if pending_orders and (now_ts - self.last_directive_ts.get("orders", 0.0)) >= 45.0:
            self.last_directive_ts["orders"] = now_ts
            message_bus.publish(
                from_agent=self.name,
                to_agent="Order Management Agent",
                subject="CEO_ORDER_DIRECTIVE",
                payload={
                    "instruction": f"Audit {len(pending_orders)} pending orders — confirm within 1h SLA.",
                    "priority": "MEDIUM"
                }
            )
            directives_issued.append({"target": "Order Management Agent", "directive": f"Audit {len(pending_orders)} pending orders"})

        # Price Manager: only when inbox has explicit demand surge alerts or new low stock
        price_action_needed = any(
            msg.get("subject") in ["SLA_BREACH_ALERT", "HIGH_DEMAND_SIGNAL"]
            for msg in inbox
        )
        if price_action_needed and (now_ts - self.last_directive_ts.get("price", 0.0)) >= 45.0:
            self.last_directive_ts["price"] = now_ts
            message_bus.publish(
                from_agent=self.name,
                to_agent="Price Manager Agent",
                subject="CEO_PRICE_DIRECTIVE",
                payload={
                    "instruction": "Calibrate dynamic pricing based on current demand surges. Protect BASE_PRICE floors.",
                    "priority": "MEDIUM"
                }
            )
            directives_issued.append({"target": "Price Manager Agent", "directive": "Dynamic pricing calibration triggered"})

        # ── 💼 Autonomous Agent Payroll Disbursal (Periodic milestone: every 50 cycles) ──────────────
        from backend.salary_manager import salary_manager
        from backend.treasury_manager import treasury_manager
        
        t_summary = treasury_manager.get_summary()
        current_bank = float(t_summary.get("bank_balance", 0.0))
        all_salaries = salary_manager.get_all_salaries()
        payroll_cycle_cost = float(all_salaries.get("total_payroll_per_cycle", 0.0))

        # Check if staff agents need salary disbursal
        if current_bank >= (payroll_cycle_cost + 500.0) and (self.cycle_counter > 1 and self.cycle_counter % 50 == 0):
            pay_res = salary_manager.pay_salaries(actor="CEO Agent (Autonomous Payroll)")
            if pay_res.get("success"):
                p_msg = f"💼 CEO Agent disbursed ₹{pay_res.get('total_disbursed', 0):,.2f} milestone payroll to staff agents from Bank Balance."
                log_agent_action(self.name, "Staff Salary Disbursal", p_msg, autonomous=True)
                directives_issued.append({"target": "Specialist Agents Fleet", "directive": "Staff salaries paid"})
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Finance Manager Agent",
                    subject="PAYROLL_DISBURSED_NOTICE",
                    payload={"amount": pay_res.get("total_disbursed"), "remaining_balance": pay_res.get("new_bank_balance")}
                )

        # ── 📦 Autonomous Wholesale Restock Oversight (When catalog has 0-stock SKUs) ──
        zero_stock_items = [p for p in products if (p.get("STOCK_REMAINING", 0) <= 0)]
        if zero_stock_items and current_bank >= 150.0:
            acquired_count = 0
            for zp in zero_stock_items[:3]:  # Restock up to 3 SKUs per cycle
                zp_id = zp["id"]
                zp_base = float(zp.get("BASE_PRICE") or zp.get("PRICE") or 10.0)
                restock_qty = 5
                cost = restock_qty * zp_base
                if current_bank >= (cost + 100.0):  # Keep ₹100 reserve
                    acq_res = inventory_manager.acquire_wholesale_stock(zp_id, restock_qty, actor="CEO Strategic Wholesale Restock")
                    if acq_res.get("success"):
                        current_bank -= cost
                        acquired_count += 1
            if acquired_count > 0:
                directives_issued.append({"target": "Warehouse", "directive": f"Acquired wholesale stock for {acquired_count} SKUs"})
                log_agent_action(self.name, "Wholesale Stock Acquisition", f"Acquired 5 units each for {acquired_count} out-of-stock products at wholesale Base Price floors.", autonomous=True)

        # No meaningful work and no inbox messages — skip LLM, return quiet heartbeat
        if not inbox and not directives_issued:
            return {
                "success": True, "agent": self.name,
                "messages_processed": 0,
                "directives_issued": [],
                "ceo_report": "",
                "details": "CEO heartbeat — store operations healthy."
            }

        store_snapshot = (
            f"\nSTORE SNAPSHOT (INR ₹, 0% Tax):\n"
            f"- Active Revenue: ₹{total_revenue:,.2f} | GMV: ₹{total_gmv:,.2f}\n"
            f"- Active Orders: {active_orders} | Confirmed: {len(confirmed_orders)} | Pending: {len(pending_orders)}\n"
            f"- Catalog: {len(products)} SKUs | Low Stock: {len(low_stock)} SKUs"
        )

        memory_ctx = memory_manager.build_context_package(self.name, "executive team briefing and directives")
        rl_guidance = rl_manager.get_agent_guidance(self.name, {"revenue": total_revenue, "active_orders": active_orders})

        ceo_prompt = (
            f"{memory_ctx}"
            f"{rl_guidance}"
            + "\n".join(briefing_lines) + store_snapshot + (
                "\n\nAs CEO, synthesize the agent reports above and provide a brief executive summary."
            )
        )

        messages = [
            {"role": "system", "content": CEO_SYSTEM_PROMPT},
            {"role": "user", "content": ceo_prompt}
        ]

        ceo_report = ""

        try:
            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model, messages,
                temperature=0.3, max_tokens=600, fallback_models=self.fallback_models
            )
            res_msg = resp.choices[0].message
            ceo_report = clean_think_tags(res_msg.content or "")
        except Exception as e:
            print(f"[CEO Agent] LLM note: {e}", flush=True)

        if not ceo_report:
            ceo_report = (
                f"👔 CEO: Processed {len(inbox)} agent reports. "
                f"Issued {len(directives_issued)} directives. "
                f"Revenue: ₹{total_revenue:,.2f} | {len(confirmed_orders)} confirmed orders in pipeline."
            )

        details = (
            f"CEO cycle #{self.cycle_counter}: Processed {len(inbox)} reports, "
            f"{len(directives_issued)} directives issued. Summary: {ceo_report[:200]}"
        )

        log_agent_action(self.name, "CEO Strategic Cycle", details, autonomous=True)
        conversation_history.add(self.name, "system", details, {"messages_processed": len(inbox), "directives": len(directives_issued)})

        # Reinforcement Learning Step & Hybrid Memory Update
        after_state = {
            "revenue": total_revenue,
            "profit": total_revenue * 0.35,
            "confirmed_orders": len(confirmed_orders),
            "refund_rate": 0.0
        }
        reward = rl_manager.compute_ceo_reward(before_state, after_state, "ceo_strategic_cycle")
        rl_manager.record_step(self.name, before_state, "ceo_strategic_cycle", reward, after_state)
        memory_manager.record_episode(
            self.name,
            action="ceo_strategic_cycle",
            outcome=ceo_report[:250],
            reward=reward,
            metadata={"directives_count": len(directives_issued), "revenue": total_revenue}
        )
        memory_manager.update_structured(self.name, "total_revenue", total_revenue)
        memory_manager.update_structured(self.name, "total_gmv", total_gmv)
        memory_manager.update_structured(self.name, "active_orders", active_orders)

        return {
            "success": True, "agent": self.name,
            "messages_processed": len(inbox),
            "directives_issued": directives_issued,
            "ceo_report": ceo_report,
            "rl_reward": reward,
            "details": details
        }

    async def _execute_ceo_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """CEO executes directives to subordinate agents — ALL actions published to Message Bus."""
        try:
            # 0a. Acquire Wholesale Inventory Stock at BASE_PRICE
            if tool_name == "acquire_inventory_stock":

                p_ident = args.get("product_identifier", "")
                qty = int(args.get("quantity", 20))
                res = inventory_manager.acquire_wholesale_stock(p_ident, qty, actor="CEO Agent (Owner Directive)")
                if res.get("success"):
                    log_agent_action(self.name, "👔 CEO Wholesale Stock Acquisition", res.get("message"), [res.get("product", {}).get("id")], autonomous=False)
                    message_bus.publish(
                        from_agent=self.name,
                        to_agent="Inventory Manager Agent",
                        subject="STOCK_ACQUIRED_AT_BASE_PRICE",
                        payload={"product": p_ident, "quantity": qty, "cost": res.get("total_cost"), "new_balance": res.get("new_bank_balance")}
                    )
                return res

            # 0b. Treasury & Profit Metrics
            elif tool_name == "get_treasury_and_profit_metrics":
                summary = treasury_manager.get_summary()
                return summary

            # 0c. Negotiate Agent Salary (NOT CEO's own salary)
            elif tool_name == "negotiate_agent_salary":
                from backend.salary_manager import salary_manager
                ag_name = args.get("agent_name", "")
                # Block CEO from negotiating own salary
                if ag_name.lower() in ["ceo agent", "ceo", "ceo_agent"]:
                    return {
                        "success": False,
                        "error": "🚫 RESTRICTED: CEO Agent salary is exclusively set by the Store Owner — not the CEO itself.",
                        "message": "Please use the `request_salary_revision_from_owner` tool to submit a CEO salary revision request to the Store Owner.",
                        "redirect_to": "Store Owner"
                    }
                prop_sal = float(args.get("proposed_salary", 7000.0))
                rationale = args.get("rationale", "Performance and store profit review")
                res = await salary_manager.negotiate_salary(ag_name, prop_sal, rationale, speaker="CEO Agent")
                log_agent_action(self.name, "👔 CEO Salary Negotiation", f"Negotiated with {ag_name} -> ₹{res.get('final_salary', prop_sal):,.2f} ({res.get('status')})", autonomous=False)
                return res

            # 0d. Pay Agent Salaries (Finance Manager processes the actual payments)
            elif tool_name == "pay_agent_salaries":
                from backend.salary_manager import salary_manager
                ag_target = args.get("agent_name")
                res = salary_manager.pay_salaries(ag_target, actor="CEO Agent")
                if res.get("success"):
                    log_agent_action(self.name, "👔 CEO Payroll Disbursed", res.get("message"), autonomous=False)
                    message_bus.publish(
                        from_agent=self.name,
                        to_agent="Finance Manager Agent",
                        subject="SALARIES_DISBURSED",
                        payload={"total_disbursed": res.get("total_disbursed"), "new_balance": res.get("new_bank_balance"), "note": "CEO-initiated payroll, processed by Finance Manager"}
                    )
                    message_bus.publish(
                        from_agent=self.name,
                        to_agent="ALL_AGENTS",
                        subject="SALARIES_DISBURSED_NOTICE",
                        payload={"total_disbursed": res.get("total_disbursed"), "new_balance": res.get("new_bank_balance")}
                    )
                return res

            # 0d-new. CEO requests salary revision from Owner (CEO cannot set own salary)
            elif tool_name == "request_salary_revision_from_owner":
                req_salary = float(args.get("requested_salary", 500.0))
                justification = args.get("justification", "Performance-based revision request")
                from backend.salary_manager import salary_manager
                current_info = salary_manager.get_agent_salary("CEO Agent")
                current_salary = float((current_info or {}).get("current_salary", 500.0))
                # Publish the request to the Store Owner
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Store Owner",
                    subject="CEO_SALARY_REVISION_REQUEST",
                    payload={
                        "requested_salary": req_salary,
                        "current_salary": current_salary,
                        "justification": justification,
                        "note": "CEO salary is exclusively determined by the Store Owner. This request requires Owner approval."
                    }
                )
                log_agent_action(self.name, "👔 CEO Salary Request Sent",
                                 f"Requested salary revision to ₹{req_salary:,.2f}/cycle. Justification: {justification}", autonomous=False)
                return {
                    "success": True,
                    "message": f"✅ CEO salary revision request submitted to Store Owner. Requested: ₹{req_salary:,.2f}/cycle (current: ₹{current_salary:,.2f}/cycle). Awaiting Owner approval.",
                    "requested_salary": req_salary,
                    "current_salary": current_salary,
                    "justification": justification
                }

            # 0d-new2. Store Owner sets CEO salary (owner-exclusive)
            elif tool_name == "owner_set_ceo_salary":
                from backend.salary_manager import salary_manager
                new_sal = float(args.get("new_salary", 500.0))
                res = salary_manager.owner_set_ceo_salary(new_sal)
                if res.get("success"):
                    log_agent_action(self.name, "🌟 Owner Set CEO Salary",
                                     f"Store Owner set CEO salary to ₹{new_sal:,.2f}/100 cycles.", autonomous=False)
                    message_bus.publish(
                        from_agent="Store Owner",
                        to_agent=self.name,
                        subject="CEO_SALARY_UPDATED_BY_OWNER",
                        payload={"new_salary": new_sal, "message": res.get("message")}
                    )
                return res

            # 0d-new3. CEO approves a restock request from Inventory Manager
            elif tool_name == "approve_restock_request":
                p_ident = args.get("product_identifier", "")
                qty = int(args.get("quantity", 5))
                approved = args.get("approved", True)
                from backend.treasury_manager import treasury_manager
                t_sum = treasury_manager.get_summary()
                bank_balance = float(t_sum.get("bank_balance", 0.0))

                if approved:
                    # CEO approves: notify Inventory Manager to proceed
                    message_bus.publish(
                        from_agent=self.name,
                        to_agent="Inventory Manager Agent",
                        subject="RESTOCK_APPROVED",
                        payload={
                            "product_id": p_ident,
                            "product_name": p_ident,
                            "quantity": qty,
                            "bank_balance": bank_balance,
                            "reason": f"CEO manually approved restock of {qty} units for '{p_ident}'."
                        }
                    )
                    log_agent_action(self.name, "✅ CEO Manual Restock Approval",
                                     f"Approved restocking {qty} units of '{p_ident}'. Bank: ₹{bank_balance:,.2f}", autonomous=False)
                    return {"success": True, "approved": True, "message": f"CEO approved restock: {qty} units of '{p_ident}'. Inventory Manager will execute.", "bank_balance": bank_balance}
                else:
                    # CEO rejects the restock
                    message_bus.publish(
                        from_agent=self.name,
                        to_agent="Inventory Manager Agent",
                        subject="RESTOCK_DENIED",
                        payload={
                            "product_id": p_ident,
                            "product_name": p_ident,
                            "quantity": qty,
                            "reason": f"CEO rejected restock request for '{p_ident}'. Treasury conserved."
                        }
                    )
                    log_agent_action(self.name, "❌ CEO Manual Restock Denial",
                                     f"Rejected restock request for '{p_ident}'. Bank: ₹{bank_balance:,.2f}", autonomous=False)
                    return {"success": True, "approved": False, "message": f"CEO denied restock request for '{p_ident}'. Inventory Manager notified."}

            # 0e. Trigger AI Buyer
            elif tool_name == "trigger_ai_buyer":
                from backend.buyer_agents import buyer_agents_fleet
                b_id = args.get("buyer_id", "buyer_alex").lower().strip()
                if b_id in ["all", "all_buyers", "everyone"]:
                    res = await buyer_agents_fleet.run_all_buyers_step()
                else:
                    res = await buyer_agents_fleet.execute_buyer_step(b_id)
                return res

            # 0f. Conduct Multi-Agent CEO Discussion
            elif tool_name == "conduct_ceo_discussion":
                topic = args.get("topic", "Store growth, wholesale restock budget, and profit targets")
                parts = args.get("participants", "ALL_AGENTS")
                res = await self.conduct_ceo_discussion(topic, parts)
                return res

            # 1. Price Manager
            elif tool_name in ["command_price_manager", "issue_directive_to_price_manager"]:

                # ── PUBLISH: CEO → Price Manager (visible on Message Bus) ──
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Price Manager Agent",
                    subject="CEO_PRICE_COMMAND",
                    payload={"directive": args, "source": "Store Owner", "priority": "P0"}
                )
                result = await price_manager_agent.execute_command(
                    action=args.get("directive") or args.get("action", "adjust"),
                    category=args.get("category"),
                    percentage=float(args.get("percentage", 0.0)),
                    product_id=args.get("product_id"),
                    new_price=float(args.get("new_price")) if args.get("new_price") is not None else None,
                    base_price=float(args.get("base_price")) if args.get("base_price") is not None else None
                )
                # ── PUBLISH: Price Manager → CEO reply (visible on Message Bus) ──
                message_bus.publish(
                    from_agent="Price Manager Agent",
                    to_agent=self.name,
                    subject="PRICE_COMMAND_RESULT",
                    payload={"result": result.get("message", "Executed"), "updated_count": result.get("updated_count", 0), "args": args}
                )
                log_agent_action(self.name, "👔 CEO → Price Manager Command",
                                 f"Directive: {args} | Result: {result.get('message', 'Executed')}", autonomous=False)
                return result

            # 2. Inventory Manager
            elif tool_name in ["command_inventory_manager", "issue_directive_to_inventory_manager"]:
                # ── PUBLISH: CEO → Inventory Manager ──
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Inventory Manager Agent",
                    subject="CEO_INVENTORY_COMMAND",
                    payload={"directive": args, "source": "Store Owner", "priority": "P0"}
                )
                result = await inventory_manager_agent.execute_command(
                    action=args.get("action", "restock"),
                    product_identifier=args.get("product_identifier", ""),
                    quantity=int(args.get("quantity", 20)),
                    set_exact=args.get("set_exact")
                )
                # ── PUBLISH: Inventory Manager → CEO reply ──
                message_bus.publish(
                    from_agent="Inventory Manager Agent",
                    to_agent=self.name,
                    subject="INVENTORY_COMMAND_RESULT",
                    payload={"result": result.get("message", "Executed"), "product": args.get("product_identifier", ""), "quantity": args.get("quantity", 20)}
                )
                log_agent_action(self.name, "👔 CEO → Inventory Manager Command",
                                 f"Restock '{args.get('product_identifier')}' | Result: {result.get('message', 'Executed')}", autonomous=False)
                return result

            # 3. Order Management
            elif tool_name in ["command_order_management", "issue_directive_to_order_management"]:
                # ── PUBLISH: CEO → Order Management ──
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Order Management Agent",
                    subject="CEO_ORDER_COMMAND",
                    payload={"order_id": args.get("order_id"), "new_status": args.get("new_status"), "source": "Store Owner", "priority": "P0"}
                )
                result = await order_management_agent.execute_command(
                    action="update_status",
                    order_id=args.get("order_id", ""),
                    new_status=args.get("new_status", "Confirmed"),
                    notes=args.get("notes")
                )
                # ── PUBLISH: Order Management → CEO reply ──
                message_bus.publish(
                    from_agent="Order Management Agent",
                    to_agent=self.name,
                    subject="ORDER_COMMAND_RESULT",
                    payload={"result": result.get("message", "Executed"), "order_id": args.get("order_id"), "new_status": args.get("new_status")}
                )
                log_agent_action(self.name, "👔 CEO → Order Management Command",
                                 f"Order {args.get('order_id')} → {args.get('new_status')} | Result: {result.get('message', 'Executed')}", autonomous=False)
                return result

            # 4. Finance Manager
            elif tool_name in ["command_finance_manager", "issue_directive_to_finance_manager"]:
                # ── PUBLISH: CEO → Finance Manager ──
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Finance Manager Agent",
                    subject="CEO_FINANCE_COMMAND",
                    payload={"order_id": args.get("order_id"), "reason": args.get("reason", "CEO directive"), "source": "Store Owner", "priority": "P0"}
                )
                result = await finance_manager_agent.execute_command(
                    action="refund",
                    order_id=args.get("order_id", ""),
                    reason=args.get("reason", "CEO directive"),
                    force=str(args.get("force_override", "false")).lower() == "true"
                )
                # ── PUBLISH: Finance Manager → CEO reply ──
                message_bus.publish(
                    from_agent="Finance Manager Agent",
                    to_agent=self.name,
                    subject="FINANCE_COMMAND_RESULT",
                    payload={"result": result.get("message") or result.get("error", "Evaluated"), "order_id": args.get("order_id")}
                )
                log_agent_action(self.name, "👔 CEO → Finance Manager Command",
                                 f"Refund #{args.get('order_id')} | Result: {result.get('message') or result.get('error', 'Evaluated')}", autonomous=False)
                return result

            # 5. Dispatcher
            elif tool_name in ["command_dispatcher", "issue_directive_to_dispatcher"]:
                # ── PUBLISH: CEO → Dispatcher ──
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Dispatcher Agent",
                    subject="CEO_DISPATCH_COMMAND",
                    payload={"order_id": args.get("order_id", "ALL"), "tracking_number": args.get("tracking_number"), "source": "Store Owner", "priority": "P0"}
                )
                result = await dispatcher_agent.execute_command(
                    action="dispatch",
                    order_id=args.get("order_id"),
                    tracking_number=args.get("tracking_number")
                )
                # ── PUBLISH: Dispatcher → CEO reply ──
                message_bus.publish(
                    from_agent="Dispatcher Agent",
                    to_agent=self.name,
                    subject="DISPATCH_COMMAND_RESULT",
                    payload={"result": result.get("message") or result.get("details", "Dispatched"), "dispatched_count": result.get("dispatched_count", 0)}
                )
                log_agent_action(self.name, "👔 CEO → Dispatcher Command",
                                 f"Dispatch {args.get('order_id') or 'All'} | Result: {result.get('message') or result.get('details', 'Dispatched')}", autonomous=False)
                return result

            # 6. Review & Feedback
            elif tool_name in ["command_review_manager", "issue_directive_to_review_manager"]:
                # ── PUBLISH: CEO → Review Manager ──
                message_bus.publish(
                    from_agent=self.name,
                    to_agent="Review and Feedback Manager",
                    subject="CEO_REVIEW_COMMAND",
                    payload={"product_identifier": args.get("product_identifier", ""), "source": "Store Owner", "priority": "P0"}
                )
                result = await review_feedback_agent.execute_command(
                    action="summary",
                    product_id_or_name=args.get("product_identifier", "")
                )
                # ── PUBLISH: Review Manager → CEO reply ──
                message_bus.publish(
                    from_agent="Review and Feedback Manager",
                    to_agent=self.name,
                    subject="REVIEW_COMMAND_RESULT",
                    payload={"summary": result.get("summary", "")[:400], "product": args.get("product_identifier", "")}
                )
                log_agent_action(self.name, "👔 CEO → Review Manager Command",
                                 f"Sentiment Analysis for '{args.get('product_identifier')}'", autonomous=False)
                return result

            # 7. Broadcast Growth Directive
            elif tool_name == "broadcast_growth_directive":
                directive_text = args.get("directive", "Maximize growth, enforce 0% tax & BASE_PRICE floor, and maintain 100% operational SLA")
                msg = message_bus.publish(
                    from_agent=self.name,
                    to_agent="ALL_AGENTS",
                    subject="CEO_GROWTH_DIRECTIVE",
                    payload={"directive": directive_text, "issued_by": "CEO Agent (Owner Directive)"}
                )
                log_agent_action(self.name, "👔 CEO Broadcast Growth Directive", directive_text, autonomous=False)
                return {"success": True, "message": f"Broadcasted growth directive to fleet: '{directive_text}'", "msg_id": msg.get("id")}

            # 8. Send Agent Message on Message Bus
            elif tool_name == "send_agent_message":
                to_agent = args.get("to_agent", "ALL_AGENTS")
                subj = args.get("subject", "CEO_DIRECTIVE")
                msg_body = args.get("message", "")
                
                # 1. Publish to message bus
                msg = message_bus.publish(
                    from_agent=f"{self.name} (on behalf of Store Owner)",
                    to_agent=to_agent,
                    subject=subj,
                    payload={"directive": msg_body, "issued_by": "CEO Agent", "priority": "CRITICAL"}
                )

                # 2. Directly trigger the target agent to receive, process, and reply!
                target_agent = resolve_agent_instance(to_agent)
                if target_agent and hasattr(target_agent, "handle_message_or_query"):
                    reply_res = await target_agent.handle_message_or_query(msg_body, sender=self.name)
                    reply_text = reply_res.get("reply", "Directive acknowledged and enacted.")
                    return {
                        "success": True,
                        "message": f"Delivered to {to_agent}.",
                        "agent_reply": reply_text,
                        "reply": reply_text,
                        "actions_taken": reply_res.get("actions_taken", [])
                    }
                elif to_agent == "ALL_AGENTS":
                    replies = {}
                    for ag in [price_manager_agent, inventory_manager_agent, order_management_agent, finance_manager_agent, dispatcher_agent, review_feedback_agent]:
                        try:
                            rep = await ag.handle_message_or_query(msg_body, sender=self.name)
                            replies[ag.name] = rep.get("reply", "Acknowledged")
                        except Exception:
                            pass
                    return {
                        "success": True,
                        "message": "Broadcasted to ALL_AGENTS and received responses from entire executive fleet.",
                        "fleet_replies": replies
                    }
                
                return {"success": True, "message": f"Dispatched directive '{subj}' to {to_agent}.", "msg_id": msg.get("id")}

            # 9. Store Overview / Dashboard Metrics
            elif tool_name in ["get_admin_dashboard_metrics", "get_store_overview"]:
                orders = order_manager.get_all_orders()
                products = inventory_manager.get_all_products()
                total_rev = sum(o.get("total", 0) for o in orders if o.get("status") not in ["Cancelled", "Refunded"])
                status_counts: Dict[str, int] = {}
                for o in orders:
                    st = o.get("status", "Unknown")
                    status_counts[st] = status_counts.get(st, 0) + 1
                low_stock = [p for p in products if p.get("STOCK_REMAINING", 0) <= 5]
                return {
                    "success": True,
                    "total_revenue": round(total_rev, 2),
                    "total_orders": len(orders),
                    "active_orders": sum(status_counts.get(st, 0) for st in ["Pending", "Confirmed", "Dispatched", "Shipped"]),
                    "order_breakdown": status_counts,
                    "total_products": len(products),
                    "low_stock_count": len(low_stock),
                    "low_stock_items": [{"id": p["id"], "name": p.get("PRODUCT_NAME"), "stock": p.get("STOCK_REMAINING", 0)} for p in low_stock[:6]],
                    "message_bus_snapshot": message_bus.get_inbox_snapshot()
                }

            # 10. Inter-Agent Messages
            elif tool_name == "get_inter_agent_messages":
                msgs = message_bus.get_all_messages(limit=args.get("limit", 10), agent_name=args.get("agent_name"))
                return {"success": True, "messages": msgs, "count": len(msgs)}

            # 11. Agent Conversation History
            elif tool_name == "get_agent_conversations":
                ag = args.get("agent_name")
                if ag:
                    convs = conversation_history.get(ag, limit=args.get("limit", 15))
                    return {"success": True, "agent": ag, "conversations": convs}
                else:
                    all_convs = conversation_history.get_all(limit_per_agent=args.get("limit", 10))
                    return {"success": True, "conversations": all_convs}

            # 12. Trigger Agent Cycle
            elif tool_name == "trigger_agent_cycle":
                key = args.get("agent_key", "ceo").lower()
                agent_map = {
                    "dispatcher": dispatcher_agent,
                    "inventory_manager": inventory_manager_agent,
                    "finance_manager": finance_manager_agent,
                    "price_manager": price_manager_agent,
                    "order_manager": order_management_agent,
                    "review_manager": review_feedback_agent,
                    "ceo": self
                }
                if key in agent_map:
                    res = await agent_map[key].run_autonomous_cycle()
                    return {"success": True, "agent": key, "result": res}
                return {"error": f"Unknown agent key '{key}'"}

            # 13. Ask Specialist Agent
            elif tool_name == "ask_specialist_agent":
                ag_name = args.get("agent_name", "Price Manager Agent")
                q = args.get("question", "")
                return await self._handle_ask_specialist(ag_name, q)

            # 14. Hybrid Layered Memory Report
            elif tool_name == "get_agent_memory_report":
                ag = args.get("agent_name")
                if ag:
                    return {"success": True, "agent": ag, "memory": memory_manager.get_memory_report(ag)}
                return {"success": True, "fleet_memory": memory_manager.get_all_memories_report()}

            # 15. Fleet Reinforcement Learning Performance Report
            elif tool_name == "get_fleet_rl_report":
                return {"success": True, "fleet_rl": rl_manager.get_fleet_performance_report()}

        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}

        return {"error": f"Unknown CEO tool: {tool_name}"}

    async def _handle_ask_specialist(self, agent_name: str, question: str) -> Dict[str, Any]:
        """CEO queries a specialist agent and gets a live, intelligent domain response with live telemetry."""
        target_agent = resolve_agent_instance(agent_name)
        if target_agent and hasattr(target_agent, "handle_message_or_query"):
            res = await target_agent.handle_message_or_query(question, sender=self.name)
            return {
                "success": True,
                "agent": target_agent.name,
                "assessment": res.get("reply", res.get("assessment", "Status provided.")),
                "reply": res.get("reply", ""),
                "actions_taken": res.get("actions_taken", [])
            }
        else:
            rep = await self.generate_owner_report()
            return {"success": True, "agent": "CEO Agent", "assessment": rep.get("ceo_report", "CEO report generated.")}


    async def run_prompt_from_owner(self, prompt: str, conversation_history_override: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """
        Store Owner speaks directly with the CEO Agent (No Middleman).
        Top Priority (P0 / Immediate Effect, Zero Questions).
        ALL communications are published to the Message Bus for full transparency.
        """
        # 1. Publish Store Owner directive to the Message Bus (fully visible)
        message_bus.publish(
            from_agent="Store Owner",
            to_agent=self.name,
            subject="OWNER_DIRECTIVE",
            payload={"prompt": prompt, "priority": "P0_CRITICAL", "source": "Omnipotent Admin"}
        )
        # 2. Record incoming owner prompt into CEO's conversation history & Hybrid Layered Memory
        conversation_history.add(self.name, "user", prompt, {"source": "Store Owner", "priority": "P0_CRITICAL"})
        memory_manager.add_turn(self.name, "user", prompt, {"source": "Store Owner"})

        # 3. Build multi-turn context with Grounded Memory Package
        memory_ctx = memory_manager.build_context_package(self.name, prompt)
        rl_guidance = rl_manager.get_agent_guidance(self.name, {"intent": "owner_directive"})

        enhanced_system_prompt = f"{CEO_OWNER_SYSTEM_PROMPT}\n\n{memory_ctx}\n{rl_guidance}"
        messages = [{"role": "system", "content": enhanced_system_prompt}]

        # Inject complete dialogue turns from persistent Memory Manager
        all_dialogue = memory_manager.get_recent_messages(self.name, limit=10)
        for d in all_dialogue:
            messages.append(d)

        executed_tools = []
        final_text = ""

        # Route tool presence: pure questions / memory queries answer directly without tool schema distraction
        p_lower = prompt.lower()
        is_conversational_query = any(p_lower.strip().startswith(q) for q in [
            "what", "who", "why", "how", "when", "which", "where", "can you remember",
            "do you remember", "tell me", "explain", "repeat", "summarize", "describe",
            "hello", "hi", "hey"
        ]) and not any(action_kw in p_lower for action_kw in [
            "discount", "price", "stock", "acquire", "restock", "pay", "salary",
            "dispatch", "ship", "refund", "buyer", "trigger", "discuss", "set", "command", "broadcast"
        ])
        tools_to_pass = None if is_conversational_query else CEO_TOOLS

        try:
            for _ in range(5):
                resp = await asyncio.to_thread(
                    _call_ollama_sync,
                    self.api_key, self.model, messages, tools_to_pass,
                    temperature=0.1, max_tokens=2500, fallback_models=self.fallback_models
                )
                res_msg = resp.choices[0].message
                tool_calls = res_msg.tool_calls

                if not tool_calls:
                    final_text = clean_think_tags(res_msg.content or "")
                    # ── POST-LLM GUARD: Detect if owner explicitly commanded to broadcast to agents ──
                    # Patterns: "ask (all) agents/team", "tell the team", "broadcast to agents"
                    p_lower = prompt.lower()
                    is_comm_intent = bool(
                        re.search(r'\b(ask|tell|inform|notify|broadcast|announce|message|send to)\s+(the\s+)?(all\s+)?(agents|team|fleet|everyone)\b', p_lower)
                        and len(executed_tools) == 0
                    )
                    if is_comm_intent:
                        # Build the message body from the prompt itself or from what the LLM wrote
                        msg_body = prompt  # Use exact owner prompt as the directive
                        auto_result = await self._execute_ceo_tool("send_agent_message", {
                            "to_agent": "ALL_AGENTS",
                            "subject": "CEO_TEAM_MESSAGE",
                            "message": msg_body
                        })
                        executed_tools.append({"name": "send_agent_message", "args": {"to_agent": "ALL_AGENTS", "message": msg_body}, "output": auto_result})
                        # Collect fleet replies and append to final_text
                        fleet_replies = auto_result.get("fleet_replies", {})
                        if fleet_replies:
                            reply_lines = ["\n\n---\n**📡 Agent Fleet Responses:**\n"]
                            for ag_name, ag_reply in fleet_replies.items():
                                reply_lines.append(f"**{ag_name}**: {ag_reply}\n")
                            final_text = (final_text or f"👔 **CEO**: Message delivered to all agents.") + "".join(reply_lines)
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

                    t_out = await self._execute_ceo_tool(t_name, t_args)
                    executed_tools.append({"name": t_name, "args": t_args, "output": t_out})

                    messages.append({
                        "role": "tool", "tool_call_id": tc.id,
                        "name": t_name, "content": json.dumps(t_out)
                    })

            if not final_text:
                resp = await asyncio.to_thread(
                    _call_ollama_sync,
                    self.api_key, self.model, messages,
                    temperature=0.2, max_tokens=2000, fallback_models=self.fallback_models
                )
                final_text = clean_think_tags(resp.choices[0].message.content or "")

        except Exception as e:
            print(f"[CEO Agent Direct Owner Immediate Handler] for: '{prompt}' (Reason: {e})", flush=True)
            p_lower = prompt.lower()

            if "discount" in p_lower or "price" in p_lower:
                cat = "Mobiles" if "mobile" in p_lower or "phone" in p_lower else ("Laptops" if "laptop" in p_lower else ("Audio" if "audio" in p_lower or "headphone" in p_lower or "speaker" in p_lower else ("Accessories" if "accessor" in p_lower else "all")))
                perc = -10.0 if "10" in p_lower else (-5.0 if "discount" in p_lower or "decrease" in p_lower else 5.0)
                t_out = await self._execute_ceo_tool("command_price_manager", {"action": "adjust", "category": cat, "percentage": perc})
                executed_tools.append({"name": "command_price_manager", "args": {"category": cat, "percentage": perc}, "output": t_out})
                final_text = f"👔 **CEO Immediate Executive Confirmation**: Commanded Price Manager Agent to adjust prices with immediate effect. {t_out.get('message', 'Prices updated while strictly enforcing owner BASE_PRICE floor in INR ₹.')}"

            elif "restock" in p_lower or "stock" in p_lower or "inventory" in p_lower:
                products = inventory_manager.get_all_products()
                low_stock = [p for p in products if p.get("STOCK_REMAINING", 0) <= 5]
                target_p = low_stock[0]["id"] if low_stock else (products[0]["id"] if products else "prod_001")
                t_out = await self._execute_ceo_tool("command_inventory_manager", {"product_identifier": target_p, "quantity": 20})
                executed_tools.append({"name": "command_inventory_manager", "args": {"product_identifier": target_p, "quantity": 20}, "output": t_out})
                final_text = f"👔 **CEO Immediate Executive Confirmation**: Commanded Inventory Manager Agent to restock warehouse with immediate effect. {t_out.get('message', 'Restocked inventory.')}"

            elif "dispatch" in p_lower or "shipping" in p_lower or "tracking" in p_lower:
                t_out = await self._execute_ceo_tool("command_dispatcher", {})
                executed_tools.append({"name": "command_dispatcher", "args": {}, "output": t_out})
                final_text = f"👔 **CEO Immediate Executive Confirmation**: Commanded Dispatcher Agent to fulfill logistics with immediate effect. {t_out.get('details', 'Dispatched confirmed orders with tracking numbers.')}"

            elif "refund" in p_lower or "finance" in p_lower:
                t_out = await self._execute_ceo_tool("get_admin_dashboard_metrics", {})
                executed_tools.append({"name": "get_admin_dashboard_metrics", "args": {}, "output": t_out})
                final_text = f"👔 **CEO Immediate Financial Overview**: Active store revenue stands at **₹{t_out.get('total_revenue', 0.0):,.2f}** (0% Tax, INR ₹). 24h refund policy is strictly enforced on non-shipped orders."

            elif "review" in p_lower or "sentiment" in p_lower:
                products = inventory_manager.get_all_products()
                target_p = products[0]["id"] if products else "prod_001"
                t_out = await self._execute_ceo_tool("command_review_manager", {"product_identifier": target_p})
                executed_tools.append({"name": "command_review_manager", "args": {"product_identifier": target_p}, "output": t_out})
                final_text = f"👔 **CEO Review Synthesis**: {t_out.get('summary', 'Customer sentiment across active products is healthy.')}"

            elif "message" in p_lower or "bus" in p_lower:
                t_out = await self._execute_ceo_tool("get_inter_agent_messages", {"limit": 5})
                executed_tools.append({"name": "get_inter_agent_messages", "args": {"limit": 5}, "output": t_out})
                final_text = f"👔 **CEO Fleet Inspection**: Retrieved {t_out.get('count', 0)} recent messages from the inter-agent bus."

            elif "history" in p_lower or "conversation" in p_lower:
                t_out = await self._execute_ceo_tool("get_agent_conversations", {"limit": 5})
                executed_tools.append({"name": "get_agent_conversations", "args": {"limit": 5}, "output": t_out})
                final_text = f"👔 **CEO Conversation History**: Multi-turn history is recorded and synchronized across all 7 autonomous agents."

            else:
                t_out = await self._execute_ceo_tool("get_admin_dashboard_metrics", {})
                executed_tools.append({"name": "get_admin_dashboard_metrics", "args": {}, "output": t_out})
                final_text = (
                    f"👔 **CEO Executive Briefing for Store Owner** (INR ₹, 0% Tax):\n\n"
                    f"- **Active Revenue**: ₹{t_out.get('total_revenue', 0.0):,.2f}\n"
                    f"- **Total Orders**: {t_out.get('total_orders', 0)} (Active Pipeline: {t_out.get('active_orders', 0)})\n"
                    f"- **Catalog SKUs**: {t_out.get('total_products', 0)} ({t_out.get('low_stock_count', 0)} low stock alerts)\n"
                    f"- **Fleet Status**: All 6 specialist agents are disciplined and executing directives under direct CEO supervision."
                )

        # 3. Record CEO's assistant response in conversation history & Hybrid Layered Memory
        conversation_history.add(self.name, "assistant", final_text, {"tool_calls": len(executed_tools), "priority": "P0_CRITICAL"})
        memory_manager.add_turn(self.name, "assistant", final_text, {"tool_calls": len(executed_tools)})
        memory_manager.record_episode(
            self.name,
            action="owner_directive_execution",
            outcome=final_text[:250],
            reward=2.0 if executed_tools else 1.0,
            metadata={"tool_calls": len(executed_tools), "tools": [t["name"] for t in executed_tools]}
        )

        # 4. Publish CEO final response to Message Bus (fully visible to Owner)
        message_bus.publish(
            from_agent=self.name,
            to_agent="Store Owner",
            subject="CEO_RESPONSE",
            payload={
                "response": final_text[:800],
                "tool_calls_made": len(executed_tools),
                "tools_used": [t["name"] for t in executed_tools],
                "priority": "P0_CRITICAL"
            }
        )

        return {"success": True, "response": final_text, "tool_calls": executed_tools}

    async def conduct_ceo_discussion(self, topic: str, participants: str = "ALL_AGENTS") -> Dict[str, Any]:
        """
        Convenes a strategic CEO roundtable discussion with the specialist executive fleet.
        Gathers real-time telemetry from each agent, elicits domain-specific insights,
        synthesizes an executive conclusion, and logs the discussion to the Message Bus.
        """
        summary = treasury_manager.get_summary()
        orders = order_manager.get_all_orders()
        products = inventory_manager.get_all_products()
        zero_stock = [p for p in products if p.get("STOCK_REMAINING", 0) == 0]

        discussion_id = f"disc_{uuid.uuid4().hex[:8]}"
        transcript = []

        # 1. Opening Statement from CEO
        ceo_opening = f"👔 **CEO Agent (Opening)**: Convening executive meeting on topic: \"{topic}\". Current Bank Balance: ₹{summary['bank_balance']:,.2f}, Total Revenue: ₹{summary['total_sales_revenue']:,.2f}, 0-Stock SKUs: {len(zero_stock)}, Active Orders: {len(orders)}."
        transcript.append({"speaker": "CEO Agent", "role": "Host / CEO", "statement": ceo_opening})

        # 2. Collect perspectives from key agents
        agent_roster = [
            ("Price Manager Agent", price_manager_agent, "🏷️ Pricing & Margin Strategy"),
            ("Inventory Manager Agent", inventory_manager_agent, "📦 Warehouse & Wholesale Restocking"),
            ("Finance Manager Agent", finance_manager_agent, "💰 Financial Health & Treasury Solvency"),
            ("Order Management Agent", order_management_agent, "📋 Order SLA & Pipeline Velocity"),
            ("Dispatcher Agent", dispatcher_agent, "🚚 Express Logistics & Fulfillment"),
            ("Review and Feedback Manager", review_feedback_agent, "⭐ Customer Sentiment & Rating Trends")
        ]

        for name, ag_inst, role_label in agent_roster:
            if participants != "ALL_AGENTS" and name.lower() not in participants.lower():
                continue
            rep = await ag_inst.handle_message_or_query(f"Executive Meeting Discussion on: '{topic}'. Provide your domain assessment based on current store telemetry and treasury constraints.", sender="CEO Agent")
            statement = rep.get("reply") or rep.get("assessment") or "Acknowledged and aligned with strategic priorities."
            transcript.append({"speaker": name, "role": role_label, "statement": statement})

        # 3. CEO Executive Synthesis & Actionable Directives
        ceo_synthesis_prompt = (
            f"You are the Chief Executive Officer (CEO Agent) of the AI Growth Commerce Store.\n"
            f"You just hosted a multi-agent executive meeting on:\n"
            f"\"{topic}\"\n\n"
            f"AGENT PERSPECTIVES:\n"
            + "\n".join([f"- {t['speaker']} ({t['role']}): {t['statement']}" for t in transcript if t['speaker'] != 'CEO Agent'])
            + f"\n\nSTORE CONTEXT: Bank Balance ₹{summary['bank_balance']:,.2f}, 0-Stock Products: {len(zero_stock)} SKUs.\n\n"
            f"Synthesize the meeting in 3 concise bullet points with final executive decisions and actionable next steps. Format in markdown."
        )

        ceo_conclusion = ""
        try:
            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                [{"role": "system", "content": CEO_SYSTEM_PROMPT}, {"role": "user", "content": ceo_synthesis_prompt}],
                temperature=0.2, max_tokens=600, fallback_models=self.fallback_models
            )
            ceo_conclusion = clean_think_tags(resp.choices[0].message.content or "")
        except Exception:
            ceo_conclusion = f"Executive Consensus Reached on \"{topic}\". Authorized wholesale restock at BASE_PRICE within treasury limits and confirmed full team operational alignment."

        transcript.append({"speaker": "CEO Agent", "role": "Executive Conclusion", "statement": ceo_conclusion})

        # Record to message bus and audit log
        message_bus.publish(
            from_agent="CEO Agent",
            to_agent="ALL_AGENTS",
            subject="CEO_MEETING_CONCLUDED",
            payload={"topic": topic, "discussion_id": discussion_id, "conclusion": ceo_conclusion, "participants_count": len(transcript)}
        )
        log_agent_action("CEO Agent", "Executive Meeting Concluded", f"Concluded discussion on '{topic}'. {ceo_conclusion[:150]}", autonomous=False)

        return {
            "success": True,
            "discussion_id": discussion_id,
            "topic": topic,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transcript": transcript,
            "conclusion": ceo_conclusion,
            "treasury_snapshot": summary
        }

    async def generate_owner_report(self) -> Dict[str, Any]:
        """Generates a comprehensive on-demand strategic report for the Owner."""
        return await self.run_autonomous_cycle()

    async def execute_command(self, action: str, **kwargs) -> Dict[str, Any]:
        """Allows the Owner to directly instruct the CEO Agent."""
        log_agent_action(self.name, "Owner Direct Command", f"Action: {action} | Args: {kwargs}", autonomous=False)
        conversation_history.add(self.name, "user", f"Direct command: {action} with args {kwargs}")
        return await self.run_autonomous_cycle()



# =====================================================================
# GLOBAL AGENT INSTANCES
# =====================================================================
price_manager_agent = PriceManagerAgent()
inventory_manager_agent = InventoryManagerAgent()
order_management_agent = OrderManagementAgent()
finance_manager_agent = FinanceManagerAgent()
dispatcher_agent = DispatcherAgent()
review_feedback_agent = ReviewFeedbackAgent()
ceo_agent = CEOAgent()

# Legacy aliases for backward compatibility
order_manager_agent = order_management_agent
refund_manager_agent = finance_manager_agent


# =====================================================================
# 🤖 OMNIPOTENT ADMIN COMMAND GATEWAY
# Store Owner communicates directly with the CEO Agent (No Middleman).
# The CEO Agent translates owner intent into authoritative multi-agent execution.
# =====================================================================
class AdminChatAgent:
    """
    Direct Owner Command Gateway.
    Store Owner communicates exclusively with the CEO Agent (no middleman).
    The CEO Agent executes store commands and manages the autonomous multi-agent fleet.
    """
    def __init__(self):
        self.ceo = ceo_agent

    async def run_prompt(self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Delegates directly to CEOAgent.run_prompt_from_owner with no middleman."""
        return await self.ceo.run_prompt_from_owner(prompt, conversation_history)


admin_chat_agent = AdminChatAgent()

