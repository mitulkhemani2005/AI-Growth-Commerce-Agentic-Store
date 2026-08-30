"""
Unit Tests for Event-Driven Coordination & Task Delegation
"""

import pytest
import asyncio
from backend.events import event_router, create_event, Event, EventType
from backend.agent_tasks import task_manager, AgentTask
from backend.admin_agents import message_bus


@pytest.fixture(autouse=True)
def clean_tasks_and_messages():
    task_manager.clear()
    message_bus.clear_history()
    yield
    task_manager.clear()
    message_bus.clear_history()


@pytest.mark.asyncio
async def test_event_publishing_and_subscription():
    received_events = []

    def handle_low_stock(event: Event):
        received_events.append(event)

    event_router.subscribe(EventType.PRODUCT_LOW_STOCK, handle_low_stock)

    evt = create_event(
        event_type=EventType.PRODUCT_LOW_STOCK,
        source_agent="Inventory Manager Agent",
        target_agent="CEO Agent",
        payload={"sku": "prod_001", "stock_remaining": 2},
        priority="high"
    )

    emit_res = await event_router.emit_event(evt)
    assert emit_res["status"] == "PROCESSED"
    assert len(received_events) == 1
    assert received_events[0].payload["sku"] == "prod_001"
    assert received_events[0].priority == "high"


def test_agent_task_lifecycle():
    # 1. Create task
    task = task_manager.create_task(
        created_by="CEO Agent",
        assigned_to="Price Manager Agent",
        objective="Run 10% promotional campaign on Audio SKUs",
        priority="high",
        constraints=["Preserve minimum 15% margin"]
    )
    assert task.status == "pending"
    assert task.assigned_to == "Price Manager Agent"

    # 2. Query pending tasks
    pending_tasks = task_manager.get_tasks(assigned_to="Price Manager Agent", status="pending")
    assert len(pending_tasks) == 1
    assert pending_tasks[0]["task_id"] == task.task_id

    # 3. Claim task
    claimed = task_manager.claim_task(task.task_id, "Price Manager Agent")
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.claimed_at is not None

    # 4. Complete task
    completed = task_manager.complete_task(task.task_id, result={"skus_discounted": 4, "avg_margin": "28%"})
    assert completed is not None
    assert completed.status == "completed"
    assert completed.result["skus_discounted"] == 4


def test_message_bus_event_integration():
    # Publish on message bus
    msg = message_bus.publish(
        from_agent="Order Management Agent",
        to_agent="Finance Manager Agent",
        subject="REFUND_REQUEST",
        payload={"order_id": "ORD-1234", "total": 450.0},
        priority="high"
    )
    assert msg["subject"] == "REFUND_REQUEST"
    assert msg["from"] == "Order Management Agent"

    # Peek inbox
    inbox = message_bus.peek_inbox("Finance Manager Agent")
    assert len(inbox) == 1
    assert inbox[0]["payload"]["order_id"] == "ORD-1234"

    # Read inbox marks messages read
    read_msgs = message_bus.get_inbox("Finance Manager Agent", mark_read=True)
    assert len(read_msgs) == 1

    # Second peek should be empty
    inbox_after = message_bus.peek_inbox("Finance Manager Agent")
    assert len(inbox_after) == 0
