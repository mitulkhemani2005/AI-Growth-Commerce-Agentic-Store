"""
Reinforcement Learning (RL) Engine for AI Agents
=================================================
Environment-in-the-loop Reinforcement Learning for Autonomous Agent Fleets.


Key Components:
1. Environment State Representation: Discretized / hashed multi-feature business state.
2. Action Space: Tool calls, directives, pricing strategies, inventory batches, fulfillment speeds.
3. Reward Functions: Tailored business KPI rewards per specialist agent.
4. Tabular Q-Learning with Softmax / Epsilon-Greedy Policy Exploration.
5. Experience Replay & Trajectory Logging (s, a, r, s', done).
6. Policy Advice Generator: Injects real-time RL recommended actions and Q-values into agent context.
7. Persistent Q-Tables & Experience History to `data/agent_rl.json`.
"""

import os
import json
import time
import math
import random
import threading
import datetime
from typing import Dict, List, Any, Optional, Tuple

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
RL_DATA_FILE = os.path.join(DATA_DIR, "agent_rl.json")


class AgentRLPolicy:
    """
    Q-Learning Policy and Trajectory Memory for an individual agent.
    """

    def __init__(self, agent_name: str, alpha: float = 0.15, gamma: float = 0.85, epsilon: float = 0.10):
        self.agent_name = agent_name
        self.alpha = alpha       # Learning rate
        self.gamma = gamma       # Discount factor
        self.epsilon = epsilon   # Exploration rate
        self._lock = threading.RLock()

        # Q-Table: state_key -> {action_name: q_value}
        self.q_table: Dict[str, Dict[str, float]] = {}

        # Trajectories / Transitions: list of (state, action, reward, next_state, timestamp)
        self.history: List[Dict[str, Any]] = []

        # Running statistics
        self.total_rewards: float = 0.0
        self.episode_count: int = 0
        self.action_counts: Dict[str, int] = {}
        self.last_action: Optional[str] = None
        self.last_state: Optional[str] = None

    def discretize_state(self, state_features: Dict[str, Any]) -> str:
        """
        Convert structured state features into a stable discretized state bucket string.
        """
        parts = []
        for k in sorted(state_features.keys()):
            val = state_features[k]
            if isinstance(val, (int, float)):
                if "stock" in k or "count" in k or "orders" in k:
                    # Discrete bins: 0, 1-3, 4-10, 11-25, 25+
                    if val <= 0:
                        bucket = "0"
                    elif val <= 3:
                        bucket = "low(1-3)"
                    elif val <= 10:
                        bucket = "med(4-10)"
                    elif val <= 25:
                        bucket = "high(11-25)"
                    else:
                        bucket = "huge(25+)"
                elif "balance" in k or "revenue" in k or "profit" in k:
                    # Currency bins: 0, <200, <500, <1000, <5000, 5000+
                    if val <= 50:
                        bucket = "<50"
                    elif val <= 200:
                        bucket = "200"
                    elif val <= 500:
                        bucket = "500"
                    elif val <= 1000:
                        bucket = "1k"
                    elif val <= 5000:
                        bucket = "5k"
                    else:
                        bucket = "5k+"
                elif "rate" in k or "pct" in k:
                    # Percentage bins: 0%, <10%, <25%, 25%+
                    if val <= 0:
                        bucket = "0%"
                    elif val <= 10:
                        bucket = "<10%"
                    elif val <= 25:
                        bucket = "<25%"
                    else:
                        bucket = "25%+"
                else:
                    bucket = f"{int(val)}"
                parts.append(f"{k}={bucket}")
            elif isinstance(val, bool):
                parts.append(f"{k}={'T' if val else 'F'}")
            else:
                parts.append(f"{k}={str(val)[:15]}")
        return "|".join(parts) if parts else "default_state"

    def get_q_values(self, state_key: str) -> Dict[str, float]:
        with self._lock:
            return self.q_table.get(state_key, {})

    def get_best_action(self, state_key: str, available_actions: Optional[List[str]] = None) -> Tuple[Optional[str], float]:
        """
        Returns (best_action, q_value) for state_key using current policy.
        """
        with self._lock:
            actions_dict = self.q_table.get(state_key, {})
            if not actions_dict:
                if available_actions:
                    return random.choice(available_actions), 0.0
                return None, 0.0

            candidates = actions_dict
            if available_actions:
                candidates = {a: actions_dict.get(a, 0.0) for a in available_actions}

            if not candidates:
                return None, 0.0

            best_act = max(candidates.keys(), key=lambda a: candidates[a])
            return best_act, candidates[best_act]

    def select_action_softmax(self, state_key: str, available_actions: List[str], temperature: float = 1.0) -> str:
        """
        Softmax action selection over Q-values for exploration/exploitation balance.
        """
        with self._lock:
            if not available_actions:
                return "default_action"
            actions_dict = self.q_table.get(state_key, {})
            q_vals = [actions_dict.get(a, 0.0) for a in available_actions]
            
            # Subtract max for numerical stability
            max_q = max(q_vals)
            exp_vals = [math.exp((q - max_q) / max(temperature, 0.05)) for q in q_vals]
            sum_exp = sum(exp_vals)
            probs = [ev / sum_exp for ev in exp_vals]

            r = random.random()
            cum = 0.0
            for act, p in zip(available_actions, probs):
                cum += p
                if r <= cum:
                    return act
            return available_actions[-1]

    def update_transition(self, state_key: str, action: str, reward: float, next_state_key: str):
        """
        Standard Q-Learning Update:
        Q(s, a) = Q(s, a) + alpha * [reward + gamma * max_a' Q(s', a') - Q(s, a)]
        """
        with self._lock:
            if state_key not in self.q_table:
                self.q_table[state_key] = {}
            current_q = self.q_table[state_key].get(action, 0.0)

            # Max Q for next state
            next_actions = self.q_table.get(next_state_key, {})
            max_next_q = max(next_actions.values()) if next_actions else 0.0

            # Bellman update
            new_q = current_q + self.alpha * (reward + (self.gamma * max_next_q) - current_q)
            self.q_table[state_key][action] = round(new_q, 4)

            # Update stats
            self.total_rewards += reward
            self.episode_count += 1
            self.action_counts[action] = self.action_counts.get(action, 0) + 1
            self.last_action = action
            self.last_state = state_key

            # Record trajectory transition
            self.history.append({
                "state": state_key,
                "action": action,
                "reward": round(reward, 4),
                "next_state": next_state_key,
                "q_after": round(new_q, 4),
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
            if len(self.history) > 100:
                self.history = self.history[-100:]

    def get_policy_advice(self, state_key: str) -> str:
        """
        Generate actionable RL guidance text for LLM injection.
        """
        with self._lock:
            actions_dict = self.q_table.get(state_key, {})
            if not actions_dict:
                return ""
            
            sorted_actions = sorted(actions_dict.items(), key=lambda x: x[1], reverse=True)
            top_rec = sorted_actions[0]
            worst_rec = sorted_actions[-1] if len(sorted_actions) > 1 and sorted_actions[-1][1] < 0 else None

            lines = [f"• Recommended Action: `{top_rec[0]}` (Expected Value Q: {top_rec[1]:+.2f})"]
            if worst_rec and worst_rec[1] < 0:
                lines.append(f"• Avoid Action: `{worst_rec[0]}` (Penalized Value Q: {worst_rec[1]:+.2f})")
            return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "agent_name": self.agent_name,
                "alpha": self.alpha,
                "gamma": self.gamma,
                "epsilon": self.epsilon,
                "total_rewards": round(self.total_rewards, 4),
                "episode_count": self.episode_count,
                "action_counts": self.action_counts,
                "q_table": self.q_table,
                "history": self.history[-30:]
            }

    def load_from_dict(self, data: Dict[str, Any]):
        with self._lock:
            self.alpha = data.get("alpha", self.alpha)
            self.gamma = data.get("gamma", self.gamma)
            self.epsilon = data.get("epsilon", self.epsilon)
            self.total_rewards = data.get("total_rewards", 0.0)
            self.episode_count = data.get("episode_count", 0)
            self.action_counts = data.get("action_counts", {})
            self.q_table = data.get("q_table", {})
            self.history = data.get("history", [])


class RLManager:
    """
    Fleet-wide Reinforcement Learning Coordinator.
    Computes domain-specific reward signals and orchestrates agent learning.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._policies: Dict[str, AgentRLPolicy] = {}
        self._last_save: float = 0.0
        self._save_interval: float = 20.0
        self._load_from_disk()

    def get_policy(self, agent_name: str) -> AgentRLPolicy:
        with self._lock:
            if agent_name not in self._policies:
                self._policies[agent_name] = AgentRLPolicy(agent_name)
            return self._policies[agent_name]

    # ── Domain Reward Computers (OpenOfficeRL inspired) ───────────────────────

    def compute_ceo_reward(self, before: Dict[str, Any], after: Dict[str, Any], action: str) -> float:
        """
        CEO Reward Function:
        + Growth in Revenue & Profit
        + Efficient Treasury utilization
        - Penalties for SLA breaches or high refund rates
        """
        r_rev = (after.get("revenue", 0.0) - before.get("revenue", 0.0)) * 0.08
        r_profit = (after.get("profit", 0.0) - before.get("profit", 0.0)) * 0.15
        r_orders = (after.get("confirmed_orders", 0) - before.get("confirmed_orders", 0)) * 2.0
        
        # Penalties
        ref_rate = after.get("refund_rate", 0.0)
        p_refund = -5.0 if ref_rate > 20.0 else (2.0 if ref_rate == 0.0 else 0.0)
        
        # Action efficiency bonus
        act_bonus = 1.0 if "restock" in action or "growth" in action or "buyer" in action else 0.0
        return round(r_rev + r_profit + r_orders + p_refund + act_bonus, 3)

    def compute_price_manager_reward(self, before: Dict[str, Any], after: Dict[str, Any], action: str) -> float:
        """
        Price Manager Reward:
        + Margin optimization without sacrificing sales volume
        + Scarcity protection on low stock
        - Overpricing causing zero demand
        """
        adjusted_count = after.get("adjusted_count", 0)
        surges = after.get("surges", 0)
        base_price_violations = after.get("base_price_violations", 0)
        
        r_actions = min(adjusted_count * 1.5, 6.0)
        r_surges = surges * 2.0
        p_violation = -50.0 if base_price_violations > 0 else 2.0
        return round(r_actions + r_surges + p_violation, 3)

    def compute_inventory_manager_reward(self, before: Dict[str, Any], after: Dict[str, Any], action: str) -> float:
        """
        Inventory Manager Reward:
        + Preventing stockouts on popular items
        + Timely restock requests submitted to CEO
        - Unnecessary overstock expenditure
        """
        restocked_count = len(after.get("restocked", []))
        requests_sent = len(after.get("restock_requests_sent", []))
        zero_stock_count = after.get("zero_stock_count", 0)
        
        r_restock = restocked_count * 3.0
        r_requests = requests_sent * 2.0
        p_zero = -2.0 * zero_stock_count
        return round(r_restock + r_requests + p_zero, 3)

    def compute_order_manager_reward(self, before: Dict[str, Any], after: Dict[str, Any], action: str) -> float:
        """
        Order Manager Reward:
        + Orders confirmed within SLA (<1h)
        + Lifecycle progression (Shipped / Delivered)
        - Pending orders aging > 1h
        """
        shipped = after.get("shipped_count", 0)
        delivered = after.get("delivered_count", 0)
        sla_breaches = after.get("sla_breaches", 0)
        
        r_flow = (shipped * 2.5) + (delivered * 4.0)
        p_breach = -5.0 * sla_breaches
        return round(r_flow + p_breach, 3)

    def compute_finance_manager_reward(self, before: Dict[str, Any], after: Dict[str, Any], action: str) -> float:
        """
        Finance Manager Reward (Sole Payment Authority):
        + Accurate 24-hour refund evaluations (rejecting shipped/delivered, approving eligible)
        + Maintaining positive treasury bank balance
        - Erroneous payment / refund processing
        """
        bank_balance = after.get("bank_balance", 0.0)
        approved_refunds = after.get("approved_refunds_count", 0)
        rejected_ineligible = after.get("rejected_ineligible_count", 0)
        
        r_treasury = 2.0 if bank_balance > 100.0 else -5.0
        r_policy = (approved_refunds * 3.0) + (rejected_ineligible * 4.0)
        return round(r_treasury + r_policy, 3)

    def compute_dispatcher_reward(self, before: Dict[str, Any], after: Dict[str, Any], action: str) -> float:
        """
        Dispatcher Reward:
        + Tracking numbers assigned
        + Following realistic random-delay window without dropping orders
        """
        dispatched_count = len(after.get("dispatched", []))
        scheduled_count = len(after.get("newly_scheduled", []))
        queue_size = after.get("queue_size", 0)
        
        r_dispatch = dispatched_count * 4.0
        r_sched = scheduled_count * 1.5
        p_stuck = -0.5 * max(0, queue_size - 10)
        return round(r_dispatch + r_sched + p_stuck, 3)

    def compute_review_manager_reward(self, before: Dict[str, Any], after: Dict[str, Any], action: str) -> float:
        """
        Review Manager Reward:
        + Proactively detecting negative trends and alerting CEO
        + Synthesizing rich product sentiment
        """
        alerts_sent = after.get("alerts_sent", 0)
        reviews_audited = after.get("reviews_audited", 0)
        
        r_audit = min(reviews_audited * 0.5, 5.0)
        r_alert = alerts_sent * 3.0
        return round(r_audit + r_alert, 3)

    def compute_customer_agent_reward(self, tool_name: str, result: Dict[str, Any]) -> float:
        """
        Nova Customer Agent Reward:
        + Successfully completing purchases, adding to cart, answering questions
        - Tool execution errors or failed checkouts
        """
        if not result or result.get("error"):
            return -2.0
        if tool_name in ["trigger_checkout", "quick_buy_product"]:
            return 10.0
        if tool_name in ["add_to_cart", "batch_add_to_cart"]:
            return 3.0
        if tool_name in ["track_order", "view_order_history", "get_product_reviews"]:
            return 1.5
        if tool_name == "request_order_refund":
            return 2.0  # Successfully routed to Finance
        return 1.0

    def compute_buyer_reward(self, buyer_id: str, step_result: Dict[str, Any]) -> float:
        """
        AI Buyer Reward:
        + Completing diverse purchases
        + Writing reviews
        + Simulating realistic returns
        """
        action = step_result.get("action", "")
        if action == "BUY":
            return 6.0
        if action == "REVIEW":
            return 4.0
        if action == "RETURN_REQUEST":
            return 3.0
        if action == "BROWSE":
            return 1.0
        return 0.5

    # ── Cycle Transition Step Hook ──────────────────────────────────────────

    def record_step(self, agent_name: str, state_features: Dict[str, Any], action: str,
                    reward: float, next_state_features: Dict[str, Any]):
        """
        Records a step transition, updates Q-values, and triggers periodic persistence.
        """
        policy = self.get_policy(agent_name)
        s_key = policy.discretize_state(state_features)
        s_next_key = policy.discretize_state(next_state_features)
        policy.update_transition(s_key, action, reward, s_next_key)
        self._maybe_save()

    def get_agent_guidance(self, agent_name: str, state_features: Dict[str, Any]) -> str:
        """
        Returns RL policy guidance text for LLM injection.
        """
        policy = self.get_policy(agent_name)
        s_key = policy.discretize_state(state_features)
        advice = policy.get_policy_advice(s_key)
        if not advice:
            # Fallback to general advice across all states
            top_actions = sorted(policy.action_counts.items(), key=lambda x: x[1], reverse=True)[:2]
            if top_actions:
                advice = f"• Historical Preferred Action: `{top_actions[0][0]}` (Executed {top_actions[0][1]} times, Fleet Reward: {policy.total_rewards:+.1f})"
        
        if not advice:
            return ""
        return f"\n[RL POLICY GUIDANCE (OpenOfficeRL Optimized)]:\n{advice}\n"

    def get_fleet_performance_report(self) -> Dict[str, Any]:
        """
        Fleet-wide RL summary for CEO dashboard and reports.
        """
        with self._lock:
            report = {}
            for name, pol in self._policies.items():
                top_acts = sorted(pol.action_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                report[name] = {
                    "total_rewards": round(pol.total_rewards, 2),
                    "episodes": pol.episode_count,
                    "q_states_explored": len(pol.q_table),
                    "top_actions": top_acts,
                    "recent_rewards": [h["reward"] for h in pol.history[-5:]] if pol.history else []
                }
            return report

    def _maybe_save(self):
        now = time.time()
        if now - self._last_save >= self._save_interval:
            self._save_to_disk()

    def save_now(self):
        self._save_to_disk()

    def _save_to_disk(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with self._lock:
                data = {name: pol.to_dict() for name, pol in self._policies.items()}
            tmp_path = RL_DATA_FILE + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, RL_DATA_FILE)
            self._last_save = time.time()
        except Exception as e:
            print(f"[RLManager] Save failed: {e}", flush=True)

    def _load_from_disk(self):
        if not os.path.exists(RL_DATA_FILE):
            return
        try:
            with open(RL_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                for agent_name, d in data.items():
                    pol = AgentRLPolicy(agent_name)
                    pol.load_from_dict(d)
                    self._policies[agent_name] = pol
            print(f"[RLManager] Loaded RL policies for {len(data)} agents.", flush=True)
        except Exception as e:
            print(f"[RLManager] Load failed: {e}", flush=True)


# ── Singleton ─────────────────────────────────────────────────────────────────
rl_manager = RLManager()
