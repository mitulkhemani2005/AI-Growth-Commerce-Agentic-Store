"""
Policy Engine — Deterministic Business Rules & Safety Validation
================================================================
Centralized deterministic policy enforcement for the AI Growth Commerce Store.
The LLM is NEVER the final authority on policy enforcement; all state-changing
actions must pass deterministic policy validation before execution.

Enforces:
  - Price floors (price >= BASE_PRICE)
  - Maximum price movement (<= 25% per adjustment)
  - Minimum gross margin (>= 15%)
  - 24-hour refund eligibility (order age <= 24h, not Shipped/Delivered)
  - Order state transition graph validity (monotonic progression)
  - Inventory non-negativity and wholesale treasury reserves
  - Treasury solvency and reserve protection (>= ₹100 buffer)
  - Role-Based Access Control (RBAC) across all 10 agents
  - Owner-exclusive actions and CEO salary revision rules
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set


# Configurable policy constants
MIN_TREASURY_RESERVE = float(os.environ.get("MIN_TREASURY_RESERVE", "100.0"))
MIN_GROSS_MARGIN_PCT = float(os.environ.get("MIN_GROSS_MARGIN_PCT", "15.0"))  # 15% minimum margin
MAX_PRICE_MOVEMENT_PCT = float(os.environ.get("MAX_PRICE_MOVEMENT_PCT", "25.0"))  # 25% max single delta
MAX_REFUND_AGE_HOURS = float(os.environ.get("MAX_REFUND_AGE_HOURS", "24.0"))  # 24 hour refund window
MIN_AGENT_SALARY_FLOOR = float(os.environ.get("MIN_AGENT_SALARY_FLOOR", "50.0"))  # ₹50 floor per cycle


@dataclass
class PolicyResult:
    """Standardized response from deterministic policy validation."""
    allowed: bool
    reason: str
    policy: str
    required_approval: Optional[str] = None
    risk_level: str = "low"  # low, medium, high, critical
    constraints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "policy": self.policy,
            "required_approval": self.required_approval,
            "risk_level": self.risk_level,
            "constraints": self.constraints,
            "metadata": self.metadata
        }


# =====================================================================
# ROLE-BASED ACCESS CONTROL (RBAC) AUTHORIZATION MATRIX
# =====================================================================

ALLOWED_ROLE_ACTIONS: Dict[str, Set[str]] = {
    "Store Owner": {
        "*"  # Unrestricted
    },
    "CEO Agent": {
        "delegate_task", "query_agent", "get_fleet_status", "get_agent_activity",
        "set_business_objective", "run_strategy_review", "get_business_forecast",
        "get_sales_forecast", "get_cashflow_forecast", "get_unit_economics",
        "get_business_risk_report", "get_anomaly_report", "get_inventory_risk_report",
        "get_pricing_risk_report", "simulate_business_decision", "escalate_to_owner",
        "approve_restock_request", "negotiate_agent_salary", "pay_agent_salaries",
        "request_salary_revision_from_owner", "acquire_inventory_stock", "broadcast_growth_directive",
        "send_agent_message", "get_admin_dashboard_metrics", "get_inter_agent_messages",
        "get_agent_conversations", "trigger_agent_cycle", "ask_specialist_agent",
        "get_agent_memory_report", "get_fleet_rl_report", "conduct_ceo_discussion"
    },
    "Admin Chat Agent": {
        "run_prompt", "forward_to_ceo", "owner_command_gateway"
    },
    "Price Manager Agent": {
        "estimate_optimal_price", "forecast_demand", "calculate_price_elasticity",
        "calculate_product_margin", "detect_price_anomaly", "create_promotion",
        "run_price_experiment", "get_competitor_price_signal", "set_approved_price",
        "batch_adjustment", "handle_message_or_query", "run_autonomous_cycle"
    },
    "Inventory Manager Agent": {
        "calculate_reorder_point", "forecast_inventory_demand", "calculate_safety_stock",
        "estimate_stockout_risk", "estimate_overstock_risk", "identify_dead_inventory",
        "get_supplier_options", "create_purchase_request", "reconcile_inventory",
        "transfer_inventory", "acquire_wholesale_stock", "handle_message_or_query",
        "run_autonomous_cycle"
    },
    "Order Management Agent": {
        "advance_order", "validate_order_transition", "get_order_timeline",
        "predict_sla_breach", "calculate_delivery_risk", "detect_stuck_order",
        "resolve_order_exception", "notify_customer", "estimate_new_delivery_date",
        "update_order_status", "handle_message_or_query", "run_autonomous_cycle"
    },
    "Dispatcher Agent": {
        "select_best_carrier", "create_shipping_label", "schedule_pickup",
        "track_shipment", "get_carrier_eta", "detect_delivery_exception",
        "handle_failed_delivery", "reschedule_delivery", "optimize_shipping_cost",
        "assign_tracking_number", "handle_message_or_query", "run_autonomous_cycle"
    },
    "Finance Manager Agent": {
        "process_refund", "verify_payment", "reconcile_payments",
        "calculate_cashflow", "calculate_unit_economics", "calculate_profitability_by_product",
        "detect_payment_anomaly", "detect_fraud_risk", "get_refund_status",
        "get_chargeback_status", "generate_invoice", "pay_agent_salaries",
        "deposit_sales", "deduct_refund", "handle_message_or_query", "run_autonomous_cycle"
    },
    "Review and Feedback Manager": {
        "cluster_review_issues", "detect_fake_review_patterns", "detect_recurring_product_failures",
        "calculate_sentiment_trend", "identify_feature_requests", "identify_return_reasons",
        "create_product_quality_alert", "generate_customer_response", "calculate_review_impact_on_sales",
        "generate_ai_review_summary", "handle_message_or_query", "run_autonomous_cycle"
    },
    "Customer AI (Nova)": {
        "search_inventory", "get_product_details", "add_to_cart", "batch_add_to_cart",
        "remove_from_cart", "clear_cart", "view_cart", "trigger_razorpay_checkout",
        "view_order_history", "track_order", "cancel_order", "request_order_refund",
        "submit_product_review", "purchase_assistant", "recommend_products",
        "compare_products", "get_personalized_offers", "apply_coupon",
        "reserve_cart_inventory", "get_delivery_estimate", "reorder_previous_purchase",
        "create_support_request"
    },
    "AI Buyer Fleet": {
        "execute_buyer_step", "simulate_coupon_usage", "simulate_checkout_failure",
        "simulate_payment_failure", "simulate_stockout", "simulate_delivery_delay",
        "test_price_change", "test_refund_flow", "test_order_exception",
        "validate_business_invariants", "generate_test_report"
    }
}


# =====================================================================
# ORDER STATE TRANSITION GRAPH
# =====================================================================

LEGAL_ORDER_TRANSITIONS: Dict[str, Set[str]] = {
    "Pending": {"Confirmed", "Cancelled"},
    "Confirmed": {"Dispatched", "Cancelled", "Refunded"},
    "Dispatched": {"Shipped"},
    "Shipped": {"Delivered"},
    "Delivered": set(),  # Terminal state (Non-refundable per 24h policy)
    "Cancelled": {"Refunded"},  # Can transition to Refunded once payment reversed
    "Refunded": set()  # Terminal state
}


class PolicyEngine:
    """
    Centralized Deterministic Policy Engine.
    All state mutations and financial workflows must validate against this engine.
    """

    @staticmethod
    def validate_authorization(actor: str, action: str) -> PolicyResult:
        """Validates if the actor possesses deterministic RBAC permission for the action."""
        if not actor:
            return PolicyResult(
                allowed=False,
                reason="Actor identity is missing or empty.",
                policy="RBAC_AUTHENTICATION_POLICY",
                risk_level="critical"
            )

        # Store Owner has universal authority
        if actor in ["Store Owner", "Omnipotent Admin", "System"]:
            return PolicyResult(
                allowed=True,
                reason=f"Action '{action}' authorized for administrative principal '{actor}'.",
                policy="RBAC_OWNER_AUTHORIZATION",
                risk_level="low"
            )

        # Match actor against known roles
        matched_role = None
        for role_name in ALLOWED_ROLE_ACTIONS:
            if role_name.lower() in actor.lower():
                matched_role = role_name
                break

        if not matched_role:
            return PolicyResult(
                allowed=False,
                reason=f"Unknown actor '{actor}' not recognized in RBAC matrix.",
                policy="RBAC_UNKNOWN_ACTOR_POLICY",
                risk_level="high"
            )

        allowed_actions = ALLOWED_ROLE_ACTIONS.get(matched_role, set())
        if "*" in allowed_actions or action in allowed_actions:
            return PolicyResult(
                allowed=True,
                reason=f"Action '{action}' is permitted for role '{matched_role}'.",
                policy="RBAC_ROLE_POLICY",
                risk_level="low"
            )

        return PolicyResult(
            allowed=False,
            reason=f"Action '{action}' is not permitted for role '{matched_role}'.",
            policy="RBAC_ACCESS_DENIED_POLICY",
            required_approval="Store Owner" if "salary" in action or "override" in action else "CEO Agent",
            risk_level="high",
            constraints=[f"Actor '{matched_role}' cannot perform '{action}'"]
        )

    @staticmethod
    def validate_price_change(
        product_id: str,
        current_price: float,
        proposed_price: float,
        base_price: float,
        actor: str = "Price Manager Agent"
    ) -> PolicyResult:
        """
        Validates price adjustments against:
        1. BASE_PRICE floor (price >= BASE_PRICE)
        2. Minimum gross margin (>= 15%)
        3. Maximum price delta per step (<= 25%)
        """
        if proposed_price is None or proposed_price <= 0:
            return PolicyResult(
                allowed=False,
                reason="Proposed price must be a positive non-zero number.",
                policy="PRICE_SANITY_POLICY",
                risk_level="high"
            )

        # 1. Base Price Floor Check
        if base_price and proposed_price < base_price:
            return PolicyResult(
                allowed=False,
                reason=f"Proposed price (₹{proposed_price:,.2f}) is strictly below immutable BASE_PRICE floor (₹{base_price:,.2f}).",
                policy="PRICE_FLOOR_PROTECTION_POLICY",
                risk_level="high",
                constraints=[f"Price must be >= ₹{base_price:,.2f}"]
            )

        # 2. Minimum Gross Margin Check: (Price - Base) / Price >= 15%
        if base_price and base_price > 0:
            margin_pct = ((proposed_price - base_price) / proposed_price) * 100.0
            if margin_pct < (MIN_GROSS_MARGIN_PCT - 0.01):  # Allow tiny floating point slack
                return PolicyResult(
                    allowed=False,
                    reason=f"Gross margin ({margin_pct:.1f}%) is below minimum store policy threshold ({MIN_GROSS_MARGIN_PCT}%).",
                    policy="MINIMUM_MARGIN_POLICY",
                    risk_level="medium",
                    constraints=[f"Minimum margin threshold is {MIN_GROSS_MARGIN_PCT}%"]
                )

        # 3. Maximum Price Movement Delta Check (<= 25%)
        if current_price and current_price > 0:
            pct_delta = abs(proposed_price - current_price) / current_price * 100.0
            if pct_delta > MAX_PRICE_MOVEMENT_PCT and actor != "Store Owner":
                return PolicyResult(
                    allowed=False,
                    reason=f"Price movement delta of {pct_delta:.1f}% exceeds maximum allowable autonomous swing of {MAX_PRICE_MOVEMENT_PCT}%.",
                    policy="PRICE_MOVEMENT_VOLATILITY_POLICY",
                    required_approval="Store Owner",
                    risk_level="high",
                    constraints=[f"Max autonomous price delta is {MAX_PRICE_MOVEMENT_PCT}% per adjustment"]
                )

        return PolicyResult(
            allowed=True,
            reason=f"Price adjustment to ₹{proposed_price:,.2f} complies with BASE_PRICE floor, minimum margin, and delta constraints.",
            policy="PRICE_VALIDATION_POLICY",
            risk_level="low"
        )

    @staticmethod
    def validate_refund_eligibility(
        order: Dict[str, Any],
        actor: str = "Finance Manager Agent",
        force_override: bool = False
    ) -> PolicyResult:
        """
        Validates refund eligibility:
        1. Only Finance Manager (or Owner) can execute refunds.
        2. Status must NOT be 'Delivered' or 'Shipped' (strictly non-refundable).
        3. Order age must be <= 24 hours.
        4. Order must not already be 'Refunded'.
        5. force_override is ONLY permitted for Store Owner.
        """
        # Security: force_override is restricted to Store Owner
        if force_override:
            if actor not in ["Store Owner", "Omnipotent Admin"]:
                return PolicyResult(
                    allowed=False,
                    reason="force_override is restricted exclusively to Store Owner. Autonomous agents cannot bypass refund policy.",
                    policy="OWNER_EXCLUSIVE_OVERRIDE_POLICY",
                    required_approval="Store Owner",
                    risk_level="critical"
                )
            return PolicyResult(
                allowed=True,
                reason="Refund approved via explicit Store Owner override.",
                policy="OWNER_OVERRIDE_POLICY",
                risk_level="high"
            )

        if not order:
            return PolicyResult(
                allowed=False,
                reason="Order not found in database.",
                policy="ORDER_EXISTENCE_POLICY",
                risk_level="high"
            )

        status = order.get("status", "")
        if status == "Refunded":
            return PolicyResult(
                allowed=False,
                reason=f"Order #{order.get('order_id')} has already been refunded.",
                policy="DUPLICATE_REFUND_PREVENTION_POLICY",
                risk_level="high"
            )

        # Shipped and Delivered items are strictly non-refundable
        if status in ["Shipped", "Delivered"]:
            return PolicyResult(
                allowed=False,
                reason=f"Order #{order.get('order_id')} is currently '{status}'. Shipped and Delivered orders are strictly non-refundable per store policy.",
                policy="24H_REFUND_SHIPPED_DELIVERED_RESTRICTION",
                risk_level="medium",
                constraints=["Delivered and Shipped orders cannot be refunded autonomously"]
            )

        # Check 24h window
        created_at_str = order.get("created_at")
        if created_at_str:
            try:
                created_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                age_hours = (now - created_dt).total_seconds() / 3600.0
                if age_hours > MAX_REFUND_AGE_HOURS:
                    return PolicyResult(
                        allowed=False,
                        reason=f"Order age ({age_hours:.1f} hours) exceeds the strict 24-hour refund window.",
                        policy="24H_REFUND_WINDOW_POLICY",
                        risk_level="medium",
                        constraints=[f"Refunds only valid within {MAX_REFUND_AGE_HOURS} hours of placement"]
                    )
            except Exception:
                pass

        return PolicyResult(
            allowed=True,
            reason=f"Order #{order.get('order_id')} meets all 24h refund eligibility requirements.",
            policy="REFUND_ELIGIBILITY_POLICY",
            risk_level="low"
        )

    @staticmethod
    def validate_order_state_transition(
        current_status: str,
        target_status: str,
        actor: str = "Order Management Agent"
    ) -> PolicyResult:
        """
        Validates that order state transitions follow the strict monotonic order graph:
        Pending -> Confirmed -> Dispatched -> Shipped -> Delivered, or Cancelled/Refunded.
        """
        curr = current_status.capitalize().strip() if current_status else "Pending"
        target = target_status.capitalize().strip() if target_status else ""

        if curr == target:
            return PolicyResult(
                allowed=True,
                reason=f"Order is already in state '{target}'. No-op state transition.",
                policy="ORDER_STATE_IDEMPOTENCY_POLICY",
                risk_level="low"
            )

        allowed_next = LEGAL_ORDER_TRANSITIONS.get(curr, set())
        if target in allowed_next:
            return PolicyResult(
                allowed=True,
                reason=f"Transition '{curr}' -> '{target}' is valid in the order state machine.",
                policy="ORDER_STATE_TRANSITION_POLICY",
                risk_level="low"
            )

        return PolicyResult(
            allowed=False,
            reason=f"Illegal order state transition: cannot jump directly from '{curr}' to '{target}'. Valid next states: {list(allowed_next)}.",
            policy="ORDER_STATE_INTEGRITY_POLICY",
            risk_level="high",
            constraints=[f"From '{curr}', allowed transitions are: {list(allowed_next)}"]
        )

    @staticmethod
    def validate_inventory_mutation(
        product_id: str,
        current_stock: int,
        delta: int,
        reason: str = "standard_adjustment"
    ) -> PolicyResult:
        """
        Enforces inventory invariant: stock cannot drop below zero.
        """
        new_stock = current_stock + delta
        if new_stock < 0:
            return PolicyResult(
                allowed=False,
                reason=f"Inventory mutation would result in negative stock ({new_stock} units for SKU {product_id}).",
                policy="INVENTORY_NON_NEGATIVE_POLICY",
                risk_level="critical",
                constraints=["Stock count cannot be negative"]
            )

        return PolicyResult(
            allowed=True,
            reason=f"Inventory mutation valid (new stock: {new_stock} units).",
            policy="INVENTORY_MUTATION_POLICY",
            risk_level="low"
        )

    @staticmethod
    def validate_wholesale_spend(
        cost: float,
        bank_balance: float,
        reserve: float = MIN_TREASURY_RESERVE,
        actor: str = "Inventory Manager Agent"
    ) -> PolicyResult:
        """
        Ensures treasury maintains minimum reserve balance during wholesale acquisition.
        """
        if cost <= 0:
            return PolicyResult(
                allowed=False,
                reason="Wholesale purchase cost must be greater than zero.",
                policy="TREASURY_SANITY_POLICY",
                risk_level="medium"
            )

        required_balance = cost + reserve
        if bank_balance < required_balance:
            return PolicyResult(
                allowed=False,
                reason=f"Treasury balance (₹{bank_balance:,.2f}) insufficient for acquisition cost (₹{cost:,.2f}) with minimum reserve buffer (₹{reserve:,.2f}).",
                policy="TREASURY_SOLVENCY_RESERVE_POLICY",
                required_approval="Store Owner",
                risk_level="high",
                constraints=[f"Bank balance must be >= ₹{required_balance:,.2f}"]
            )

        return PolicyResult(
            allowed=True,
            reason=f"Wholesale spend of ₹{cost:,.2f} approved with ₹{bank_balance - cost:,.2f} remaining above ₹{reserve:,.2f} reserve.",
            policy="TREASURY_SPEND_POLICY",
            risk_level="low"
        )

    @staticmethod
    def validate_salary_modification(
        agent_name: str,
        proposed_salary: float,
        actor: str = "CEO Agent"
    ) -> PolicyResult:
        """
        Validates salary adjustments:
        1. CEO salary is exclusively determined by Store Owner.
        2. Specialist staff salaries must be >= ₹50 minimum floor.
        """
        is_ceo = agent_name.lower().strip() in ["ceo agent", "ceo", "ceo_agent"]

        if is_ceo and actor != "Store Owner":
            return PolicyResult(
                allowed=False,
                reason="CEO Agent salary is exclusively determined by the Store Owner. CEO cannot negotiate or set its own salary.",
                policy="CEO_SALARY_OWNER_EXCLUSIVE_POLICY",
                required_approval="Store Owner",
                risk_level="high",
                constraints=["CEO salary revision requires Store Owner authorization"]
            )

        if proposed_salary < MIN_AGENT_SALARY_FLOOR:
            return PolicyResult(
                allowed=False,
                reason=f"Proposed salary (₹{proposed_salary:,.2f}) is below the mandatory minimum compensation floor (₹{MIN_AGENT_SALARY_FLOOR:,.2f}/cycle).",
                policy="MINIMUM_AGENT_SALARY_FLOOR_POLICY",
                risk_level="medium",
                constraints=[f"Salary must be >= ₹{MIN_AGENT_SALARY_FLOOR:,.2f}"]
            )

        return PolicyResult(
            allowed=True,
            reason=f"Salary proposal of ₹{proposed_salary:,.2f} for '{agent_name}' adheres to compensation policies.",
            policy="AGENT_SALARY_POLICY",
            risk_level="low"
        )


# Global Policy Engine Singleton
policy_engine = PolicyEngine()


def validate_policy(
    action: str,
    actor: str,
    resource: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Public entrypoint for deterministic policy validation across the entire system.
    """
    params = parameters or {}
    ctx = context or {}

    # 1. First validate RBAC authorization
    rbac_res = policy_engine.validate_authorization(actor, action)
    if not rbac_res.allowed:
        return rbac_res.to_dict()

    # 2. Action-specific deterministic validation
    if action in ["set_price", "set_approved_price", "adjust_price", "batch_adjustment"]:
        cur_p = float(params.get("current_price", 0.0))
        prop_p = float(params.get("proposed_price") or params.get("new_price") or 0.0)
        base_p = float(params.get("base_price", 0.0))
        return policy_engine.validate_price_change(
            product_id=resource or params.get("product_id", ""),
            current_price=cur_p,
            proposed_price=prop_p,
            base_price=base_p,
            actor=actor
        ).to_dict()

    elif action in ["refund", "process_refund", "cancel_order_and_refund"]:
        order_obj = params.get("order") or ctx.get("order") or {}
        forced = bool(params.get("force_override", False) or params.get("force", False))
        return policy_engine.validate_refund_eligibility(
            order=order_obj,
            actor=actor,
            force_override=forced
        ).to_dict()

    elif action in ["advance_order", "update_order_status"]:
        curr_st = str(params.get("current_status", ""))
        target_st = str(params.get("target_status") or params.get("new_status", ""))
        return policy_engine.validate_order_state_transition(
            current_status=curr_st,
            target_status=target_st,
            actor=actor
        ).to_dict()

    elif action in ["mutate_inventory", "deduct_stock", "add_stock"]:
        cur_stock = int(params.get("current_stock", 0))
        delta = int(params.get("delta", 0))
        return policy_engine.validate_inventory_mutation(
            product_id=resource or params.get("product_id", ""),
            current_stock=cur_stock,
            delta=delta,
            reason=params.get("reason", "")
        ).to_dict()

    elif action in ["acquire_wholesale_stock", "wholesale_spend", "spend_treasury"]:
        cost = float(params.get("cost", 0.0))
        balance = float(params.get("bank_balance", 0.0))
        reserve = float(params.get("reserve", MIN_TREASURY_RESERVE))
        return policy_engine.validate_wholesale_spend(
            cost=cost,
            bank_balance=balance,
            reserve=reserve,
            actor=actor
        ).to_dict()

    elif action in ["negotiate_salary", "update_salary", "set_ceo_salary"]:
        target_agent = str(params.get("agent_name", ""))
        proposed_sal = float(params.get("proposed_salary") or params.get("new_salary", 0.0))
        return policy_engine.validate_salary_modification(
            agent_name=target_agent,
            proposed_salary=proposed_sal,
            actor=actor
        ).to_dict()

    # If action is permitted by RBAC and has no further specific constraints
    return PolicyResult(
        allowed=True,
        reason=f"Action '{action}' permitted for '{actor}'.",
        policy="DEFAULT_RBAC_POLICY",
        risk_level="low"
    ).to_dict()
