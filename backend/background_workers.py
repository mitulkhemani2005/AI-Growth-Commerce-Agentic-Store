import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.admin_agents import (
    price_manager_agent,
    inventory_manager_agent,
    order_management_agent,
    finance_manager_agent,
    dispatcher_agent,
    review_feedback_agent,
    ceo_agent,
    message_bus
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
        self.tick_sleep_seconds = 2  # Evaluation loop tick every 2 seconds

        # Per-agent independent schedule configurations (Sensible collaborative intervals)
        self.agent_states: Dict[str, Dict[str, Any]] = {
            "dispatcher": {
                "name": "Dispatcher Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("DISPATCHER_INTERVAL_SECONDS", "15")),
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "truck",
                "description": "Packages confirmed orders, assigns tracking numbers (TRK-XXXXX), and dispatches logistics in real time."
            },
            "inventory_manager": {
                "name": "Inventory Manager Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("INVENTORY_AGENT_INTERVAL_SECONDS", "20")),
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "package",
                "description": "Audits warehouse stock, restocks SKUs below threshold, signals high-demand to Price Manager, reports low-stock to CEO."
            },
            "finance_manager": {
                "name": "Finance Manager Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("FINANCE_AGENT_INTERVAL_SECONDS", "30")),
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "dollar-sign",
                "description": "Monitors financial health (revenue, GMV, refund rate). Auto-approves refunds ≤24h & not Shipped/Delivered. Reports P&L to CEO."
            },
            "price_manager": {
                "name": "Price Manager Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("PRICE_AGENT_INTERVAL_SECONDS", "25")),
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "tag",
                "description": "Autonomously optimizes selling prices based on demand signals, inventory levels, and strict owner BASE_PRICE floors."
            },
            "order_manager": {
                "name": "Order Management Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("ORDER_AGENT_INTERVAL_SECONDS", "20")),
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "clipboard-list",
                "description": "Monitors SLA adherence, audits order lifecycle states (Pending→Delivered), receives dispatch reports from Inventory Manager."
            },
            "review_manager": {
                "name": "Review & Feedback Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("REVIEW_AGENT_INTERVAL_SECONDS", "45")),
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "star",
                "description": "Analyzes customer sentiment via Groq LLM; auto-updates product listings with AI review summaries; alerts CEO on low-rated products."
            },
            "ceo": {
                "name": "CEO Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("CEO_AGENT_INTERVAL_SECONDS", "30")),
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "briefcase",
                "description": "Head of all agents. Continuously processes inter-agent messages, makes strategic decisions, issues directives, and reports to Owner."
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
        print("[24/7 Background Workers] Autonomous AI Agent Fleet (7 agents with per-agent API keys) started!", flush=True)

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
        Periodically checks each agent's individual schedule and triggers execution
        only when its configured interval has elapsed.
        Order matters: run specialized agents before CEO so CEO has fresh messages to process.
        """
        now_ts = time.time()
        results = {}
        agents_map = {
            "dispatcher": dispatcher_agent,
            "inventory_manager": inventory_manager_agent,
            "finance_manager": finance_manager_agent,
            "price_manager": price_manager_agent,
            "order_manager": order_management_agent,
            "review_manager": review_feedback_agent,
            "ceo": ceo_agent  # CEO runs last so it can process all fresh messages
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
                    print(f"Error running autonomous agent '{key}': {e}", flush=True)
                    results[key] = {"error": str(e)}

        return results

    async def trigger_agent(self, agent_key: str) -> Dict[str, Any]:
        """Manually triggers an instant autonomous execution for a specific agent."""
        agents_map = {
            "dispatcher": dispatcher_agent,
            "inventory_manager": inventory_manager_agent,
            "finance_manager": finance_manager_agent,
            "price_manager": price_manager_agent,
            "order_manager": order_management_agent,
            "review_manager": review_feedback_agent,
            "ceo": ceo_agent
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
        """Dynamically update an agent's execution interval."""
        if agent_key not in self.agent_states:
            return {"success": False, "error": f"Unknown agent '{agent_key}'"}

        interval_seconds = max(1, int(interval_seconds))
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
        """Returns live statuses, individual schedule intervals, and telemetry for all 7 agents."""
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
            "agents": enriched_agents,
            "message_bus_snapshot": message_bus.get_inbox_snapshot()
        }


# Global singleton
background_worker = BackgroundAgentWorker()
