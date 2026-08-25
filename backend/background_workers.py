import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.admin_agents import (
    price_manager_agent,
    inventory_manager_agent,
    order_manager_agent,
    refund_manager_agent,
    dispatcher_agent,
    review_feedback_agent
)

def format_interval_human(seconds: int) -> str:
    """Helper to format seconds into clean human-readable intervals (e.g. 2m, 5m, 2h)."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins} min" if mins == 1 else f"{mins} mins"
    else:
        hrs = seconds / 3600
        return f"{int(hrs)} hr" if hrs == 1 else f"{hrs:.1f}".rstrip('0').rstrip('.') + " hours"


class BackgroundAgentWorker:
    def __init__(self):
        self._running = False
        self._task = None
        self.tick_sleep_seconds = 5  # Internal scheduler evaluation loop tick

        # Per-agent independent schedule configurations (Loaded from .env with sensible defaults)
        self.agent_states: Dict[str, Dict[str, Any]] = {
            "dispatcher": {
                "name": "Dispatcher Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("DISPATCHER_INTERVAL_SECONDS", "120")),  # 2 min
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "truck",
                "description": "Packages confirmed orders, assigns tracking numbers (TRK-XXXXX), and dispatches logistics."
            },
            "inventory_manager": {
                "name": "Inventory Manager Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("INVENTORY_AGENT_INTERVAL_SECONDS", "300")),  # 5 min
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "package",
                "description": "Audits warehouse stock and autonomously restocks SKUs falling below threshold."
            },
            "refund_manager": {
                "name": "Refund Manager Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("REFUND_AGENT_INTERVAL_SECONDS", "3600")),  # 1 hour
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "rotate-ccw",
                "description": "Enforces 24h & non-shipped refund policy; autonomously processes Razorpay refunds & restocks."
            },
            "price_manager": {
                "name": "Price Manager Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("PRICE_AGENT_INTERVAL_SECONDS", "120")),  # 2 min
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "tag",
                "description": "Autonomously optimizes item prices based on demand and warehouse stock ratios."
            },
            "order_manager": {
                "name": "Order Manager Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("ORDER_AGENT_INTERVAL_SECONDS", "1800")),  # 30 min
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "clipboard-list",
                "description": "Monitors SLA adherence and audits lifetime order lifecycle states (Pending -> Delivered)."
            },
            "review_manager": {
                "name": "Review & Feedback Manager",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("REVIEW_AGENT_INTERVAL_SECONDS", "7200")),  # 2 hours
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "star",
                "description": "Analyzes customer sentiment via Groq LLM; auto-updates product listings with review summaries."
            }
        }

    def start(self):
        """Starts the 24/7 background worker async task."""
        if self._running:
            return
        self._running = True
        try:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(self._run_loop())
        except RuntimeError:
            pass
        print("[24/7 Background Workers] Autonomous AI Agent Fleet successfully started with independent intervals!")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _run_loop(self):
        # Initial warm-up delay
        await asyncio.sleep(3)
        while self._running:
            try:
                await self.check_and_run_due_agents()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[24/7 Background Worker Loop Error]: {e}", flush=True)
            await asyncio.sleep(self.tick_sleep_seconds)

    async def check_and_run_due_agents(self) -> Dict[str, Any]:
        """
        Periodically checks each agent's individual schedule (2min, 5min, 2h, etc.)
        and triggers execution only when its configured interval has elapsed.
        """
        now_ts = time.time()
        results = {}
        agents_map = {
            "dispatcher": dispatcher_agent,
            "inventory_manager": inventory_manager_agent,
            "refund_manager": refund_manager_agent,
            "price_manager": price_manager_agent,
            "order_manager": order_manager_agent,
            "review_manager": review_feedback_agent
        }

        for key, agent_instance in agents_map.items():
            state = self.agent_states.get(key, {})
            if not state.get("enabled", True):
                continue

            interval = state.get("interval_seconds", 300)
            last_ts = state.get("last_run_ts", 0.0)

            # Check if interval has elapsed
            if (now_ts - last_ts) >= interval:
                try:
                    state["status"] = "EXECUTING"
                    res = await agent_instance.run_autonomous_cycle()
                    state["last_run"] = datetime.now(timezone.utc).isoformat()
                    state["last_run_ts"] = time.time()
                    state["actions_count"] += 1
                    state["status"] = "RUNNING 24/7"
                    results[key] = res
                except Exception as e:
                    state["status"] = "ERROR"
                    print(f"Error running autonomous agent {key}: {e}", flush=True)
                    results[key] = {"error": str(e)}

        return results

    async def trigger_agent(self, agent_key: str) -> Dict[str, Any]:
        """Manually triggers an instant autonomous execution for a specific agent."""
        agents_map = {
            "dispatcher": dispatcher_agent,
            "inventory_manager": inventory_manager_agent,
            "refund_manager": refund_manager_agent,
            "price_manager": price_manager_agent,
            "order_manager": order_manager_agent,
            "review_manager": review_feedback_agent
        }
        if agent_key not in agents_map:
            return {"success": False, "error": f"Unknown agent '{agent_key}'"}

        agent = agents_map[agent_key]
        state = self.agent_states.get(agent_key, {})
        state["status"] = "EXECUTING"
        try:
            res = await agent.run_autonomous_cycle()
            state["last_run"] = datetime.now(timezone.utc).isoformat()
            state["last_run_ts"] = time.time()
            state["actions_count"] += 1
            state["status"] = "RUNNING 24/7"
            return {"success": True, "agent": agent_key, "result": res}
        except Exception as e:
            state["status"] = "ERROR"
            return {"success": False, "error": str(e)}

    def update_agent_interval(self, agent_key: str, interval_seconds: int) -> Dict[str, Any]:
        """Dynamically update an agent's execution interval (e.g. 120 for 2m, 300 for 5m, 7200 for 2h)."""
        if agent_key not in self.agent_states:
            return {"success": False, "error": f"Unknown agent '{agent_key}'"}
        
        interval_seconds = max(10, int(interval_seconds))
        self.agent_states[agent_key]["interval_seconds"] = interval_seconds
        human_str = format_interval_human(interval_seconds)
        return {
            "success": True,
            "agent": agent_key,
            "interval_seconds": interval_seconds,
            "human_interval": human_str,
            "message": f"Updated {self.agent_states[agent_key]['name']} interval to {human_str}."
        }

    def get_status(self) -> Dict[str, Any]:
        """Returns live statuses, individual schedule intervals, and telemetry for all 6 agents."""
        enriched_agents = {}
        now_ts = time.time()
        for k, v in self.agent_states.items():
            enriched = dict(v)
            interval = v.get("interval_seconds", 300)
            last_ts = v.get("last_run_ts", 0.0)
            elapsed = int(now_ts - last_ts) if last_ts > 0 else None
            next_due_in = max(0, interval - elapsed) if elapsed is not None else 0
            enriched["human_interval"] = format_interval_human(interval)
            enriched["next_due_in_seconds"] = next_due_in
            enriched_agents[k] = enriched

        return {
            "is_running_24_7": self._running,
            "agents": enriched_agents
        }

# Global singleton
background_worker = BackgroundAgentWorker()
