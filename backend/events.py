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
