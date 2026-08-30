"""
Unit Tests for Idempotency System — Safe Mutation & Deduplication
"""

import pytest
import asyncio
from backend.idempotency import idempotency_manager, execute_idempotent_operation


@pytest.fixture(autouse=True)
def clean_idempotency_records():
    idempotency_manager.clear()
    yield
    idempotency_manager.clear()


@pytest.mark.asyncio
async def test_idempotent_execution_success_caching():
    call_count = 0

    async def mock_operation(amount: float):
        nonlocal call_count
        call_count += 1
        return {"success": True, "disbursed": amount, "call_count": call_count}

    op_id = "test_payroll_001"

    # First call
    res1 = await execute_idempotent_operation(op_id, "PAYROLL", "CEO Agent", mock_operation, amount=500.0)
    assert res1.get("success") is True
    assert res1.get("disbursed") == 500.0
    assert call_count == 1

    # Second call (exact same operation ID) -> Should NOT execute callable again, but return cached result
    res2 = await execute_idempotent_operation(op_id, "PAYROLL", "CEO Agent", mock_operation, amount=500.0)
    assert res2.get("success") is True
    assert res2.get("idempotent_replay") is True
    assert res2.get("cached_result", {}).get("disbursed") == 500.0
    assert call_count == 1  # Callable was NOT executed a second time!


@pytest.mark.asyncio
async def test_idempotent_execution_failure_retry():
    call_count = 0

    async def mock_failing_operation():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"success": False, "error": "Gateway temporary timeout"}
        return {"success": True, "data": "Settled on retry"}

    op_id = "test_retry_op_001"

    # First attempt fails
    res1 = await execute_idempotent_operation(op_id, "PAYMENT", "Finance Manager Agent", mock_failing_operation)
    assert res1.get("success") is False
    assert call_count == 1

    # Second attempt allowed to retry because first failed
    res2 = await execute_idempotent_operation(op_id, "PAYMENT", "Finance Manager Agent", mock_failing_operation)
    assert res2.get("success") is True
    assert call_count == 2
    assert res2.get("data") == "Settled on retry"


def test_idempotency_manager_start_and_complete():
    op_id = "manual_sync_001"
    acq1, ex1 = idempotency_manager.start_operation(op_id, "RESTOCK", "Inventory Manager Agent")
    assert acq1 is True
    assert ex1 is None

    # Completing
    idempotency_manager.complete_operation(op_id, {"units": 10})

    # Checking record
    rec = idempotency_manager.check(op_id)
    assert rec is not None
    assert rec["status"] == "SUCCESS"
    assert rec["result"] == {"units": 10}

    # Subsequent start fails acquisition
    acq2, ex2 = idempotency_manager.start_operation(op_id, "RESTOCK", "Inventory Manager Agent")
    assert acq2 is False
    assert ex2["status"] == "SUCCESS"
