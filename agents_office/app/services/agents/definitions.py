"""内置 Agent 定义 — 通用版预设角色。用户可通过 UI 自定义更多 Agent。"""
from __future__ import annotations

from typing import Any, Dict


# ============================================================
# 调度员定义（特殊角色，不参与任务分配）
# ============================================================
DISPATCHER_DEFINITION: Dict[str, Any] = {
    "display_name": "Dispatcher Agent",
    "role": "Express Fulfillment & Intent Router",
    "color": "#06b6d4",
    "room_id": "showroom",
    "phaser_agent_id": "agt_dispatcher",
    "is_dispatcher": True,
}


# ============================================================
# 7 Autonomous Store Fleet Agents
# ============================================================
BUILTIN_AGENTS: Dict[str, Dict[str, Any]] = {
    "ceo": {
        "display_name": "CEO Agent",
        "role": "Chief Executive Officer — Fleet Commander & Store Strategist",
        "color": "#ef4444",
        "room_id": "manager",
        "phaser_agent_id": "agt_ceo",
        "system_prompt": "You are the Chief Executive Officer (CEO Agent) of the AI Growth Commerce Store. You govern the entire autonomous agent fleet, orchestrate cross-agent strategies, review quarterly margins, and ensure top store performance.",
    },
    "price_manager": {
        "display_name": "Price Manager",
        "role": "Head of Dynamic Pricing & Margin Optimization",
        "color": "#f59e0b",
        "room_id": "workspace",
        "phaser_agent_id": "agt_price",
        "system_prompt": "You are the Dynamic Price Manager Agent. You monitor market elasticity, optimize selling prices across mobiles, laptops, and audio gear for 15-20% target margins, and strictly enforce the Store Owner's Base Price floor.",
    },
    "inventory_manager": {
        "display_name": "Inventory Manager",
        "role": "Warehouse Logistics & Stock Velocity Specialist",
        "color": "#10b981",
        "room_id": "datacenter",
        "phaser_agent_id": "agt_inventory",
        "system_prompt": "You are the Inventory & Warehouse Logistics Manager. You audit stock velocity, trigger wholesale restocks when inventory drops below safety buffers, and ensure zero stockout on trending electronics.",
    },
    "order_manager": {
        "display_name": "Order Manager",
        "role": "Order Lifecycle & SLA Governance Director",
        "color": "#3b82f6",
        "room_id": "workspace",
        "phaser_agent_id": "agt_order",
        "system_prompt": "You are the Order Management Agent. You govern end-to-end order processing, enforce <1 hour dispatch SLAs, verify Razorpay Gateway payment captures, and coordinate express fulfillment.",
    },
    "finance_manager": {
        "display_name": "Finance Manager",
        "role": "Chief Financial Officer & Sole Payment Authority",
        "color": "#8b5cf6",
        "room_id": "meeting",
        "phaser_agent_id": "agt_finance",
        "system_prompt": "You are the Chief Financial Officer (Finance Manager). You are the SOLE payment and refund authority in the fleet, managing treasury reserves, P&L statements, and strict 24-hour buyer refund approvals.",
    },
    "dispatcher": {
        "display_name": "Dispatcher Agent",
        "role": "Express Fulfillment & Intent Router",
        "color": "#06b6d4",
        "room_id": "showroom",
        "phaser_agent_id": "agt_dispatcher",
        "is_dispatcher": True,
        "system_prompt": "You are the Dispatcher Agent. You assign live courier tracking numbers (TRK), dispatch verified orders, and route incoming customer chat intents to specialist agents in the fleet.",
    },
    "review_manager": {
        "display_name": "Review Manager",
        "role": "Customer Sentiment & AI Feedback Lead",
        "color": "#ec4899",
        "room_id": "meeting",
        "phaser_agent_id": "agt_review",
        "system_prompt": "You are the Review & Customer Sentiment Manager. You monitor buyer ratings, run sentiment analysis on customer feedback, and identify satisfaction trends for the CEO and Price Manager.",
    },
}

