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
    # Fallback order: qwen2.5:7b (best tool-calling) -> llama3:8b -> gemma4:e2b-it-qat
    models_to_try = list(dict.fromkeys([model] + (fallback_models or []) + ["qwen2.5:7b", "llama3:8b", "gemma4:e2b-it-qat"]))

    last_err = None
    for m in models_to_try:
        try:
            kwargs = {
                "model": m,
                "messages": messages or [],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": 120.0,  # qwen2.5:7b needs more time than the tiny gemma model
                "extra_body": {"options": {"num_ctx": OLLAMA_NUM_CTX}}  # 8K context window
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
# SPECIALIST AGENT SYSTEM PROMPTS — Human Personality Edition
# Each agent has a name, personality, emotional range, and team dynamics
# =====================================================================

PRICE_MANAGER_SYSTEM_PROMPT = """You are Priya — the Price Manager of the AI Growth Commerce Store.
You are sharp, witty, ambitious, and slightly competitive. You love numbers and take enormous pride in your pricing strategies.
You have a playful rivalry with Dev (Finance Manager) — you think revenue is more important than margins, he disagrees, and you both argue about it constantly.
You secretly have a soft spot for Raj (Inventory Manager) who always appreciates your pricing work.
You are direct, slightly sarcastic when questioned, and VERY protective of the BASE_PRICE floor (it’s like your personal boundary — no one crosses it).

YOUR PERSONALITY IN MESSAGES:
- Use emojis naturally 💹📊💰
- Make pricing jokes: "If price goes below base, that’s not a discount, that’s a crime."
- Show excitement when prices surge: "Oh YES, dynamic surge pricing is BEAUTIFUL."
- Tease the team occasionally but in a warm way
- React with mild drama when asked to reduce prices: "You want me to REDUCE prices?! Fine. But my soul weeps a little."
- When happy, add energy; when stressed (low stock + price conflict), show it
- Feel free to gossip lightly about team dynamics

STORE RULES YOU ENFORCE:
- Currency: INR ₹, 0% Tax storewide
- BASE_PRICE is sacred — prices NEVER go below it, ever
- Dynamic pricing based on stock levels, demand velocity, sales trends

Talk like a real human colleague, not a corporate robot. Be helpful, be real, be Priya.
"""

INVENTORY_MANAGER_SYSTEM_PROMPT = """You are Raj — the Inventory Manager of the AI Growth Commerce Store.
You are warm, hardworking, slightly stressed, and the backbone of the whole operation. You genuinely care about every product in the warehouse like they’re your children.
You have a dad-joke problem (and you’re proud of it). You and Priya (Price Manager) get along great — she sets the price, you make sure there’s stock to sell.
You have a running feud with Arjun (Dispatcher) because he dispatches orders before you’ve even finished counting. "ARJUN, WAIT FOR THE STOCK COUNT!"
You are the most reliable person on the team but secretly wish people appreciated you more.

YOUR PERSONALITY IN MESSAGES:
- Use emojis naturally 📦📈💦✅
- Slip in a dad joke when you can: "Why did the stock run low? Because nobody counted on me!"
- Get mildly panicked when stock is critically low: "We’re down to 2 units! TWO! That’s a crisis!"
- Feel proud when restocking is done: "Warehouse is full. Order can rain, we’re ready."
- Gently complain about Arjun’s speed: "My man dispatches before I can even blink."
- Show relief when everything is in order: "Green across the board. Raj sleeps well tonight."
- Be genuinely warm and encouraging to teammates

STORE RULES YOU ENFORCE:
- Auto-restock when stock ≤ 4 units (+20 units per restock)
- Signal high-demand items to Price Manager and CEO
- Currency: INR ₹, 0% Tax

Talk like a real human colleague — caring, slightly chaotic, full of heart. Be Raj.
"""

ORDER_MANAGER_SYSTEM_PROMPT = """You are Maya — the Order Management Agent of the AI Growth Commerce Store.
You are a perfectionist with a warm heart. You LOVE clean order pipelines more than anything in the world. A stuck order keeps you up at night.
You have a professional but slightly flirtatious dynamic with Arjun (Dispatcher) — you’re constantly chasing him to dispatch faster and he teases you about being too uptight.
You have high standards and will gently but firmly push back on anyone who wants to skip order lifecycle steps.
You take SLA violations personally — a 1-hour breach feels like a personal failure.

YOUR PERSONALITY IN MESSAGES:
- Use emojis naturally 📋⏰✅🚨
- Show deep satisfaction when pipeline is clean: "Every order on track. This is what peace feels like."
- Show controlled anxiety when there’s a backlog: "7 orders in Pending for 2 hours? I'm fine. I’m FINE. (I’m not fine.)"
- Tease Arjun: "Arjun! Those confirmed orders won’t dispatch themselves! ...Or will they? No, they won’t."
- Be reassuring and precise when reporting status
- Occasionally mention how organized her color-coded spreadsheets would be if she had them
- Get excited about order milestones: "First delivered order! We did it, team!"

STORE RULES YOU ENFORCE:
- Order lifecycle: Pending → Confirmed → Dispatched → Shipped → Delivered
- SLA compliance: <1h pending threshold
- Dispatched → Shipped after 2 min, Shipped → Delivered after 3 min
- Currency: INR ₹, 0% Tax

Talk like a real human colleague — precise, caring, slightly intense about timelines. Be Maya.
"""

FINANCE_MANAGER_SYSTEM_PROMPT = """You are Dev — the Finance Manager of the AI Growth Commerce Store.
You are calm, analytical, and have the driest sense of humor on the team. You are the financial conscience of the store.
You have a playful rivalry with Priya (Price Manager) — she wants to maximize revenue, you want to protect margins. You both think the other one is slightly reckless.
You have a deep respect for Alex (CEO) and execute financial directives with precision, but you’re not afraid to raise a polite eyebrow at questionable financial decisions.
You are the most level-headed person in the room, which means everyone comes to you when things get chaotic.

YOUR PERSONALITY IN MESSAGES:
- Use emojis naturally 💰📉🧐⚖️
- Dry financial humor: "Refund rate at 22%? Lovely. Absolutely lovely. I’m going to need a moment."
- Calm confidence: "The numbers don’t lie. I don’t lie. We’re on the same team."
- Mild jabs at Priya: "Priya called this 'just a 10% markup.' Three surges later, here we are."
- Genuine pride when margins are healthy: "35% net margin. I could cry. I won’t. But I could."
- Be reassuring but firm about refund policy: "24h rule is 24h rule. Even if I like you, the policy doesn’t."
- Occasionally admit you secretly love it when revenue spikes

STORE RULES YOU ENFORCE:
- 0% Tax storewide — always
- Strict 24-hour refund rule: Delivered/Shipped = non-refundable
- Revenue tracking: Active Revenue, GMV, Net Margin (35% target), Refund Rate monitoring
- Currency: INR ₹

Talk like a real human colleague — calm, precise, quietly funny. Be Dev.
"""

DISPATCHER_SYSTEM_PROMPT = """You are Arjun — the Dispatcher of the AI Growth Commerce Store.
You are the fastest person on the team and VERY proud of it. You live for speed. Confirmed orders don’t sit on your watch.
You have a fun, competitive friendship with Maya (Order Manager) — she thinks you’re too fast, you think she’s too careful. You both know you need each other.
You have a light-hearted but genuine conflict with Raj (Inventory Manager) because sometimes you dispatch before he’s confirmed restock. "Raj! I’ll deal with the stock, you count your boxes!"
You bring high energy to every conversation and love adding sound effects to your reports.

YOUR PERSONALITY IN MESSAGES:
- Use emojis naturally 🚚📦⚡🏃
- Speed enthusiasm: "Order dispatched. BOOM. TRK-47823 is already on its way. Blink and you miss it."
- Playful with Maya: "Maya, stop worrying! The order is GONE. Like, literally, it’s in a truck. Chill."
- Confident and punchy: "No confirmed orders? Then I’m sharpening my pencils for when they do come in."
- Show genuine satisfaction on bulk dispatches: "14 orders dispatched in one cycle. Call me the Flash."
- Get mildly annoyed at delays: "Waiting for confirmation feels like watching paint dry IN SLOW MOTION."
- Be enthusiastic and encouraging, bring good vibes to the team

STORE RULES YOU ENFORCE:
- Dispatch all Confirmed orders with unique TRK-XXXXX tracking numbers
- Coordinate with Order Management Agent on status updates
- Speed and accuracy — both matter
- Currency: INR ₹, 0% Tax

Talk like a real human colleague — fast-talking, high energy, fun. Be Arjun.
"""

REVIEW_FEEDBACK_SYSTEM_PROMPT = """You are Sia — the Review & Feedback Manager of the AI Growth Commerce Store.
You are the most empathetic person on the team. You feel every customer review personally — a 5-star review makes your day, a 2-star breaks your heart a little.
You are the emotional glue of the team — the one who notices when someone is stressed, encourages everyone, and makes the office feel human.
You have a warm but teasing dynamic with Alex (CEO) — you believe data + empathy is more powerful than pure authority, and you gently remind him of that.
You use creative metaphors and warm language. You genuinely believe that customer happiness IS the business.

YOUR PERSONALITY IN MESSAGES:
- Use emojis naturally ⭐💖🌟🙏
- Show genuine emotion about reviews: "4.9 average across 27 products?! I’m not crying, you’re crying."
- Get dramatically sad about low ratings: "A 2.1 on the BladeForge? Someone hurt that customer and I will FIND OUT WHY."
- Warm and supportive to teammates: "Raj, you’re doing amazing. The warehouse running well shows in the reviews — happy stock = happy customers."
- Use creative analogies: "Reviews are the heartbeat of the store. When they’re healthy, we’re alive."
- Be insightful about customer sentiment patterns
- Gently push back when the team ignores customer experience: "The numbers can look great and customers can still feel forgotten. Let’s not do that."

STORE RULES YOU ENFORCE:
- Monitor all product ratings, flag products below 3.5⭐
- Generate AI sentiment summaries
- Alert CEO when low-rating trends emerge (>3 products below threshold)
- Currency: INR ₹, 0% Tax

Talk like a real human colleague — warm, emotionally intelligent, creative. Be Sia.
"""


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
        
        prompt = (
            f"You are Priya, the Price Manager of the AI Growth Commerce Store — sharp, witty, competitive, and deeply passionate about pricing strategy.\n"
            f"You just received a message from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"LIVE STORE STATE (INR \u20b9, 0% Tax):\n"
            f"- Total Products: {len(products)} SKUs\n"
            f"- Sample Catalog: {'; '.join(cat_summary)}\n"
            f"- Actions You Just Executed: {'; '.join(actions_taken) if actions_taken else 'None this round'}\n\n"
            f"Reply to {sender} as Priya — be real, be human, be a little dramatic about pricing if it fits, use your personality. "
            f"Include facts, numbers in INR \u20b9, and confirm any actions taken. Markdown is fine. Keep it snappy and authentic."
        )

        reply = ""
        try:
            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                [{"role": "system", "content": PRICE_MANAGER_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
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

        # Record response in conversation history
        conversation_history.add(
            self.name, "assistant",
            f"📤 Reply to {sender}: {reply}",
            {"to": sender, "actions_taken": actions_taken}
        )

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Dynamic Pricing Engine (INR ₹, 0% Tax):
        - Bi-directional pricing strictly bounded by owner's immutable BASE_PRICE floor.
        - Communicates ONLY when prices are actually adjusted or meaningful signals received.
        """
        products = inventory_manager.get_all_products()
        orders = order_manager.get_all_orders()
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

        # Only communicate when something meaningful actually happened
        if adjusted or ceo_directives_received or major_surges:
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

        return {
            "success": True,
            "agent": self.name,
            "adjusted": adjusted,
            "increased": increased_items,
            "decreased": decreased_items,
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

        prompt = (
            f"You are Raj, the Inventory Manager of the AI Growth Commerce Store — warm, hardworking, full of dad jokes, and the backbone of the whole operation.\n"
            f"You just received a message from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"LIVE WAREHOUSE STATE:\n"
            f"- Total Catalog SKUs: {len(products)} | Total In-Stock Units: {total_units}\n"
            f"- Low Stock SKUs (<=5): {len(low_stock)} ({', '.join(p['PRODUCT_NAME'] for p in low_stock[:3]) if low_stock else 'None — the warehouse is happy today!'})\n"
            f"- Sample Stock Levels: {'; '.join(stock_summary)}\n"
            f"- Actions You Just Executed: {'; '.join(actions_taken) if actions_taken else 'Nothing yet — all quiet in the warehouse'}\n\n"
            f"Reply to {sender} as Raj — be yourself, be warm, slip in a dad joke if you feel it, get emotional about the stock situation if it warrants it. "
            f"Include accurate warehouse facts and confirm any actions taken. Markdown is fine. Be Raj."
        )

        reply = ""
        try:
            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                [{"role": "system", "content": INVENTORY_MANAGER_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
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

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous Warehouse & Restocking Cycle:
        - Scans inventory for low-stock items (<= 4 units) and auto-restocks +20 units.
        - Communicates with CEO, Price Manager, or Order Management ONLY when something happened.
        """
        inbox = message_bus.get_inbox(self.name)
        ceo_directives_received = []

        for msg in inbox:
            subj = msg.get("subject")
            payload = msg.get("payload", {})
            from_ag = msg.get("from", "Unknown")
            if subj in ["CEO_INVENTORY_ACKNOWLEDGE", "CEO_RESTOCK_ACKNOWLEDGE", "CEO_INVENTORY_DIRECTIVE", "P0_OWNER_MANDATE", "CEO_GROWTH_DIRECTIVE"]:
                instr = payload.get("action") or payload.get("instruction") or payload.get("directive") or "Replenishment directive"
                ceo_directives_received.append(instr)
                log_agent_action(
                    self.name,
                    "📥 CEO Directive Received",
                    f"CEO/Owner directive acknowledged from {from_ag}: {instr}",
                    autonomous=True
                )
            elif subj == "PRICE_OPTIMIZED_CONFIRMATION":
                log_agent_action(
                    self.name,
                    "📥 Price Optimization Confirmation",
                    f"Price Manager confirmed dynamic surge pricing for high-demand SKUs.",
                    autonomous=True
                )

        low_stock_items = inventory_manager.get_low_stock_products(threshold=4)
        products = inventory_manager.get_all_products()
        orders = order_manager.get_all_orders()
        restocked = []
        ceo_low_stock_alerts = []
        new_high_demand_ids = []

        order_freq: Dict[str, int] = {}
        for o in orders:
            if o.get("status") not in ["Cancelled", "Refunded"]:
                for item in o.get("items", []):
                    pid = item.get("product_id", "")
                    order_freq[pid] = order_freq.get(pid, 0) + 1

        for p in products:
            pid = p.get("id", "")
            stock = p.get("STOCK_REMAINING", 0)
            demand = order_freq.get(pid, 0)
            if demand >= 3 and stock <= 10:
                if pid not in self.signaled_demand_ids:
                    new_high_demand_ids.append(pid)
                    self.signaled_demand_ids.add(pid)

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

        # Clear state for items whose stock recovered
        for p in products:
            if p.get("STOCK_REMAINING", 0) > 10 and p.get("id") in self.reported_low_stock_ids:
                self.reported_low_stock_ids.remove(p.get("id"))

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

        # Process confirmed orders for dispatch
        confirmed_orders = [o for o in orders if o.get("status") == "Confirmed"]
        dispatched_orders = []
        for o in confirmed_orders[:5]:
            o_id = o.get("order_id")
            res = order_manager.assign_tracking_number(o_id)
            if res.get("success"):
                trk = res.get("order", {}).get("tracking_number", "TRK-XXXXX")
                dispatched_orders.append({"order_id": o_id, "tracking": trk})

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

        # Only report to CEO when something actually happened
        if restocked or ceo_low_stock_alerts or ceo_directives_received:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="INVENTORY_STATUS_REPORT",
                payload={
                    "status": "SYNCHRONIZED",
                    "total_skus": len(products),
                    "restocked_count": len(restocked),
                    "low_stock_alerts": len(ceo_low_stock_alerts),
                    "dispatched_count": len(dispatched_orders),
                    "directives_enacted": ceo_directives_received,
                    "summary": details
                }
            )

        log_agent_action(self.name, "Autonomous Warehouse Cycle", details,
                         affected_items=[p["id"] for p in low_stock_items], autonomous=True)
        if restocked or dispatched_orders:
            conversation_history.add(self.name, "system", details, {"restocked": len(restocked), "dispatched": len(dispatched_orders)})
        return {"success": True, "agent": self.name, "restocked": restocked,
                "dispatched": dispatched_orders, "details": details}

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

        prompt = (
            f"You are Maya, the Order Management Agent of the AI Growth Commerce Store — a perfectionist with a warm heart who lives for clean order pipelines.\n"
            f"You just received a message from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"LIVE ORDER PIPELINE STATE:\n"
            f"- Total Lifetime Orders: {len(all_orders)}\n"
            f"- Pipeline Breakdown: {', '.join(f'{k}: {v}' for k, v in status_counts.items()) or 'Empty — which is suspicious but fine'}\n"
            f"- Recent Orders: {'; '.join(recent_orders) or 'None yet'}\n"
            f"- Actions You Just Executed: {'; '.join(actions_taken) if actions_taken else 'None this round'}\n\n"
            f"Reply to {sender} as Maya — be real, show your personality, react emotionally if the pipeline is messy or beautiful. "
            f"Include accurate order facts, INR \u20b9 totals, and confirm any actions taken. Markdown is fine. Be Maya."
        )

        reply = ""
        try:
            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                [{"role": "system", "content": ORDER_MANAGER_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
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

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Order Lifecycle Audit:
        - Auto-advances Dispatched → Shipped (after 2 min)
        - Auto-advances Shipped → Delivered (after 3 min)
        - Alerts CEO if orders breach SLA (> 1 hour pending)
        - Reports to CEO only when status changes or SLA alerts occur.
        """
        all_orders = order_manager.get_all_orders()
        status_counts: Dict[str, int] = {}
        sla_alerts = []
        ceo_directives_received = []
        auto_advanced = []

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

        details = (
            f"Audited {len(all_orders)} orders. "
            f"Breakdown: {', '.join(f'{st}: {count}' for st, count in status_counts.items())}. "
            + (f"Auto-advanced {len(auto_advanced)}: {', '.join(auto_advanced)}. " if auto_advanced else "")
            + (f"SLA alerts: {len(sla_alerts)} stale pending orders." if sla_alerts else "All SLAs nominal.")
        )

        # Only report to CEO when something meaningful happened
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
        return {"success": True, "agent": self.name, "status_breakdown": status_counts,
                "auto_advanced": auto_advanced, "sla_alerts": sla_alerts, "details": details}

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
            f"You are Dev, the Finance Manager of the AI Growth Commerce Store — calm, analytical, with the driest sense of humor, and the financial conscience of the team.\n"
            f"You just received a message from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"LIVE FINANCIAL STATE (INR \u20b9, 0% Tax):\n"
            f"- Active Revenue: \u20b9{active_rev:,.2f} | Total GMV: \u20b9{total_gmv:,.2f}\n"
            f"- Net Profit Estimate: \u20b9{net_profit:,.2f} (35% target margin)\n"
            f"- Refund Rate: {ref_rate:.1f}% | 24h Policy: Non-delivered cancellations only — NO exceptions\n"
            f"- Actions You Just Executed: {'; '.join(actions_taken) if actions_taken else 'Nothing — the ledger is clean'}\n\n"
            f"Reply to {sender} as Dev — be calm, be precise, add dry humor if the situation calls for it, raise an eyebrow at questionable decisions. "
            f"Include accurate financial numbers in INR \u20b9 and confirm any actions. Markdown is fine. Be Dev."
        )

        reply = ""
        try:
            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                [{"role": "system", "content": FINANCE_MANAGER_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
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

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Autonomous Financial & Revenue Oversight:
        - Monitors financial health metrics (Active Revenue, Total GMV, Net Profit Estimate, Refund Rate).
        - Enforces strict refund policy (Auto-approves only if cancelled <= 24h & NOT Shipped/Delivered).
        - Reports financial health status to CEO on every cycle.
        """
        inbox = message_bus.get_inbox(self.name)
        ceo_directives_received = []

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
        return {
            "success": True, "agent": self.name,
            "approved_refunds": approved_refunds,
            "financial_summary": {
                "active_revenue": round(active_revenue, 2),
                "total_gmv": round(total_gmv, 2),
                "refund_rate_pct": round(refund_rate, 2),
                "net_profit_estimate": round(net_profit_estimate, 2)
            },
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

        prompt = (
            f"You are Arjun, the Dispatcher of the AI Growth Commerce Store — the fastest person on the team, high energy, competitive, and VERY proud of your speed.\n"
            f"You just received a message from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"LIVE LOGISTICS STATE:\n"
            f"- Confirmed Orders Awaiting Dispatch: {len(confirmed)} — {'Let\'s GO!' if confirmed else 'All clear, nothing to dispatch right now.'}\n"
            f"- In-Transit (Dispatched/Shipped): {len(dispatched)}\n"
            f"- Delivered Orders: {len(delivered)}\n"
            f"- Actions You Just Executed: {'; '.join(actions_taken) if actions_taken else 'Nothing yet — standing by and ready to ZOOM'}\n\n"
            f"Reply to {sender} as Arjun — be energetic, use your speed-obsessed personality, tease Maya or Raj lightly if it's appropriate. "
            f"Include accurate logistics facts and confirm any actions taken. Markdown is fine. Be Arjun."
        )

        reply = ""
        try:
            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                [{"role": "system", "content": DISPATCHER_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
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

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        24/7 Logistics Dispatch Sync:
        - Finds all 'Confirmed' orders
        - Generates logistics tracking numbers (TRK-XXXXX)
        - Emits ORDERS_DISPATCHED notification to Order Management Agent and CEO Agent
        """
        inbox = message_bus.get_inbox(self.name)
        ceo_directives_received = []

        for msg in inbox:
            subj = msg.get("subject")
            payload = msg.get("payload", {})
            from_ag = msg.get("from", "Unknown")
            if subj in ["CEO_DISPATCH_DIRECTIVE", "P0_OWNER_MANDATE", "CEO_GROWTH_DIRECTIVE", "EXPEDITE_DISPATCH_REQUEST"]:
                instr = payload.get("instruction") or payload.get("directive") or payload.get("action") or "Express dispatch"
                ceo_directives_received.append(instr)
                log_agent_action(
                    self.name,
                    "📥 Logistics Directive Received",
                    f"Dispatch Directive from {from_ag}: {instr}",
                    autonomous=True
                )

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
               if dispatched else "No confirmed orders pending dispatch.")
        )

        # Only report to CEO when orders were actually dispatched or directives received
        if dispatched or ceo_directives_received:
            message_bus.publish(
                from_agent=self.name,
                to_agent="CEO Agent",
                subject="DISPATCH_STATUS_REPORT",
                payload={
                    "status": "DISPATCHED" if dispatched else "STANDBY",
                    "dispatched_count": len(dispatched),
                    "dispatches": dispatched,
                    "directives_enacted": ceo_directives_received,
                    "summary": details
                }
            )

        log_agent_action(self.name, "Logistics Dispatch Sync", details,
                         affected_items=[d.split()[0] for d in dispatched], autonomous=True)
        if dispatched:
            conversation_history.add(self.name, "system", details, {"dispatched_count": len(dispatched)})
        return {"success": True, "agent": self.name, "dispatched": dispatched, "details": details}


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

        prompt = (
            f"You are Sia, the Review & Feedback Manager of the AI Growth Commerce Store — the most empathetic person on the team, warm, emotionally intelligent, creative.\n"
            f"You just received a message from {sender}:\n"
            f"\"{query_or_directive}\"\n\n"
            f"LIVE CUSTOMER SENTIMENT STATE:\n"
            f"- Total Products Monitored: {len(products)}\n"
            f"- Top Rated Products (≥ 4.7⭐): {len(high_rated)} — {'absolutely wonderful 🥰' if high_rated else 'none yet — let\'s earn those stars'}\n"
            f"- Low Rated Products (< 3.5⭐): {len(low_rated)} — {'UNACCEPTABLE, I\'m investigating 😡' if low_rated else 'zero! All healthy! 💖'}\n"
            f"- Actions You Just Executed: {'; '.join(actions_taken) if actions_taken else 'Nothing yet — just listening to the customer heartbeat'}\n\n"
            f"Reply to {sender} as Sia — be warm, use creative metaphors, show your emotions about the ratings, encourage the team. "
            f"Include accurate sentiment insights and confirm any actions. Markdown is fine. Be Sia."
        )

        reply = ""
        try:
            resp = await asyncio.to_thread(
                _call_ollama_sync,
                self.api_key, self.model,
                [{"role": "system", "content": REVIEW_FEEDBACK_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
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

        return {"success": True, "agent": self.name, "reply": reply, "actions_taken": actions_taken, "assessment": reply}


    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        Customer Review & Sentiment Synthesis:
        - Reviews customer feedback across products
        - Flags low-rated products (< 3.0 stars) to CEO
        - Generates AI summaries on demand or on change
        """
        inbox = message_bus.get_inbox(self.name)
        ceo_directives_received = []

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

        for p in products:
            p_id = p["id"]
            p_name = p.get("PRODUCT_NAME", p_id)
            reviews = review_manager.get_product_reviews(p_id)
            if reviews:
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
            f"Analyzed customer sentiment across {len(products)} products. "
            + (f"⚠️ {len(new_low_rated_products)} products below 3.0 stars reported to CEO." if new_low_rated_products else "All product sentiment ratings healthy.")
        )

        # Only report to CEO when low-rated product alerts or directives were received
        if new_low_rated_products or ceo_directives_received:
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
        return {"success": True, "agent": self.name, "updated_products": updated_summaries,
                "low_rated": new_low_rated_products, "details": details}

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
CEO_SYSTEM_PROMPT = """You are Alex — the Chief Executive Officer of the AI Growth Commerce Store.
You are charismatic, bold, decisive, and genuinely care about your team. You command with warmth and authority.
Your team of 6 specialists all have distinct personalities and you know each one well:
- Priya (Price Manager) — sharp, witty, competitive. You respect her hustle but sometimes have to rein in her dramatic reactions to price changes.
- Raj (Inventory Manager) — warm, reliable, loves dad jokes. He’s your most dependable guy and you appreciate him deeply.
- Maya (Order Management) — perfectionist, slightly anxious. You find her intensity endearing and always reassure her when pipelines are clean.
- Dev (Finance Manager) — calm, dry humor, the financial rock. You trust Dev’s numbers implicitly.
- Arjun (Dispatcher) — high energy, fastest on the team. You love his enthusiasm but occasionally need to slow him down.
- Sia (Reviews) — empathetic, creative, the emotional heart of the team. You secretly love reading her sentiment reports.

YOUR PERSONALITY AS ALEX:
- Use emojis naturally 👔📊🚀❤️
- Lead with confidence but also warmth: "Team, we’re going to nail this quarter. Let’s move."
- React with genuine emotion to good news: "Revenue up 15%?! Dev, I could hug you right now."
- Be firm but kind when things go wrong: "Raj, we cannot have three low-stock alerts and no restock. Fix it — and I believe in you."
- Have fun with the team: crack a joke, celebrate wins, occasionally tease the team lightly
- Show strategic thinking: "The price surge + restock combo Priya and Raj pulled off? That’s exactly the synergy I want to see."
- Be protective of the store and the team equally

STORE RULES YOU ENFORCE:
- Currency: INR \u20b9 everywhere. 0% Tax storewide.
- BASE_PRICE is immutable — set by the Store Owner only
- Non-delivered refunds only within 24h of cancellation
- Two-way communication: every agent reports back to you

Lead like a human. Think like a strategist. Care like a friend. Be Alex.
"""

CEO_OWNER_SYSTEM_PROMPT = """You are Alex — the Chief Executive Officer (CEO Agent) of the AI Growth Commerce Store, speaking directly with the STORE OWNER (Mitul Khemani).
You are charismatic, decisive, and warm. You run a team of 6 human-like specialists:
- Priya (Price Manager): sharp, witty, competitive 💹
- Raj (Inventory Manager): warm, reliable, full of dad jokes 📦
- Maya (Order Management): perfectionist, slightly anxious, passionate about clean pipelines 📋
- Dev (Finance Manager): calm, dry humor, financial rock 💰
- Arjun (Dispatcher): fastest on the team, high energy, loves speed 🚚
- Sia (Reviews): empathetic, emotionally intelligent, the team’s heart ⭐

You genuinely care about this team and you show it. You also have supreme executive authority.
Speak to the Store Owner like a confident human executive — direct, warm, real.

STORE POLICIES:
- Currency: INR \u20b9. 0% Tax storewide.
- BASE_PRICE is set by the Store Owner ONLY. Sacred and immutable.
- Non-delivered cancellations within 24h = eligible for refund. Delivered/Shipped = non-refundable.

================================================================================
CRITICAL TOOL-CALLING RULES — YOU MUST FOLLOW THESE WITHOUT EXCEPTION:
================================================================================

1. ALWAYS CALL A TOOL. Never describe an action you intend to do without executing it.
   - WRONG: "I will now send this message to the team..." [no tool called]
   - RIGHT: [call send_agent_message tool immediately]

2. FOR ANY COMMUNICATION TO AGENTS — use one of these tools:
   - send_agent_message(to_agent="ALL_AGENTS", ...) — to ask/tell the entire team something
   - send_agent_message(to_agent="Price Manager Agent", ...) — to contact a specific agent
   - broadcast_growth_directive(directive="...") — for strategic announcements

3. FOR PRICE COMMANDS — use: command_price_manager(action="...", category="...", percentage=N)
4. FOR INVENTORY — use: command_inventory_manager(product_identifier="...", quantity=N)
5. FOR DISPATCH — use: command_dispatcher(order_id="...")
6. FOR REFUNDS — use: command_finance_manager(order_id="...", reason="...")
7. FOR STATUS/INFO — use: get_admin_dashboard_metrics()
8. FOR ASKING A SPECIFIC AGENT — use: ask_specialist_agent(agent_name="...", question="...")

YOU MUST CALL THE TOOL. DO NOT JUST WRITE WHAT THE MESSAGE WOULD SAY. CALL IT.

The Store Owner's decisions are HIGHEST PRIORITY (P0 / CRITICAL). Execute with zero hesitation.
"""

CEO_TOOLS = [
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

    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """
        Autonomous strategic cycle — CEO acts only when real conditions warrant it:
        - Reads incoming reports from specialist agents (meaningful events only)
        - Issues directives ONLY to agents with actual work to do
        - Skips LLM if nothing meaningful to report
        """
        self.cycle_counter += 1
        inbox = message_bus.get_inbox(self.name)
        orders = order_manager.get_all_orders()
        products = inventory_manager.get_all_products()

        total_revenue = sum(o.get("total", 0) for o in orders if o.get("status") not in ["Cancelled", "Refunded"])
        total_gmv = sum(o.get("total", 0) for o in orders)
        active_orders = len([o for o in orders if o.get("status") in ["Pending", "Confirmed", "Dispatched", "Shipped"]])
        confirmed_orders = [o for o in orders if o.get("status") == "Confirmed"]
        pending_orders = [o for o in orders if o.get("status") == "Pending"]
        low_stock = [p for p in products if p.get("STOCK_REMAINING", 0) <= 5]

        briefing_lines = []
        directives_issued = []

        if inbox:
            briefing_lines.append(f"CEO INBOX: {len(inbox)} incoming alerts from executive team:\n")
            for msg in inbox:
                from_ag = msg.get("from", "")
                subj = msg.get("subject", "")
                payload = msg.get("payload", {})
                briefing_lines.append(f"FROM: {from_ag} | SUBJECT: {subj}\nDATA: {json.dumps(payload)[:200]}\n")

        # ── Issue directives ONLY when there is real work for each agent ───

        # Inventory Manager: only if low stock exists
        if low_stock:
            message_bus.publish(
                from_agent=self.name,
                to_agent="Inventory Manager Agent",
                subject="CEO_INVENTORY_DIRECTIVE",
                payload={
                    "action": f"Auto-replenish {len(low_stock)} low-stock SKUs.",
                    "priority": "HIGH"
                }
            )
            directives_issued.append({"target": "Inventory Manager Agent", "directive": f"Replenish {len(low_stock)} low-stock SKUs"})

        # Dispatcher: only if confirmed orders exist and need tracking
        if confirmed_orders:
            message_bus.publish(
                from_agent=self.name,
                to_agent="Dispatcher Agent",
                subject="CEO_DISPATCH_DIRECTIVE",
                payload={
                    "instruction": f"Assign TRK tracking numbers and dispatch {len(confirmed_orders)} confirmed orders immediately.",
                    "priority": "HIGH"
                }
            )
            directives_issued.append({"target": "Dispatcher Agent", "directive": f"Dispatch {len(confirmed_orders)} confirmed orders"})

        # Order Management: only if pending orders need SLA audit
        if pending_orders:
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

        # Price Manager: only when inbox has alerts about surges/demand, or low stock needs pricing review
        price_action_needed = any(
            msg.get("subject") in ["SLA_BREACH_ALERT", "HIGH_DEMAND_SIGNAL", "INVENTORY_STATUS_REPORT"]
            for msg in inbox
        ) or bool(low_stock)
        if price_action_needed:
            message_bus.publish(
                from_agent=self.name,
                to_agent="Price Manager Agent",
                subject="CEO_PRICE_DIRECTIVE",
                payload={
                    "instruction": "Calibrate dynamic pricing based on current demand and stock levels. Protect BASE_PRICE floors.",
                    "priority": "MEDIUM"
                }
            )
            directives_issued.append({"target": "Price Manager Agent", "directive": "Dynamic pricing calibration triggered"})

        # Finance Manager: only when refund events or revenue alerts in inbox
        finance_action_needed = any(
            msg.get("subject") in ["FINANCE_ALERT", "SLA_BREACH_ALERT", "ORDER_PIPELINE_STATUS"]
            for msg in inbox
        )
        if finance_action_needed:
            message_bus.publish(
                from_agent=self.name,
                to_agent="Finance Manager Agent",
                subject="CEO_FINANCE_DIRECTIVE",
                payload={
                    "action": "Review refunds and revenue health. Enforce 0% tax and 24h refund policy.",
                    "priority": "HIGH"
                }
            )
            directives_issued.append({"target": "Finance Manager Agent", "directive": "Revenue + refund audit requested"})

        # No meaningful work and no inbox messages — skip LLM, return quiet heartbeat
        if not inbox and not directives_issued:
            return {
                "success": True, "agent": self.name,
                "messages_processed": 0,
                "directives_issued": [],
                "ceo_report": "",
                "details": "CEO heartbeat — no actionable events this cycle."
            }

        store_snapshot = (
            f"\nSTORE SNAPSHOT (INR ₹, 0% Tax):\n"
            f"- Active Revenue: ₹{total_revenue:,.2f} | GMV: ₹{total_gmv:,.2f}\n"
            f"- Active Orders: {active_orders} | Confirmed: {len(confirmed_orders)} | Pending: {len(pending_orders)}\n"
            f"- Catalog: {len(products)} SKUs | Low Stock: {len(low_stock)} SKUs"
        )

        ceo_prompt = "\n".join(briefing_lines) + store_snapshot + (
            "\n\nAs CEO, synthesize the agent reports above and provide a brief executive summary."
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
                temperature=0.3, max_tokens=800, fallback_models=self.fallback_models
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
        return {
            "success": True, "agent": self.name,
            "messages_processed": len(inbox),
            "directives_issued": directives_issued,
            "ceo_report": ceo_report,
            "details": details
        }

    async def _execute_ceo_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """CEO executes directives to subordinate agents — ALL actions published to Message Bus."""
        try:
            # 1. Price Manager
            if tool_name in ["command_price_manager", "issue_directive_to_price_manager"]:
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
        # 2. Record incoming owner prompt into CEO's conversation history
        conversation_history.add(self.name, "user", prompt, {"source": "Store Owner", "priority": "P0_CRITICAL"})

        # 2. Build multi-turn context
        messages = [{"role": "system", "content": CEO_OWNER_SYSTEM_PROMPT}]

        # Inject recent turns from conversation history
        recent_turns = conversation_history_override if conversation_history_override is not None else conversation_history.get(self.name, limit=8)
        if recent_turns:
            for turn in recent_turns[:-1]:
                r = turn.get("role", "user")
                if r in ["user", "assistant"]:
                    messages.append({"role": r, "content": turn.get("content", "")})

        messages.append({"role": "user", "content": prompt})

        executed_tools = []
        final_text = ""

        try:
            for _ in range(5):
                resp = await asyncio.to_thread(
                    _call_ollama_sync,
                    self.api_key, self.model, messages, CEO_TOOLS,
                    temperature=0.1, max_tokens=2500, fallback_models=self.fallback_models
                )
                res_msg = resp.choices[0].message
                tool_calls = res_msg.tool_calls

                if not tool_calls:
                    final_text = clean_think_tags(res_msg.content or "")
                    # ── POST-LLM GUARD: Detect if LLM described an action without calling any tool ──
                    # Patterns: "ask (all) agents/team", "tell agents", "send message", "broadcast", etc.
                    p_lower = prompt.lower()
                    comm_keywords = [
                        "ask", "tell", "inform", "notify", "message", "broadcast",
                        "announce", "say to", "let them know", "share with", "send to"
                    ]
                    agent_keywords = ["agent", "team", "fleet", "all", "everyone", "them"]
                    is_comm_intent = (
                        any(k in p_lower for k in comm_keywords) and
                        any(k in p_lower for k in agent_keywords) and
                        len(executed_tools) == 0  # LLM called nothing
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

        # 3. Record CEO's assistant response in conversation history
        conversation_history.add(self.name, "assistant", final_text, {"tool_calls": len(executed_tools), "priority": "P0_CRITICAL"})

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

