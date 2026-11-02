import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Dict, Any

from backend.admin_agents import (
    price_manager_agent,
    inventory_manager_agent,
    order_management_agent,
    finance_manager_agent,
    dispatcher_agent,
    review_feedback_agent,
    ceo_agent,
    message_bus,
    log_agent_action
)
from backend.agent_tasks import task_manager


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
        self._agent_locks: Dict[str, asyncio.Lock] = {}
        self.tick_sleep_seconds = 1  # Evaluation loop tick every 1 second

        # Per-agent independent schedule configurations (Event-driven autonomous cycles)
        self.agent_states: Dict[str, Dict[str, Any]] = {
            "dispatcher": {
                "name": "Dispatcher Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("DISPATCHER_INTERVAL_SECONDS", "15")),
                "effective_interval": int(os.environ.get("DISPATCHER_INTERVAL_SECONDS", "15")),
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
                "effective_interval": int(os.environ.get("INVENTORY_AGENT_INTERVAL_SECONDS", "20")),
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
                "effective_interval": int(os.environ.get("FINANCE_AGENT_INTERVAL_SECONDS", "30")),
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
                "interval_seconds": int(os.environ.get("PRICE_AGENT_INTERVAL_SECONDS", "20")),
                "effective_interval": int(os.environ.get("PRICE_AGENT_INTERVAL_SECONDS", "20")),
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
                "effective_interval": int(os.environ.get("ORDER_AGENT_INTERVAL_SECONDS", "20")),
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
                "interval_seconds": int(os.environ.get("REVIEW_AGENT_INTERVAL_SECONDS", "35")),
                "effective_interval": int(os.environ.get("REVIEW_AGENT_INTERVAL_SECONDS", "35")),
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "star",
                "description": "Analyzes customer sentiment via Ollama LLM; auto-updates product listings with AI review summaries; alerts CEO on low-rated products."
            },
            "ceo": {
                "name": "CEO Agent",
                "status": "RUNNING 24/7",
                "enabled": True,
                "interval_seconds": int(os.environ.get("CEO_AGENT_INTERVAL_SECONDS", "25")),
                "effective_interval": int(os.environ.get("CEO_AGENT_INTERVAL_SECONDS", "25")),
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "briefcase",
                "description": "Head of all agents. Oversees fleet discipline, processes inter-agent messages, makes strategic decisions, issues directives, and reports to Owner."
            },
            "buyer_agents": {
                "name": "5 AI Autonomous Shoppers Fleet",
                "status": "RUNNING 24/7",
                "enabled": str(os.environ.get("BUYER_SIMULATION_ENABLED", "true")).lower() == "true",
                "interval_seconds": 1,
                "effective_interval": 1,
                "last_run": None,
                "last_run_ts": 0.0,
                "actions_count": 0,
                "icon": "shopping-cart",
                "description": "5 AI shoppers (Alex, Sophia, David, Elena, Marcus) autonomously browse catalog, checkout via AP2, post verified reviews, and test return policies with staggered 5-minute random timing."
            }
        }

    def start(self):
        """Starts the 24/7 background worker async task."""
        if self._running:
            return
        self._running = True
        log_agent_action("Nova Runtime", "Fleet started", "Seven specialist agents and the configured buyer simulation are scheduled.")
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._run_loop())
        except RuntimeError:
            # The FastAPI lifespan always has a running loop.  Keeping this
            # explicit prevents a deceptive "RUNNING" UI state in scripts.
            self._running = False
            raise RuntimeError("BackgroundAgentWorker.start() requires a running asyncio loop")
        print("[24/7 Background Workers] Autonomous AI Agent Fleet & 5 AI Shoppers running 24/7!", flush=True)

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _run_loop(self):
        # Initial brief warm-up
        await asyncio.sleep(1)
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
        Periodically checks each agent's schedule and triggers execution
        with organic randomness and event-driven responsiveness.
        """
        import random
        from backend.buyer_agents import buyer_agents_fleet
        # Recover after a server/process interruption before dispatching fresh
        # work.  Without this, an interrupted task is invisible forever.
        stale_seconds = max(30, int(os.environ.get("AGENT_TASK_STALE_SECONDS", "300")))
        recovered_tasks = task_manager.recover_stale_claims(stale_seconds)
        now_ts = time.time()
        agents_map = {
            "dispatcher": dispatcher_agent,
            "inventory_manager": inventory_manager_agent,
            "finance_manager": finance_manager_agent,
            "price_manager": price_manager_agent,
            "order_manager": order_management_agent,
            "review_manager": review_feedback_agent,
            "ceo": ceo_agent
        }

        async def _run_agent(key: str, agent_instance: Any):
            # An HTTP manual trigger and the ticker used to invoke the same
            # agent concurrently.  JSON persistence then raced and tasks could
            # remain permanently 'running'.  One lock per specialist gives a
            # single, observable execution lane without serialising the fleet.
            lock = self._agent_locks.setdefault(key, asyncio.Lock())
            if lock.locked():
                return key, {"skipped": "already_executing"}
            async with lock:
                return await _run_agent_locked(key, agent_instance)

        async def _run_agent_locked(key: str, agent_instance: Any):
            state = self.agent_states.get(key, {})
            if not state.get("enabled", True):
                return key, None

            # Buyer fleet uses independent staggered 0-5m per-buyer scheduling
            if key == "buyer_agents":
                try:
                    due_results = await buyer_agents_fleet.check_due_buyers()
                    if due_results:
                        state["last_run"] = datetime.now(timezone.utc).isoformat()
                        state["last_run_ts"] = time.time()
                        state["actions_count"] += len(due_results)
                        return key, due_results
                except Exception as e:
                    print(f"Error checking due buyers: {e}", flush=True)
                return key, None

            base_interval = state.get("interval_seconds", 20)
            effective_interval = state.get("effective_interval", base_interval)
            last_ts = state.get("last_run_ts", 0.0)

            # Check if agent has pending messages on the bus (event-driven awaken)
            agent_inst_name = getattr(agent_instance, "name", "")
            has_pending_messages = False
            if agent_inst_name:
                pending_inbox = message_bus.peek_inbox(agent_inst_name)
                has_pending_messages = len(pending_inbox) > 0

            # Trigger if scheduled time arrived OR if unread messages arrived after minimum 4s cooldown
            time_due = (now_ts - last_ts) >= effective_interval
            event_due = has_pending_messages and (now_ts - last_ts) >= 4.0

            if time_due or event_due:
                try:
                    state["status"] = "EXECUTING"
                    state["started_at"] = datetime.now(timezone.utc).isoformat()
                    timeout_seconds = max(10, int(os.environ.get("AGENT_CYCLE_TIMEOUT_SECONDS", "90")))
                    res = await asyncio.wait_for(agent_instance.run_autonomous_cycle(), timeout=timeout_seconds)
                    state["last_run"] = datetime.now(timezone.utc).isoformat()
                    state["last_run_ts"] = time.time()
                    state["actions_count"] += 1
                    state["status"] = "RUNNING 24/7"
                    state["last_error"] = None
                    state["last_summary"] = str(res.get("details") or res.get("message") or "Cycle completed")[:600]
                    # Calculate new organic interval with +/- 25% random jitter
                    jitter_factor = random.uniform(0.75, 1.25)
                    state["effective_interval"] = max(5, int(base_interval * jitter_factor))
                    return key, res
                except Exception as e:
                    state["status"] = "ERROR"
                    state["last_error"] = str(e)
                    state["error_count"] = int(state.get("error_count", 0)) + 1
                    log_agent_action(state.get("name", key), "Cycle failed", str(e))
                    print(f"Error running autonomous agent '{key}': {e}", flush=True)
                    return key, {"error": str(e)}
            return key, None

        # Build list of run tasks including buyer agents fleet
        tasks = [_run_agent(k, inst) for k, inst in agents_map.items()]
        tasks.append(_run_agent("buyer_agents", buyer_agents_fleet))

        # Run all agents concurrently and asynchronously together
        results_list = await asyncio.gather(
            *tasks,
            return_exceptions=True
        )

        results = {}
        if recovered_tasks:
            results["recovered_tasks"] = recovered_tasks
        for item in results_list:
            if isinstance(item, tuple) and len(item) == 2:
                k, res = item
                if res is not None:
                    results[k] = res

        return results

    async def trigger_agent(self, agent_key: str) -> Dict[str, Any]:
        """Manually triggers an instant autonomous execution for a specific agent or buyer fleet."""
        from backend.buyer_agents import buyer_agents_fleet
        agents_map = {
            "dispatcher": dispatcher_agent,
            "inventory_manager": inventory_manager_agent,
            "finance_manager": finance_manager_agent,
            "price_manager": price_manager_agent,
            "order_manager": order_management_agent,
            "review_manager": review_feedback_agent,
            "ceo": ceo_agent
        }

        if agent_key in ["buyer_agents", "buyers", "all_buyers"]:
            state = self.agent_states.get("buyer_agents", {})
            lock = self._agent_locks.setdefault("buyer_agents", asyncio.Lock())
            if lock.locked():
                return {"success": False, "agent": "buyer_agents", "error": "Agent is already executing"}
            async with lock:
                state["status"] = "EXECUTING"
                try:
                    res = await buyer_agents_fleet.run_all_buyers_step()
                    state["last_run"] = datetime.now(timezone.utc).isoformat()
                    state["last_run_ts"] = time.time()
                    state["actions_count"] += 1
                    state["status"] = "RUNNING 24/7"
                    return {"success": True, "agent": "buyer_agents", "result": res}
                except Exception as e:
                    state["status"] = "ERROR"
                    state["last_error"] = str(e)
                    state["error_count"] = int(state.get("error_count", 0)) + 1
                    return {"success": False, "error": str(e)}

        if agent_key not in agents_map:
            return {"success": False, "error": f"Unknown agent '{agent_key}'"}

        agent = agents_map[agent_key]
        state = self.agent_states.get(agent_key, {})
        lock = self._agent_locks.setdefault(agent_key, asyncio.Lock())
        if lock.locked():
            return {"success": False, "agent": agent_key, "error": "Agent is already executing"}
        async with lock:
            return await self._trigger_agent_locked(agent_key, agent, state)

    async def _trigger_agent_locked(self, agent_key: str, agent: Any, state: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single manually requested cycle under the agent's lock."""
        state["status"] = "EXECUTING"
        state["started_at"] = datetime.now(timezone.utc).isoformat()
        log_agent_action(state.get("name", agent_key), "Cycle started", "Executing a requested agent cycle.", autonomous=False)
        try:
            timeout_seconds = max(10, int(os.environ.get("AGENT_CYCLE_TIMEOUT_SECONDS", "90")))
            res = await asyncio.wait_for(agent.run_autonomous_cycle(), timeout=timeout_seconds)
            state["last_run"] = datetime.now(timezone.utc).isoformat()
            state["last_run_ts"] = time.time()
            state["actions_count"] += 1
            state["status"] = "RUNNING 24/7"
            state["last_error"] = None
            state["last_summary"] = str(res.get("details") or res.get("message") or "Cycle completed")[:600]
            log_agent_action(state.get("name", agent_key), "Cycle completed", state["last_summary"], autonomous=False)
            return {"success": True, "agent": agent_key, "result": res}
        except Exception as e:
            state["status"] = "ERROR"
            state["last_error"] = str(e)
            state["error_count"] = int(state.get("error_count", 0)) + 1
            log_agent_action(state.get("name", agent_key), "Cycle failed", str(e), autonomous=False)
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
            if not self._running and enriched.get("status") != "EXECUTING":
                enriched["status"] = "MANUAL"
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
