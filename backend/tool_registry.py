"""
Tool Registry — Centralized Tool Metadata, RBAC & Risk Classification
======================================================================
Maintains a formal catalog of all tools across Nova, CEO, Price, Inventory,
Order, Dispatcher, Finance, Review, and Buyer Fleet.

Risk Levels:
  - LOW: Search, catalog retrieval, sentiment reading, metric inspection.
  - MEDIUM: Recommendations, forecasts, customer responses, draft allocations.
  - HIGH: Price adjustments, inventory stock mutations, order status transitions, carrier dispatch.
  - CRITICAL: Payment execution, refund processing, treasury disbursals, salary revisions.
    (CRITICAL tools strictly enforce Policy Validation, RBAC Authorization, Idempotency, and Audit Logging).
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from backend.policy_engine import policy_engine, PolicyResult


@dataclass
class ToolDefinition:
    """Metadata schema for a registered agent tool."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    allowed_agents: List[str]
    risk_level: str = "low"  # low, medium, high, critical
    requires_policy: bool = False
    requires_approval: bool = False
    idempotent: bool = False
    emits_events: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "allowed_agents": self.allowed_agents,
            "risk_level": self.risk_level,
            "requires_policy": self.requires_policy,
            "requires_approval": self.requires_approval,
            "idempotent": self.idempotent,
            "emits_events": self.emits_events
        }


class ToolRegistry:
    """Central registry and policy validator for all tools across the business."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register(self, tool_def: ToolDefinition):
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def get_tools_for_agent(self, agent_name: str) -> List[ToolDefinition]:
        """Returns all tools that a specific agent is authorized to use."""
        result = []
        for t in self._tools.values():
            if "*" in t.allowed_agents or any(ag.lower() in agent_name.lower() for ag in t.allowed_agents):
                result.append(t)
        return result

    def get_openai_tool_schemas_for_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """Converts registered tools for an agent into OpenAI/Ollama function calling schema."""
        tools = self.get_tools_for_agent(agent_name)
        schemas = []
        for t in tools:
            schemas.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema
                }
            })
        return schemas

    def validate_tool_access(self, tool_name: str, agent_name: str) -> PolicyResult:
        """Determines if the agent has permissions to call the requested tool."""
        tool = self.get(tool_name)
        if not tool:
            return PolicyResult(
                allowed=False,
                reason=f"Tool '{tool_name}' is not registered in the system.",
                policy="TOOL_NOT_FOUND_POLICY",
                risk_level="high"
            )

        if "*" in tool.allowed_agents or any(ag.lower() in agent_name.lower() for ag in tool.allowed_agents):
            return PolicyResult(
                allowed=True,
                reason=f"Agent '{agent_name}' is authorized to call '{tool_name}' ({tool.risk_level.upper()} risk).",
                policy="TOOL_AUTHORIZATION_POLICY",
                risk_level=tool.risk_level
            )

        return PolicyResult(
            allowed=False,
            reason=f"Agent '{agent_name}' is unauthorized to call tool '{tool_name}'. Allowed agents: {tool.allowed_agents}.",
            policy="TOOL_AUTHORIZATION_POLICY",
            risk_level="critical",
            required_approval="Store Owner" if tool.risk_level == "critical" else "CEO Agent"
        )

    def _register_default_tools(self):
        """Registers all tools with formal risk levels and agent permissions."""

        # ── NOVA (Customer AI) Tools ──
        self.register(ToolDefinition(
            name="purchase_assistant",
            description="End-to-end commerce orchestration: validates stock, reserves cart items, applies eligible promotions, computes total in INR ₹, and prepares instant checkout.",
            input_schema={
                "type": "object",
                "properties": {
                    "products": {"type": "array", "items": {"type": "string"}, "description": "List of product IDs or names"},
                    "quantities": {"type": "array", "items": {"type": "integer"}, "description": "Quantities per product"},
                    "variants": {"type": "array", "items": {"type": "string"}, "description": "Size or variant options"},
                    "coupon": {"type": ["string", "null"], "description": "Optional discount coupon code"},
                    "delivery_preference": {"type": ["string", "null"], "description": "Standard, Express, or Priority"}
                },
                "required": ["products"]
            },
            allowed_agents=["Customer AI (Nova)", "Store Owner"],
            risk_level="medium",
            requires_policy=True
        ))

        self.register(ToolDefinition(
            name="search_inventory",
            description="Search product catalog by keyword, categories, price range, and in-stock status.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": ["string", "null"]},
                    "product_types": {"type": ["array", "null"], "items": {"type": "string"}},
                    "size": {"type": ["string", "null"]},
                    "min_price": {"type": ["number", "null"]},
                    "max_price": {"type": ["number", "null"]},
                    "in_stock_only": {"type": ["boolean", "null"]}
                }
            },
            allowed_agents=["Customer AI (Nova)", "Store Owner", "AI Buyer Fleet"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="get_product_details",
            description="Retrieve comprehensive product specifications, pricing, stock, size variants, ratings, and AI review summaries.",
            input_schema={
                "type": "object",
                "properties": {
                    "product_name_or_id": {"type": ["string", "null"]},
                    "product_id": {"type": ["string", "null"]},
                    "product_name": {"type": ["string", "null"]}
                }
            },
            allowed_agents=["Customer AI (Nova)", "Store Owner", "Review and Feedback Manager"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="recommend_products",
            description="Generate personalized product recommendations based on preferences, category, or budget.",
            input_schema={
                "type": "object",
                "properties": {
                    "category": {"type": ["string", "null"]},
                    "budget": {"type": ["number", "null"]},
                    "preferences": {"type": ["string", "null"]}
                }
            },
            allowed_agents=["Customer AI (Nova)", "Store Owner"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="compare_products",
            description="Side-by-side comparison of 2 or more products (specs, prices, ratings, advantages).",
            input_schema={
                "type": "object",
                "properties": {
                    "product_ids": {"type": "array", "items": {"type": "string"}, "description": "List of product IDs or names to compare"}
                },
                "required": ["product_ids"]
            },
            allowed_agents=["Customer AI (Nova)", "Store Owner"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="apply_coupon",
            description="Validate and apply promotional coupon code to shopping cart.",
            input_schema={
                "type": "object",
                "properties": {
                    "coupon_code": {"type": "string", "description": "Coupon code to apply (e.g. 'GROWTH10', 'TECH20')"}
                },
                "required": ["coupon_code"]
            },
            allowed_agents=["Customer AI (Nova)", "Store Owner", "AI Buyer Fleet"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="reserve_cart_inventory",
            description="Temporarily reserve inventory stock for items currently in cart.",
            input_schema={"type": "object", "properties": {}},
            allowed_agents=["Customer AI (Nova)", "Store Owner"],
            risk_level="medium"
        ))

        self.register(ToolDefinition(
            name="get_delivery_estimate",
            description="Compute delivery timeframe and carrier estimation for destination and items.",
            input_schema={
                "type": "object",
                "properties": {
                    "shipping_address": {"type": ["string", "null"]}
                }
            },
            allowed_agents=["Customer AI (Nova)", "Store Owner", "Dispatcher Agent"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="reorder_previous_purchase",
            description="Re-add items from a past completed order into cart for fast 1-click reorder.",
            input_schema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Past order ID to reorder"}
                },
                "required": ["order_id"]
            },
            allowed_agents=["Customer AI (Nova)", "Store Owner"],
            risk_level="medium"
        ))

        self.register(ToolDefinition(
            name="create_support_request",
            description="Create a formal customer support ticket / exception request routed to Order or Review manager.",
            input_schema={
                "type": "object",
                "properties": {
                    "issue_type": {"type": "string", "description": "Type: delivery_delay, damaged_item, inquiry, spec_question"},
                    "message": {"type": "string", "description": "Customer message"},
                    "order_id": {"type": ["string", "null"], "description": "Related order ID"}
                },
                "required": ["issue_type", "message"]
            },
            allowed_agents=["Customer AI (Nova)", "Store Owner"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="trigger_razorpay_checkout",
            description="Open secure Razorpay Checkout popup modal on user screen.",
            input_schema={"type": "object", "properties": {}},
            allowed_agents=["Customer AI (Nova)", "Store Owner"],
            risk_level="high",
            emits_events=["PAYMENT_RECEIVED"]
        ))

        # ── CEO Tools ──
        self.register(ToolDefinition(
            name="delegate_task",
            description="High-level orchestration: delegate strategic tasks and objectives to specialist agents with priorities and constraints.",
            input_schema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Target specialist agent name"},
                    "objective": {"type": "string", "description": "Clear business objective to accomplish"},
                    "priority": {"type": "string", "description": "Priority: low, normal, high, critical"},
                    "constraints": {"type": "array", "items": {"type": "string"}, "description": "Operational constraints"},
                    "deadline": {"type": ["string", "null"], "description": "Optional deadline"}
                },
                "required": ["agent", "objective"]
            },
            allowed_agents=["CEO Agent", "Store Owner"],
            risk_level="medium",
            emits_events=["AGENT_TASK_CREATED"]
        ))

        self.register(ToolDefinition(
            name="query_agent",
            description="Consult a specialist agent for deep domain evaluation, status, or recommendations.",
            input_schema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent name to consult"},
                    "question": {"type": "string", "description": "Domain inquiry or question"},
                    "context": {"type": ["object", "null"], "description": "Optional context"}
                },
                "required": ["agent", "question"]
            },
            allowed_agents=["CEO Agent", "Store Owner"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="simulate_business_decision",
            description="Simulate the business impact of a strategic decision (e.g. price change, marketing campaign, wholesale restock) on revenue, gross margin, inventory turnover, treasury, and risk score.",
            input_schema={
                "type": "object",
                "properties": {
                    "scenario": {"type": "string", "description": "Scenario description (e.g. 'Reduce laptop prices by 5%', 'Restock 50 units of iPhone')"},
                    "assumptions": {"type": ["object", "null"], "description": "Optional key assumptions"}
                },
                "required": ["scenario"]
            },
            allowed_agents=["CEO Agent", "Store Owner"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="get_business_forecast",
            description="Get forecasted revenue, demand velocity, cashflow, and inventory runway.",
            input_schema={
                "type": "object",
                "properties": {
                    "timeframe_days": {"type": "integer", "description": "Forecast horizon (default 7 days)"}
                }
            },
            allowed_agents=["CEO Agent", "Store Owner"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="get_anomaly_report",
            description="Inspect all business, inventory, pricing, and payment anomalies across the fleet.",
            input_schema={"type": "object", "properties": {}},
            allowed_agents=["CEO Agent", "Store Owner"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="escalate_to_owner",
            description="Deterministic escalation of high-risk conflicts, treasury breaches, or critical anomalies to Store Owner.",
            input_schema={
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Reason for owner escalation"},
                    "risk": {"type": "string", "description": "Risk level: medium, high, critical"},
                    "proposed_action": {"type": "string", "description": "Proposed executive action"},
                    "context": {"type": ["object", "null"], "description": "Supporting telemetry context"}
                },
                "required": ["reason", "risk", "proposed_action"]
            },
            allowed_agents=["CEO Agent", "Finance Manager Agent", "Store Owner"],
            risk_level="medium",
            emits_events=["OWNER_DIRECTIVE"]
        ))

        # ── Price Manager Tools ──
        self.register(ToolDefinition(
            name="estimate_optimal_price",
            description="Calculate optimal selling price based on demand elasticity, inventory scarcity, base price floor, and target margin.",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID"}
                },
                "required": ["product_id"]
            },
            allowed_agents=["Price Manager Agent", "Store Owner"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="set_approved_price",
            description="Set product price with mandatory deterministic policy validation against BASE_PRICE floor and margin rules.",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID"},
                    "recommended_price": {"type": "number", "description": "New price in INR ₹"},
                    "reason": {"type": "string", "description": "Business rationale"},
                    "confidence": {"type": ["number", "null"], "description": "Decision confidence (0.0 - 1.0)"}
                },
                "required": ["product_id", "recommended_price", "reason"]
            },
            allowed_agents=["Price Manager Agent", "Store Owner"],
            risk_level="high",
            requires_policy=True,
            emits_events=["PRICE_CHANGED"]
        ))

        # ── Inventory Manager Tools ──
        self.register(ToolDefinition(
            name="calculate_reorder_point",
            description="Calculate optimal inventory reorder points and safety stock based on sales velocity and lead time.",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID"}
                },
                "required": ["product_id"]
            },
            allowed_agents=["Inventory Manager Agent", "Store Owner"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="create_purchase_request",
            description="Create formal wholesale restock request submitted to CEO Agent for treasury approval.",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID"},
                    "quantity": {"type": "integer", "description": "Requested replenishment quantity"},
                    "reason": {"type": "string", "description": "Restock justification"}
                },
                "required": ["product_id", "quantity"]
            },
            allowed_agents=["Inventory Manager Agent", "Store Owner"],
            risk_level="high",
            requires_policy=True,
            emits_events=["RESTOCK_REQUESTED"]
        ))

        self.register(ToolDefinition(
            name="reconcile_inventory",
            description="Reconcile warehouse inventory with audit reason and evidence (replaces arbitrary stock creation).",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID"},
                    "counted_quantity": {"type": "integer", "description": "Actual physical count"},
                    "reason": {"type": "string", "description": "Audit reconciliation reason"},
                    "evidence": {"type": ["string", "null"], "description": "Optional audit log or evidence note"}
                },
                "required": ["product_id", "counted_quantity", "reason"]
            },
            allowed_agents=["Inventory Manager Agent", "Store Owner"],
            risk_level="high",
            requires_policy=True,
            idempotent=True,
            emits_events=["INVENTORY_RECONCILED"]
        ))

        # ── Order Management Tools ──
        self.register(ToolDefinition(
            name="advance_order",
            description="Advance order through state lifecycle with strict state machine validation.",
            input_schema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID (e.g. 'ORD-1001')"},
                    "target_state": {"type": "string", "description": "Target status (Confirmed, Dispatched, Shipped, Delivered, Cancelled)"},
                    "reason": {"type": ["string", "null"], "description": "Status transition reason"}
                },
                "required": ["order_id", "target_state"]
            },
            allowed_agents=["Order Management Agent", "Store Owner"],
            risk_level="high",
            requires_policy=True,
            idempotent=True
        ))

        self.register(ToolDefinition(
            name="predict_sla_breach",
            description="Predict pending order SLA breaches and identify delivery bottleneck risks.",
            input_schema={
                "type": "object",
                "properties": {
                    "order_id": {"type": ["string", "null"], "description": "Optional specific order ID"}
                }
            },
            allowed_agents=["Order Management Agent", "Store Owner"],
            risk_level="low"
        ))

        # ── Dispatcher Tools ──
        self.register(ToolDefinition(
            name="select_best_carrier",
            description="Evaluate carriers based on cost, ETA, delivery reliability score, and destination.",
            input_schema={
                "type": "object",
                "properties": {
                    "destination": {"type": ["string", "null"], "description": "Delivery destination"},
                    "package": {"type": ["string", "null"], "description": "Package category/weight"},
                    "priority": {"type": ["string", "null"], "description": "Priority: standard, express"}
                }
            },
            allowed_agents=["Dispatcher Agent", "Store Owner"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="create_shipping_label",
            description="Generate formal carrier shipping label and tracking identifier (TRK-XXXXX) for confirmed order.",
            input_schema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Confirmed order ID"},
                    "carrier": {"type": ["string", "null"], "description": "Selected carrier"}
                },
                "required": ["order_id"]
            },
            allowed_agents=["Dispatcher Agent", "Store Owner"],
            risk_level="high",
            idempotent=True,
            emits_events=["ORDER_DISPATCHED"]
        ))

        # ── Finance Manager Tools ──
        self.register(ToolDefinition(
            name="process_refund",
            description="Sole Payment Authority: evaluates 24h eligibility, checks idempotency, processes Razorpay refund, deducts from Treasury, and restocks inventory.",
            input_schema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID to refund"},
                    "reason": {"type": "string", "description": "Refund justification"},
                    "operation_id": {"type": ["string", "null"], "description": "Unique operation ID for idempotency"}
                },
                "required": ["order_id", "reason"]
            },
            allowed_agents=["Finance Manager Agent", "Store Owner"],
            risk_level="critical",
            requires_policy=True,
            idempotent=True,
            emits_events=["REFUND_COMPLETED"]
        ))

        self.register(ToolDefinition(
            name="reconcile_payments",
            description="Audit orders vs payment provider vs treasury vs refunds to detect payment discrepancies, orphan records, and balance mismatches.",
            input_schema={"type": "object", "properties": {}},
            allowed_agents=["Finance Manager Agent", "Store Owner"],
            risk_level="low",
            emits_events=["PAYMENT_RECONCILED"]
        ))

        # ── Review & Feedback Tools ──
        self.register(ToolDefinition(
            name="cluster_review_issues",
            description="Cluster customer feedback topics and identify recurring complaints, defects, and satisfaction drivers.",
            input_schema={"type": "object", "properties": {}},
            allowed_agents=["Review and Feedback Manager", "Store Owner"],
            risk_level="low"
        ))

        self.register(ToolDefinition(
            name="create_product_quality_alert",
            description="Generate product quality alert sent to CEO for items with rating trends < 3.0 stars or recurring defect clusters.",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID"},
                    "issue": {"type": "string", "description": "Quality issue description"},
                    "severity": {"type": "string", "description": "low, medium, high, critical"}
                },
                "required": ["product_id", "issue"]
            },
            allowed_agents=["Review and Feedback Manager", "Store Owner"],
            risk_level="medium",
            emits_events=["PRODUCT_QUALITY_ALERT"]
        ))

        # ── Buyer Fleet Tools ──
        self.register(ToolDefinition(
            name="validate_business_invariants",
            description="Continuous Integration / QA: inspects storewide invariants (no negative inventory, no negative treasury, no duplicate refunds, no invalid order states, no prices below BASE_PRICE).",
            input_schema={"type": "object", "properties": {}},
            allowed_agents=["AI Buyer Fleet", "Store Owner", "CEO Agent"],
            risk_level="low"
        ))


# Singleton
tool_registry = ToolRegistry()
