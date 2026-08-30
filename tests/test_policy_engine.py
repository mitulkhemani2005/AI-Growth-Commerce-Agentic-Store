"""
Unit Tests for Policy Engine — Deterministic Business Rules & Safety Validation
"""

import pytest
from datetime import datetime, timezone, timedelta
from backend.policy_engine import policy_engine, validate_policy, PolicyResult


def test_price_floor_enforcement():
    # Price below base_price should be REJECTED
    res = policy_engine.validate_price_change(
        product_id="prod_001",
        current_price=150.0,
        proposed_price=90.0,
        base_price=100.0,
        actor="Price Manager Agent"
    )
    assert res.allowed is False
    assert "BASE_PRICE floor" in res.reason


def test_price_minimum_margin_enforcement():
    # Margin (105 - 100) / 105 = 4.76% (< 15%) should be REJECTED
    res = policy_engine.validate_price_change(
        product_id="prod_001",
        current_price=120.0,
        proposed_price=105.0,
        base_price=100.0,
        actor="Price Manager Agent"
    )
    assert res.allowed is False
    assert "margin" in res.reason.lower()


def test_price_max_delta_enforcement():
    # Price increase from 100 to 140 is 40% delta (> 25% max) -> REJECTED for autonomous agent
    res = policy_engine.validate_price_change(
        product_id="prod_001",
        current_price=100.0,
        proposed_price=140.0,
        base_price=50.0,
        actor="Price Manager Agent"
    )
    assert res.allowed is False
    assert "volatility" in res.policy.lower() or "delta" in res.reason.lower()


def test_price_valid_change():
    # Price from 100 to 120 (20% increase, base is 50 -> margin is (120-50)/120 = 58.3%) -> ALLOWED
    res = policy_engine.validate_price_change(
        product_id="prod_001",
        current_price=100.0,
        proposed_price=120.0,
        base_price=50.0,
        actor="Price Manager Agent"
    )
    assert res.allowed is True


def test_refund_eligibility_within_24h_non_shipped():
    now_iso = datetime.now(timezone.utc).isoformat()
    order = {
        "order_id": "ORD-999",
        "status": "Confirmed",
        "created_at": now_iso,
        "total": 500.0
    }
    res = policy_engine.validate_refund_eligibility(order, actor="Finance Manager Agent")
    assert res.allowed is True


def test_refund_eligibility_exceeded_24h():
    old_dt = (datetime.now(timezone.utc) - timedelta(hours=26)).isoformat()
    order = {
        "order_id": "ORD-998",
        "status": "Confirmed",
        "created_at": old_dt,
        "total": 500.0
    }
    res = policy_engine.validate_refund_eligibility(order, actor="Finance Manager Agent")
    assert res.allowed is False
    assert "24-hour" in res.reason


def test_refund_eligibility_shipped_delivered_rejected():
    now_iso = datetime.now(timezone.utc).isoformat()
    order_shipped = {"order_id": "ORD-997", "status": "Shipped", "created_at": now_iso, "total": 500.0}
    res_shipped = policy_engine.validate_refund_eligibility(order_shipped, actor="Finance Manager Agent")
    assert res_shipped.allowed is False
    assert "non-refundable" in res_shipped.reason.lower()

    order_delivered = {"order_id": "ORD-996", "status": "Delivered", "created_at": now_iso, "total": 500.0}
    res_delivered = policy_engine.validate_refund_eligibility(order_delivered, actor="Finance Manager Agent")
    assert res_delivered.allowed is False


def test_refund_force_override_restricted_to_owner():
    now_iso = datetime.now(timezone.utc).isoformat()
    order = {"order_id": "ORD-995", "status": "Delivered", "created_at": now_iso, "total": 500.0}
    
    # CEO cannot force override
    res_ceo = policy_engine.validate_refund_eligibility(order, actor="CEO Agent", force_override=True)
    assert res_ceo.allowed is False
    assert "restricted exclusively to Store Owner" in res_ceo.reason

    # Store Owner can force override
    res_owner = policy_engine.validate_refund_eligibility(order, actor="Store Owner", force_override=True)
    assert res_owner.allowed is True


def test_order_state_transitions():
    # Valid transitions
    assert policy_engine.validate_order_state_transition("Pending", "Confirmed").allowed is True
    assert policy_engine.validate_order_state_transition("Confirmed", "Dispatched").allowed is True
    assert policy_engine.validate_order_state_transition("Dispatched", "Shipped").allowed is True
    assert policy_engine.validate_order_state_transition("Shipped", "Delivered").allowed is True
    assert policy_engine.validate_order_state_transition("Confirmed", "Cancelled").allowed is True

    # Invalid transitions
    assert policy_engine.validate_order_state_transition("Pending", "Delivered").allowed is False
    assert policy_engine.validate_order_state_transition("Delivered", "Pending").allowed is False
    assert policy_engine.validate_order_state_transition("Refunded", "Shipped").allowed is False


def test_inventory_non_negative_mutation():
    # 5 stock, deduct 2 -> 3 >= 0 (Allowed)
    assert policy_engine.validate_inventory_mutation("SKU1", 5, -2).allowed is True
    # 5 stock, deduct 6 -> -1 < 0 (Rejected)
    assert policy_engine.validate_inventory_mutation("SKU1", 5, -6).allowed is False


def test_treasury_wholesale_spend_reserve_check():
    # Balance 500, cost 300, reserve 100 -> Remaining 200 >= 100 (Allowed)
    assert policy_engine.validate_wholesale_spend(cost=300.0, bank_balance=500.0, reserve=100.0).allowed is True
    # Balance 350, cost 300, reserve 100 -> Remaining 50 < 100 (Rejected)
    assert policy_engine.validate_wholesale_spend(cost=300.0, bank_balance=350.0, reserve=100.0).allowed is False


def test_salary_modification_rules():
    # CEO salary modified by CEO -> Rejected
    assert policy_engine.validate_salary_modification("CEO Agent", 600.0, actor="CEO Agent").allowed is False
    # CEO salary modified by Store Owner -> Allowed
    assert policy_engine.validate_salary_modification("CEO Agent", 600.0, actor="Store Owner").allowed is True
    # Specialist salary below ₹50 floor -> Rejected
    assert policy_engine.validate_salary_modification("Price Manager Agent", 30.0, actor="CEO Agent").allowed is False
    # Specialist salary >= ₹50 -> Allowed
    assert policy_engine.validate_salary_modification("Price Manager Agent", 75.0, actor="CEO Agent").allowed is True


def test_rbac_authorization():
    # Finance can process refunds
    assert policy_engine.validate_authorization("Finance Manager Agent", "process_refund").allowed is True
    # Nova cannot process refunds directly (must route)
    assert policy_engine.validate_authorization("Customer AI (Nova)", "process_refund").allowed is False
    # CEO cannot mutate prices directly without delegation
    assert policy_engine.validate_authorization("CEO Agent", "set_approved_price").allowed is False
    # Store Owner has universal access
    assert policy_engine.validate_authorization("Store Owner", "anything").allowed is True
