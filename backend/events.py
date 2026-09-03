"""
Event System — Formal Event Taxonomy & Event-Driven Routing
============================================================
Defines structured events, standardized event types, event publishing,
and asynchronous event routing across all autonomous agents.
"""

import json
import uuid
import threading
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable, Awaitable, Set
import inspect


# =====================================================================
# FORMAL EVENT TAXONOMY
# =====================================================================

class EventType:
    # Inventory & Demand
    PRODUCT_LOW_STOCK = "PRODUCT_LOW_STOCK"
    DEMAND_SPIKE = "DEMAND_SPIKE"
    DEMAND_DROP = "DEMAND_DROP"
    RESTOCK_REQUESTED = "RESTOCK_REQUESTED"
    RESTOCK_APPROVED = "RESTOCK_APPROVED"
    RESTOCK_REJECTED = "RESTOCK_REJECTED"
    INVENTORY_RESTOCKED = "INVENTORY_RESTOCKED"
    INVENTORY_RECONCILED = "INVENTORY_RECONCILED"

    # Pricing & Margin
    PRICE_CHANGE_REQUESTED = "PRICE_CHANGE_REQUESTED"
    PRICE_CHANGED = "PRICE_CHANGED"
    PRICE_POLICY_VIOLATION = "PRICE_POLICY_VIOLATION"
    PROMOTION_CREATED = "PROMOTION_CREATED"

    # Order Lifecycle
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    ORDER_DISPATCHED = "ORDER_DISPATCHED"
    ORDER_SHIPPED = "ORDER_SHIPPED"
    ORDER_DELIVERED = "ORDER_DELIVERED"
    ORDER_DELAYED = "ORDER_DELAYED"
    ORDER_SLA_RISK = "ORDER_SLA_RISK"
    ORDER_CANCELLED = "ORDER_CANCELLED"

    # Payments & Treasury
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_RECONCILIATION_ERROR = "PAYMENT_RECONCILIATION_ERROR"
    PAYMENT_RECONCILED = "PAYMENT_RECONCILED"
    TREASURY_DEPOSIT = "TREASURY_DEPOSIT"
    TREASURY_WITHDRAWAL = "TREASURY_WITHDRAWAL"
    SALARY_PAID = "SALARY_PAID"

    # Refunds
    REFUND_REQUESTED = "REFUND_REQUESTED"
    REFUND_APPROVED = "REFUND_APPROVED"
    REFUND_REJECTED = "REFUND_REJECTED"
    REFUND_COMPLETED = "REFUND_COMPLETED"

    # Customer Sentiment & Quality
    LOW_RATING_DETECTED = "LOW_RATING_DETECTED"
    PRODUCT_QUALITY_ALERT = "PRODUCT_QUALITY_ALERT"
    REVIEW_SUBMITTED = "REVIEW_SUBMITTED"

    # Operational Anomaly & Risk
    BUSINESS_ANOMALY_DETECTED = "BUSINESS_ANOMALY_DETECTED"
    BUSINESS_RISK_DETECTED = "BUSINESS_RISK_DETECTED"
    INVARIANT_VIOLATION_DETECTED = "INVARIANT_VIOLATION_DETECTED"

    # Tasks & Directives
    AGENT_TASK_CREATED = "AGENT_TASK_CREATED"
    AGENT_TASK_CLAIMED = "AGENT_TASK_CLAIMED"
    AGENT_TASK_COMPLETED = "AGENT_TASK_COMPLETED"
    AGENT_TASK_FAILED = "AGENT_TASK_FAILED"
    CEO_DIRECTIVE = "CEO_DIRECTIVE"
    OWNER_DIRECTIVE = "OWNER_DIRECTIVE"


@dataclass
class Event:
    """Standardized event object for inter-agent asynchronous coordination."""
    event_type: str
    source_agent: str
    target_agent: str = "ALL_AGENTS"
    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:10]}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    priority: str = "normal"  # low, normal, high, critical
    correlation_id: str = field(default_factory=lambda: f"corr_{uuid.uuid4().hex[:8]}")
    operation_id: Optional[str] = None
    requires_ack: bool = False
    status: str = "PENDING"  # PENDING, PROCESSED, FAILED
    retry_count: int = 0
    acknowledged_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        fields_set = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in fields_set}
        return cls(**filtered)


# =====================================================================
# EVENT ROUTER & SUBSCRIPTION MANAGER
# =====================================================================

class EventRouter:
    """Manages event subscriptions, asynchronous dispatch, and dead-letter queues."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Event], Any]]] = {}
        self._agent_subscribers: Dict[str, List[Callable[[Event], Any]]] = {}
        self._dead_letter_queue: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, handler: Callable[[Event], Any]):
        """Subscribe a handler to a specific event type."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    def subscribe_agent(self, agent_name: str, handler: Callable[[Event], Any]):
        """Subscribe an agent to receive all events addressed to it or to ALL_AGENTS."""
        with self._lock:
            if agent_name not in self._agent_subscribers:
                self._agent_subscribers[agent_name] = []
            if handler not in self._agent_subscribers[agent_name]:
                self._agent_subscribers[agent_name].append(handler)

    async def emit_event(self, event: Event) -> Dict[str, Any]:
        """
        Dispatches an event asynchronously to all subscribed handlers.
        """
        handlers_to_call = []
        with self._lock:
            # 1. Type subscribers
            if event.event_type in self._subscribers:
                handlers_to_call.extend(self._subscribers[event.event_type])
            # 2. Target agent subscribers
            if event.target_agent == "ALL_AGENTS":
                for ag, h_list in self._agent_subscribers.items():
                    if ag != event.source_agent:
                        handlers_to_call.extend(h_list)
            elif event.target_agent in self._agent_subscribers:
                handlers_to_call.extend(self._agent_subscribers[event.target_agent])

        # Remove duplicates while preserving order
        unique_handlers = list(dict.fromkeys(handlers_to_call))
        results = []
        errors = []

        for h in unique_handlers:
            try:
                if inspect.iscoroutinefunction(h):
                    res = await h(event)
                else:
                    res = h(event)
                results.append(res)
            except Exception as e:
                err_str = str(e)
                errors.append(err_str)
                event.error = err_str

        if errors:
            event.status = "FAILED"
            with self._lock:
                self._dead_letter_queue.append(event.to_dict())
        else:
            event.status = "PROCESSED"
            event.acknowledged_at = datetime.now(timezone.utc).isoformat()

        return {
            "event_id": event.event_id,
            "status": event.status,
            "handlers_executed": len(unique_handlers),
            "errors": errors
        }

    def get_dead_letters(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._dead_letter_queue[-limit:])


# Global Event Router Singleton
event_router = EventRouter()


def dispatch_agent_event_message(event: Event):
    """
    Translates store lifecycle events into rich inter-agent messages between specialist agents.
    RULE: The CEO Agent is EXPLICITLY EXCLUDED from sending event-level messages.
    """
    from backend.admin_agents import message_bus

    # If the source is CEO Agent, do not broadcast event-level messaging spam
    if event.source_agent and "ceo" in event.source_agent.lower():
        return

    etype = event.event_type
    p = event.payload or {}

    if etype == EventType.ORDER_CONFIRMED:
        oid = p.get("order_id", "Unknown")
        total = float(p.get("total", 0.0))
        items_summary = p.get("items_summary") or f"{len(p.get('items', []))} item(s)"
        # 1. Order Manager notifies Dispatcher Agent
        message_bus.publish(
            from_agent="Order Management Agent",
            to_agent="Dispatcher Agent",
            subject="ORDER_CONFIRMED",
            payload={
                "order_id": oid,
                "total": total,
                "items_summary": items_summary,
                "shipping_address": p.get("shipping_address", ""),
                "action_required": "Assign express courier tracking (TRK-XXXXX) and prepare package dispatch."
            },
            priority="high",
            correlation_id=event.correlation_id
        )
        # 2. Order Manager notifies Finance Manager Agent
        message_bus.publish(
            from_agent="Order Management Agent",
            to_agent="Finance Manager Agent",
            subject="ORDER_PAYMENT_CAPTURED",
            payload={
                "order_id": oid,
                "total": total,
                "payment_method": p.get("payment_method", "Razorpay Gateway"),
                "action_required": "Verify settlement and reconcile treasury ledger."
            },
            priority="normal",
            correlation_id=event.correlation_id
        )

    elif etype == EventType.ORDER_DISPATCHED:
        oid = p.get("order_id", "Unknown")
        trk = p.get("tracking_number", "TRK-Pending")
        carrier = p.get("carrier", "BlueDart Express")
        # Dispatcher notifies Order Manager
        message_bus.publish(
            from_agent="Dispatcher Agent",
            to_agent="Order Management Agent",
            subject="ORDER_DISPATCHED",
            payload={
                "order_id": oid,
                "tracking_number": trk,
                "carrier": carrier,
                "eta": p.get("eta", "2-3 Business Days"),
                "details": f"Parcel handed to {carrier} under tracking #{trk}."
            },
            priority="high",
            correlation_id=event.correlation_id
        )

    elif etype == EventType.ORDER_SHIPPED:
        oid = p.get("order_id", "Unknown")
        message_bus.publish(
            from_agent="Order Management Agent",
            to_agent="Dispatcher Agent",
            subject="ORDER_SHIPPED",
            payload={"order_id": oid, "status": "Shipped", "tracking_number": p.get("tracking_number")},
            priority="normal",
            correlation_id=event.correlation_id
        )

    elif etype == EventType.ORDER_DELIVERED:
        oid = p.get("order_id", "Unknown")
        message_bus.publish(
            from_agent="Order Management Agent",
            to_agent="Review and Feedback Manager",
            subject="ORDER_DELIVERED",
            payload={"order_id": oid, "customer": p.get("customer", ""), "action_required": "Track customer satisfaction and solicit verified review."},
            priority="normal",
            correlation_id=event.correlation_id
        )

    elif etype in [EventType.ORDER_CANCELLED, EventType.REFUND_REQUESTED]:
        oid = p.get("order_id", "Unknown")
        message_bus.publish(
            from_agent="Order Management Agent",
            to_agent="Finance Manager Agent",
            subject="REFUND_REQUEST",
            payload={"order_id": oid, "reason": p.get("reason", "Customer cancellation"), "total": float(p.get("total", 0.0)), "action_required": "Evaluate 24h non-shipped refund policy and disburse funds."},
            priority="high",
            correlation_id=event.correlation_id
        )

    elif etype in [EventType.REFUND_COMPLETED, EventType.REFUND_APPROVED]:
        oid = p.get("order_id", "Unknown")
        amt = float(p.get("amount") or p.get("total", 0.0))
        # Finance notifies Order Manager
        message_bus.publish(
            from_agent="Finance Manager Agent",
            to_agent="Order Management Agent",
            subject="REFUND_COMPLETED",
            payload={"order_id": oid, "amount": amt, "status": "Refunded", "details": f"Refund of ₹{amt:,.2f} disbursed to customer."},
            priority="high",
            correlation_id=event.correlation_id
        )
        # Finance notifies Inventory Manager to restock
        message_bus.publish(
            from_agent="Finance Manager Agent",
            to_agent="Inventory Manager Agent",
            subject="RESTOCK_CANCELLED_ITEMS",
            payload={"order_id": oid, "items": p.get("items", []), "action_required": "Restock returned items into warehouse inventory."},
            priority="normal",
            correlation_id=event.correlation_id
        )

    elif etype == EventType.PAYMENT_RECEIVED:
        oid = p.get("order_id", "Unknown")
        amt = float(p.get("amount", 0.0))
        pid = p.get("payment_id", "")
        # Finance notifies Order Manager
        message_bus.publish(
            from_agent="Finance Manager Agent",
            to_agent="Order Management Agent",
            subject="PAYMENT_RECEIVED",
            payload={"order_id": oid, "payment_id": pid, "amount": amt, "method": p.get("payment_method", "Razorpay Gateway")},
            priority="normal",
            correlation_id=event.correlation_id
        )

    elif etype == EventType.PRODUCT_LOW_STOCK:
        pname = p.get("product_name") or p.get("PRODUCT_NAME") or p.get("sku", "Item")
        stock = p.get("stock_remaining", 0)
        pid = p.get("product_id") or p.get("id", "")
        # Inventory Manager notifies Price Manager
        message_bus.publish(
            from_agent="Inventory Manager Agent",
            to_agent="Price Manager Agent",
            subject="LOW_STOCK_SCARCITY_ALERT",
            payload={"product_id": pid, "product_name": pname, "stock_remaining": stock, "action_required": "Evaluate margin surge for remaining stock."},
            priority="high",
            correlation_id=event.correlation_id
        )

    elif etype in [EventType.INVENTORY_RESTOCKED, EventType.RESTOCK_APPROVED]:
        pname = p.get("product_name") or p.get("sku", "Item")
        qty = p.get("quantity", 0)
        pid = p.get("product_id", "")
        cost = float(p.get("total_cost", 0.0))
        # Inventory Manager notifies Price Manager
        message_bus.publish(
            from_agent="Inventory Manager Agent",
            to_agent="Price Manager Agent",
            subject="INVENTORY_RESTOCKED",
            payload={"product_id": pid, "product_name": pname, "quantity_added": qty, "action_required": "Normalize selling price following stock replenishment."},
            priority="normal",
            correlation_id=event.correlation_id
        )
        if cost > 0:
            # Inventory Manager notifies Finance Manager
            message_bus.publish(
                from_agent="Inventory Manager Agent",
                to_agent="Finance Manager Agent",
                subject="STOCK_PURCHASE_COMPLETED",
                payload={"product_id": pid, "product_name": pname, "quantity": qty, "cost": cost},
                priority="normal",
                correlation_id=event.correlation_id
            )

    elif etype == EventType.PRICE_CHANGED:
        pname = p.get("product_name", "Item")
        new_p = float(p.get("new_price", 0.0))
        old_p = float(p.get("old_price", 0.0))
        # Price Manager notifies Inventory Manager
        message_bus.publish(
            from_agent="Price Manager Agent",
            to_agent="Inventory Manager Agent",
            subject="PRICE_ADJUSTED",
            payload={"product_id": p.get("product_id", ""), "product_name": pname, "old_price": old_p, "new_price": new_p, "reason": p.get("reason", "Dynamic pricing recalibration")},
            priority="normal",
            correlation_id=event.correlation_id
        )

    elif etype == EventType.REVIEW_SUBMITTED:
        pname = p.get("product_name", "Product")
        rating = p.get("rating", 5)
        # Review Manager notifies Price Manager
        message_bus.publish(
            from_agent="Review and Feedback Manager",
            to_agent="Price Manager Agent",
            subject="REVIEW_SUBMITTED",
            payload={"product_id": p.get("product_id", ""), "product_name": pname, "rating": rating, "review": str(p.get("review_text", ""))[:100]},
            priority="normal",
            correlation_id=event.correlation_id
        )


def create_event(
    event_type: str,
    source_agent: str,
    target_agent: str = "ALL_AGENTS",
    payload: Optional[Dict[str, Any]] = None,
    priority: str = "normal",
    correlation_id: Optional[str] = None,
    operation_id: Optional[str] = None,
    requires_ack: bool = False
) -> Event:
    """Helper to instantiate a structured event."""
    return Event(
        event_type=event_type,
        source_agent=source_agent,
        target_agent=target_agent,
        payload=payload or {},
        priority=priority,
        correlation_id=correlation_id or f"corr_{uuid.uuid4().hex[:8]}",
        operation_id=operation_id,
        requires_ack=requires_ack
    )


def emit_store_event(
    event_type: str,
    source_agent: str,
    payload: Optional[Dict[str, Any]] = None,
    priority: str = "normal"
) -> Event:
    """
    Synchronous and asynchronous safe dispatcher:
    1. Creates a structured event.
    2. Immediately dispatches the inter-agent peer message (excluding CEO).
    3. Emits on the async event router if an event loop is active.
    """
    evt = create_event(
        event_type=event_type,
        source_agent=source_agent,
        target_agent="ALL_AGENTS",
        payload=payload or {},
        priority=priority
    )
    try:
        dispatch_agent_event_message(evt)
    except Exception as e:
        print(f"[Event Message Dispatch Warning] {e}", flush=True)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(event_router.emit_event(evt))
    except RuntimeError:
        pass
    return evt
