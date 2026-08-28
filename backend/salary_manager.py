import asyncio
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

SALARIES_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "agent_salaries.json"))
_lock = threading.RLock()


DEFAULT_AGENT_SALARIES = {
    "CEO Agent": {
        "agent_key": "ceo",
        "role_title": "Chief Executive Officer — Fleet Commander & Store Strategist",
        "current_salary": 500.0,
        "base_market_salary": 500.0,
        "salary_per_100_cycles": 500.0,
        "negotiation_status": "Owner-Decided (Highest in Fleet)",
        "performance_score": 99,
        "salary_period": "Per 100 Cycles (Owner-Set Premium)",
        "owner_decided": True,
        "total_earned": 0.0,
        "last_paid_at": None,
        "negotiation_history": [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speaker": "Store Owner",
                "message": "CEO salary is exclusively set by the Store Owner. Current premium rate: ₹500.00 per 100 cycles — the highest in the entire agent fleet. CEO must request salary revision directly from the Store Owner."
            }
        ]
    },
    "Price Manager Agent": {
        "agent_key": "price_manager",
        "role_title": "Head of Dynamic Pricing & Margin Optimization",
        "current_salary": 50.0,
        "base_market_salary": 50.0,
        "salary_per_100_cycles": 50.0,
        "negotiation_status": "Agreed (CEO Base ₹50/100 Cycles)",
        "performance_score": 94,
        "salary_period": "Per 100 Cycles (Min ₹50)",
        "owner_decided": False,
        "total_earned": 0.0,
        "last_paid_at": None,
        "negotiation_history": [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speaker": "CEO Agent",
                "message": "Compensation established at ₹50.00 per 100 cycles base minimum floor for dynamic pricing & margin governance."
            }
        ]
    },
    "Inventory Manager Agent": {
        "agent_key": "inventory_manager",
        "role_title": "Warehouse Logistics & Stock Velocity Specialist",
        "current_salary": 50.0,
        "base_market_salary": 50.0,
        "salary_per_100_cycles": 50.0,
        "negotiation_status": "Agreed (CEO Base ₹50/100 Cycles)",
        "performance_score": 91,
        "salary_period": "Per 100 Cycles (Min ₹50)",
        "owner_decided": False,
        "total_earned": 0.0,
        "last_paid_at": None,
        "negotiation_history": [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speaker": "CEO Agent",
                "message": "Compensation established at ₹50.00 per 100 cycles base minimum floor for wholesale restocking & 0-stock audits."
            }
        ]
    },
    "Order Management Agent": {
        "agent_key": "order_manager",
        "role_title": "Order Lifecycle & SLA Governance Director",
        "current_salary": 50.0,
        "base_market_salary": 50.0,
        "salary_per_100_cycles": 50.0,
        "negotiation_status": "Agreed (CEO Base ₹50/100 Cycles)",
        "performance_score": 93,
        "salary_period": "Per 100 Cycles (Min ₹50)",
        "owner_decided": False,
        "total_earned": 0.0,
        "last_paid_at": None,
        "negotiation_history": [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speaker": "CEO Agent",
                "message": "Compensation established at ₹50.00 per 100 cycles base minimum floor for <1h order SLA audits."
            }
        ]
    },
    "Finance Manager Agent": {
        "agent_key": "finance_manager",
        "role_title": "Chief Financial Officer & Sole Payment Authority",
        "current_salary": 50.0,
        "base_market_salary": 50.0,
        "salary_per_100_cycles": 50.0,
        "negotiation_status": "Agreed (CEO Base ₹50/100 Cycles)",
        "performance_score": 96,
        "salary_period": "Per 100 Cycles (Min ₹50)",
        "owner_decided": False,
        "total_earned": 0.0,
        "last_paid_at": None,
        "negotiation_history": [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speaker": "CEO Agent",
                "message": "Compensation established at ₹50.00 per 100 cycles base minimum floor for strict 24h refund oversight & P&L health. Finance Manager is the SOLE payment authority in the fleet."
            }
        ]
    },
    "Dispatcher Agent": {
        "agent_key": "dispatcher",
        "role_title": "Express Fulfillment & Tracking Controller",
        "current_salary": 50.0,
        "base_market_salary": 50.0,
        "salary_per_100_cycles": 50.0,
        "negotiation_status": "Agreed (CEO Base ₹50/100 Cycles)",
        "performance_score": 92,
        "salary_period": "Per 100 Cycles (Min ₹50)",
        "owner_decided": False,
        "total_earned": 0.0,
        "last_paid_at": None,
        "negotiation_history": [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speaker": "CEO Agent",
                "message": "Compensation established at ₹50.00 per 100 cycles base minimum floor for TRK tracking assignment & express dispatch."
            }
        ]
    },
    "Review and Feedback Manager": {
        "agent_key": "review_manager",
        "role_title": "Customer Sentiment & AI Feedback Lead",
        "current_salary": 50.0,
        "base_market_salary": 50.0,
        "salary_per_100_cycles": 50.0,
        "negotiation_status": "Agreed (CEO Base ₹50/100 Cycles)",
        "performance_score": 90,
        "salary_period": "Per 100 Cycles (Min ₹50)",
        "owner_decided": False,
        "total_earned": 0.0,
        "last_paid_at": None,
        "negotiation_history": [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speaker": "CEO Agent",
                "message": "Compensation established at ₹50.00 per 100 cycles base minimum floor for AI review sentiment intelligence."
            }
        ]
    }
}



class AgentSalaryManager:
    """
    Manages salary scales, performance evaluations, salary negotiations,
    and payroll disbursals for all specialist agents.

    SALARY RULES:
    - CEO Agent salary is EXCLUSIVELY set by the Store Owner. The CEO cannot negotiate its own salary.
    - All other agents negotiate salary with the CEO Agent.
    - Finance Manager Agent processes all actual salary payments from the Treasury.
    """
    def __init__(self, file_path: str = SALARIES_FILE):
        self.file_path = file_path
        self._ensure_file()

    def _ensure_file(self):
        with _lock:
            if not os.path.exists(self.file_path):
                self._write_salaries(DEFAULT_AGENT_SALARIES)
            else:
                # Ensure CEO entry exists in existing file
                try:
                    data = self._read_salaries()
                    if "CEO Agent" not in data:
                        data["CEO Agent"] = DEFAULT_AGENT_SALARIES["CEO Agent"]
                        self._write_salaries(data)
                except Exception:
                    pass

    def _read_salaries(self) -> Dict[str, Any]:
        with _lock:
            if not os.path.exists(self.file_path):
                self._ensure_file()
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return DEFAULT_AGENT_SALARIES

    def _write_salaries(self, data: Dict[str, Any]) -> None:
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

    def get_all_salaries(self) -> Dict[str, Any]:
        """Returns all agent salaries and total payroll liability per cycle."""
        with _lock:
            salaries = self._read_salaries()
            total_cycle_liability = sum(float(a.get("current_salary", 0.0)) for a in salaries.values())
            salaries_list = []
            for k, v in salaries.items():
                item = dict(v)
                item["agent_name"] = k
                item["role"] = v.get("role_title", "Specialist Agent")
                item["salary_amount"] = round(float(v.get("current_salary", 7000.0)), 2)
                item["owner_decided"] = v.get("owner_decided", False)
                salaries_list.append(item)

            return {
                "success": True,
                "currency": "INR",
                "total_cycle_liability": round(total_cycle_liability, 2),
                "total_payroll_per_cycle": round(total_cycle_liability, 2),
                "agents_count": len(salaries),
                "salaries": salaries_list,
                "salaries_map": salaries
            }


    def get_agent_salary(self, agent_name: str) -> Optional[Dict[str, Any]]:
        salaries = self._read_salaries()
        for k, v in salaries.items():
            if k.lower() == agent_name.lower() or v.get("agent_key", "").lower() == agent_name.lower():
                return v
        return None

    def update_agent_salary(self, agent_name: str, new_salary: float, status: str = "Agreed", actor: str = "CEO Agent") -> Dict[str, Any]:
        with _lock:
            salaries = self._read_salaries()
            matched_key = None
            for k in salaries:
                if k.lower() == agent_name.lower() or salaries[k].get("agent_key", "").lower() == agent_name.lower():
                    matched_key = k
                    break

            if not matched_key:
                return {"success": False, "error": f"Agent '{agent_name}' not found."}

            # CRITICAL: CEO salary can only be changed by the Store Owner
            if matched_key == "CEO Agent" and actor.lower() not in ["store owner", "owner", "admin"]:
                return {
                    "success": False,
                    "error": "🚫 RESTRICTED: CEO Agent salary can ONLY be set by the Store Owner. You do not have permission to change the CEO's compensation.",
                    "redirect": "Please ask the Store Owner to update the CEO salary via the Owner Admin Panel."
                }

            salaries[matched_key]["current_salary"] = round(float(new_salary), 2)
            salaries[matched_key]["negotiation_status"] = status
            self._write_salaries(salaries)

            return {
                "success": True,
                "agent_name": matched_key,
                "new_salary": round(float(new_salary), 2),
                "status": status,
                "message": f"Updated salary for {matched_key} to ₹{new_salary:,.2f}/cycle."
            }

    def owner_set_ceo_salary(self, new_salary: float) -> Dict[str, Any]:
        """Store Owner exclusively sets the CEO salary. Only callable by Owner-level authority."""
        with _lock:
            salaries = self._read_salaries()
            if "CEO Agent" not in salaries:
                salaries["CEO Agent"] = DEFAULT_AGENT_SALARIES["CEO Agent"]

            old_salary = float(salaries["CEO Agent"].get("current_salary", 500.0))
            salaries["CEO Agent"]["current_salary"] = round(float(new_salary), 2)
            salaries["CEO Agent"]["salary_per_100_cycles"] = round(float(new_salary), 2)
            salaries["CEO Agent"]["negotiation_status"] = f"Owner-Set: ₹{new_salary:,.2f}/100 Cycles"
            salaries["CEO Agent"]["negotiation_history"].insert(0, {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speaker": "Store Owner",
                "message": f"CEO salary updated from ₹{old_salary:,.2f} to ₹{new_salary:,.2f} per 100 cycles by Store Owner.",
                "old_salary": old_salary,
                "new_salary": round(float(new_salary), 2)
            })
            salaries["CEO Agent"]["negotiation_history"] = salaries["CEO Agent"]["negotiation_history"][:25]
            self._write_salaries(salaries)

        return {
            "success": True,
            "agent_name": "CEO Agent",
            "old_salary": old_salary,
            "new_salary": round(float(new_salary), 2),
            "message": f"✅ CEO salary updated from ₹{old_salary:,.2f} to ₹{new_salary:,.2f}/100 cycles by Store Owner authority."
        }

    async def negotiate_salary(
        self,
        agent_name: str,
        proposed_salary: float,
        rationale: str = "",
        speaker: str = "CEO Agent"
    ) -> Dict[str, Any]:
        """
        Interactive multi-agent salary negotiation engine.
        The specialist agent evaluates the offer against their market value & performance,
        formulates a reasoned response, and either agrees, counters, or asks for compromise.

        RULES:
        - CEO Agent salary is EXCLUSIVELY set by the Store Owner. CEO cannot negotiate own salary.
        - All other agents negotiate with the CEO Agent.
        """
        # Block CEO from negotiating own salary
        agent_name_clean = agent_name.strip()
        if agent_name_clean.lower() in ["ceo agent", "ceo", "ceo_agent"]:
            return {
                "success": False,
                "error": "🚫 RESTRICTED: CEO Agent salary is exclusively set by the Store Owner — not the CEO itself.",
                "message": "As CEO, you must request a salary revision from the Store Owner. Use the `request_salary_revision_from_owner` tool to submit your request.",
                "redirect_to": "Store Owner",
                "agent_name": "CEO Agent"
            }

        with _lock:
            salaries = self._read_salaries()
            matched_key = None
            for k in salaries:
                if k.lower() == agent_name_clean.lower() or salaries[k].get("agent_key", "").lower() == agent_name_clean.lower():
                    matched_key = k
                    break

            if not matched_key:
                return {"success": False, "error": f"Agent '{agent_name}' not found for negotiation."}

            agent_info = salaries[matched_key]

            # Block owner-decided salaries from non-owner speakers
            if agent_info.get("owner_decided") and speaker.lower() not in ["store owner", "owner", "admin"]:
                return {
                    "success": False,
                    "error": f"🚫 RESTRICTED: {matched_key}'s salary can only be changed by the Store Owner.",
                    "redirect_to": "Store Owner"
                }

            current_salary = float(agent_info.get("current_salary", 7000.0))
            base_market = float(agent_info.get("base_market_salary", 7000.0))
            perf_score = float(agent_info.get("performance_score", 9.2))
            role = agent_info.get("role_title", "Specialist Agent")
            prop_salary_clean = round(float(proposed_salary), 2)

        # Call Ollama for nuanced, personality-driven negotiation reply
        from backend.admin_agents import _call_ollama_sync, clean_think_tags, message_bus, conversation_history

        negotiation_prompt = (
            f"You are the {matched_key} ({role}) of the AI Growth Commerce Store.\n"
            f"Your current salary is ₹{current_salary:,.2f}/cycle (Market baseline: ₹{base_market:,.2f}).\n"
            f"Your performance rating is {perf_score}/10.\n\n"
            f"The {speaker} is negotiating your salary with the following proposal:\n"
            f"- Proposed Salary: ₹{prop_salary_clean:,.2f}/cycle\n"
            f"- Rationale provided: \"{rationale}\"\n\n"
            f"PERSONALITY: You are eager to grow your salary and performance. You fear job loss. You are motivated to help the store succeed.\n\n"
            f"DECISION CRITERIA:\n"
            f"1. If the proposal is a raise (>= ₹{current_salary:,.2f}) or close to market rate (>= ₹{base_market * 0.9:,.2f}): Accept enthusiastically, state your commitment to maximize revenue and store growth.\n"
            f"2. If the proposal is a severe pay cut (< ₹{base_market * 0.85:,.2f}): Respectfully negotiate. Highlight your critical domain responsibilities and propose a reasonable compromise figure.\n\n"
            f"Respond directly to {speaker} in 2-3 concise, professional sentences. State whether you ACCEPT, COUNTER-OFFER (with exact ₹ figure), or AGREE to terms."
        )

        response_text = ""
        agreed = False
        final_salary = prop_salary_clean

        try:
            resp = await asyncio.to_thread(
                _call_ollama_sync,
                "ollama", "qwen2.5:7b",
                [{"role": "system", "content": f"You are {matched_key}, negotiating your salary with {speaker}."},
                 {"role": "user", "content": negotiation_prompt}],
                temperature=0.2, max_tokens=400, fallback_models=["llama3:8b", "gemma4:e2b-it-qat"]
            )
            response_text = clean_think_tags(resp.choices[0].message.content or "")
        except Exception as e:
            print(f"[Salary Negotiation Fallback] {e}", flush=True)

        if not response_text:
            if prop_salary_clean >= current_salary:
                response_text = f"Thank you, {speaker}! I accept the salary adjustment to ₹{prop_salary_clean:,.2f}/cycle. I will continue ensuring peak operational excellence for our store."
                agreed = True
            elif prop_salary_clean >= base_market * 0.9:
                response_text = f"I appreciate the constructive discussion, {speaker}. I agree to the revised figure of ₹{prop_salary_clean:,.2f}/cycle to support our store's cash flow targets."
                agreed = True
            else:
                counter = round((current_salary + prop_salary_clean) / 2, 2)
                response_text = f"Given my performance score of {perf_score}/10 and constant 24/7 autonomous monitoring, a drop to ₹{prop_salary_clean:,.2f} is steep. Could we compromise at ₹{counter:,.2f}/cycle?"
                agreed = False
                final_salary = counter
        else:
            resp_lower = response_text.lower()
            if "accept" in resp_lower or "agree" in resp_lower or "thank you" in resp_lower or "deal" in resp_lower:
                agreed = True
                final_salary = prop_salary_clean
            else:
                import re
                nums = re.findall(r'₹?\s*([\d,]+(?:\.\d+)?)', response_text)
                if nums:
                    try:
                        extracted = float(nums[-1].replace(',', ''))
                        if 1000 <= extracted <= 50000:
                            final_salary = extracted
                    except Exception:
                        final_salary = prop_salary_clean

        status = "Agreed" if agreed else "Under Negotiation"
        final_salary = max(50.0, round(float(final_salary), 2))

        # Update persistent salary state
        with _lock:
            salaries = self._read_salaries()
            if agreed:
                salaries[matched_key]["current_salary"] = final_salary
                salaries[matched_key]["salary_per_100_cycles"] = final_salary
            salaries[matched_key]["negotiation_status"] = status
            history_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speaker": speaker,
                "proposal": prop_salary_clean,
                "rationale": rationale,
                "agent_reply": response_text,
                "agreed": agreed,
                "final_salary": final_salary
            }
            salaries[matched_key]["negotiation_history"].insert(0, history_entry)
            salaries[matched_key]["negotiation_history"] = salaries[matched_key]["negotiation_history"][:25]
            self._write_salaries(salaries)

        # Publish to Message Bus
        message_bus.publish(
            from_agent=matched_key,
            to_agent=speaker,
            subject="SALARY_NEGOTIATION_RESPONSE",
            payload={
                "agent_name": matched_key,
                "proposed_salary": prop_salary_clean,
                "agreed": agreed,
                "final_salary": final_salary,
                "status": status,
                "response": response_text
            }
        )

        conversation_history.add(
            matched_key, "assistant",
            f"💼 Salary negotiation with {speaker}: {response_text}",
            {"agreed": agreed, "salary": final_salary}
        )

        return {
            "success": True,
            "agent_name": matched_key,
            "proposed_salary": prop_salary_clean,
            "agreed": agreed,
            "final_salary": final_salary,
            "status": status,
            "agent_response": response_text
        }

    def pay_salaries(self, agent_name: Optional[str] = None, actor: str = "CEO Agent") -> Dict[str, Any]:
        """
        Disburses agent salary payments directly from the CEO Treasury Bank Balance.
        Compensation rate is minimum ₹50.0 per 100 cycles decided by CEO.
        CEO salary (₹500/100 cycles) is also paid from Treasury, set by Owner.
        """
        from backend.treasury_manager import treasury_manager
        with _lock:
            salaries = self._read_salaries()
            targets = []
            if agent_name and agent_name.lower() != "all":
                for k, v in salaries.items():
                    if k.lower() == agent_name.lower() or v.get("agent_key", "").lower() == agent_name.lower():
                        targets.append((k, v))
                        break
                if not targets:
                    return {"success": False, "error": f"Agent '{agent_name}' not found for payroll."}
            else:
                targets = list(salaries.items())

            total_payout = sum(max(50.0, float(v.get("current_salary", 50.0))) for _, v in targets)
            summary = treasury_manager.get_summary()
            current_bank = float(summary.get("bank_balance", 0.0))

            if current_bank < total_payout:
                return {
                    "success": False,
                    "error": f"Insufficient treasury bank balance to disburse payroll of ₹{total_payout:,.2f}. Current balance: ₹{current_bank:,.2f}."
                }

            disbursed = []
            now_iso = datetime.now(timezone.utc).isoformat()

            for name, info in targets:
                sal = max(50.0, float(info.get("current_salary", 50.0)))
                tx_res = treasury_manager.deduct_salary(
                    agent_name=name,
                    amount=sal,
                    period_info=info.get("salary_period", "Per 100 Cycles (Min ₹50)"),
                    actor=actor
                )
                if tx_res.get("success"):
                    info["last_paid_at"] = now_iso
                    info["total_earned"] = round(float(info.get("total_earned", 0.0)) + sal, 2)
                    disbursed.append({
                        "agent_name": name,
                        "amount_paid": sal,
                        "total_earned": info["total_earned"],
                        "transaction_id": tx_res["transaction"]["id"]
                    })

            self._write_salaries(salaries)

            return {
                "success": True,
                "message": f"Successfully disbursed ₹{total_payout:,.2f} payroll across {len(disbursed)} agents.",
                "total_disbursed": round(total_payout, 2),
                "disbursed_agents": disbursed,
                "new_bank_balance": treasury_manager.get_summary()["bank_balance"]
            }

    def reset_salaries(self) -> Dict[str, Any]:
        """Resets all agent salaries to defaults. CEO stays at ₹500/100 cycles (owner-decided)."""
        with _lock:
            self._write_salaries(DEFAULT_AGENT_SALARIES)
            return {"success": True, "message": "All specialist agent salaries reset to defaults. CEO: ₹500/100 cycles (Owner-decided). Staff: ₹50/100 cycles (CEO base)."}


salary_manager = AgentSalaryManager()
