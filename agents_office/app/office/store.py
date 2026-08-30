"""AgentsOffice 容器层数据操作 -- 100% JSON-Based Pure Storage (无 SQLite / 无 SQL 数据库)。"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models import now_iso

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data"))
JSON_FILE = os.path.join(DATA_DIR, "agents_office.json")
INVENTORY_FILE = os.path.join(DATA_DIR, "inventory.json")

_store_lock = threading.RLock()


def _dt_to_iso(val: Any) -> str:
    """将 datetime 转为 ISO 字符串。"""
    if val is None:
        return now_iso()
    if isinstance(val, str):
        return val
    return val.isoformat()


class OfficeStore:
    """100% 纯 JSON 数据存储 -- 管理 agents, skills, costs, conversations, tasks。"""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.file_path = JSON_FILE
        os.makedirs(DATA_DIR, exist_ok=True)
        self._load_or_seed()

    def _get_default_agents(self) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        return [
            {
                "agent_id": "agt_ceo",
                "name": "CEO Agent",
                "slug": "ceo",
                "description": "Chief Executive Officer — Fleet Commander & Store Strategist",
                "agent_type": "executive",
                "status": "idle",
                "model_config": {"model_name": "ollama/qwen2.5:7b"},
                "metadata": {
                    "display_name": "CEO Agent",
                    "role": "Fleet Commander & Store Strategist",
                    "color": "#ef4444",
                    "room_id": "manager",
                    "phaser_agent_id": "agt_ceo",
                    "sprite_key": "char_01",
                    "is_dispatcher": False,
                },
                "created_at": now,
                "updated_at": now,
                "last_active_at": None,
                "error_message": None,
            },
            {
                "agent_id": "agt_price",
                "name": "Price Manager Agent",
                "slug": "price_manager",
                "description": "Head of Dynamic Pricing & Margin Optimization",
                "agent_type": "pricing",
                "status": "idle",
                "model_config": {"model_name": "ollama/qwen2.5:7b"},
                "metadata": {
                    "display_name": "Price Manager",
                    "role": "Head of Dynamic Pricing & Margins",
                    "color": "#f59e0b",
                    "room_id": "workspace",
                    "phaser_agent_id": "agt_price",
                    "sprite_key": "char_02",
                    "is_dispatcher": False,
                },
                "created_at": now,
                "updated_at": now,
                "last_active_at": None,
                "error_message": None,
            },
            {
                "agent_id": "agt_inventory",
                "name": "Inventory Manager Agent",
                "slug": "inventory_manager",
                "description": "Warehouse Logistics & Stock Velocity Specialist",
                "agent_type": "logistics",
                "status": "idle",
                "model_config": {"model_name": "ollama/qwen2.5:7b"},
                "metadata": {
                    "display_name": "Inventory Manager",
                    "role": "Warehouse Logistics & Restocking",
                    "color": "#10b981",
                    "room_id": "datacenter",
                    "phaser_agent_id": "agt_inventory",
                    "sprite_key": "char_03",
                    "is_dispatcher": False,
                },
                "created_at": now,
                "updated_at": now,
                "last_active_at": None,
                "error_message": None,
            },
            {
                "agent_id": "agt_order",
                "name": "Order Management Agent",
                "slug": "order_manager",
                "description": "Order Lifecycle & SLA Governance Director",
                "agent_type": "operations",
                "status": "idle",
                "model_config": {"model_name": "ollama/qwen2.5:7b"},
                "metadata": {
                    "display_name": "Order Manager",
                    "role": "Order Lifecycle & SLA Governance",
                    "color": "#3b82f6",
                    "room_id": "workspace",
                    "phaser_agent_id": "agt_order",
                    "sprite_key": "char_04",
                    "is_dispatcher": False,
                },
                "created_at": now,
                "updated_at": now,
                "last_active_at": None,
                "error_message": None,
            },
            {
                "agent_id": "agt_finance",
                "name": "Finance Manager Agent",
                "slug": "finance_manager",
                "description": "Chief Financial Officer & Sole Payment Authority",
                "agent_type": "finance",
                "status": "idle",
                "model_config": {"model_name": "ollama/qwen2.5:7b"},
                "metadata": {
                    "display_name": "Finance Manager",
                    "role": "Chief Financial Officer & Refunds",
                    "color": "#8b5cf6",
                    "room_id": "meeting",
                    "phaser_agent_id": "agt_finance",
                    "sprite_key": "char_05",
                    "is_dispatcher": False,
                },
                "created_at": now,
                "updated_at": now,
                "last_active_at": None,
                "error_message": None,
            },
            {
                "agent_id": "agt_dispatcher",
                "name": "Dispatcher Agent",
                "slug": "dispatcher",
                "description": "Express Fulfillment & Tracking Controller",
                "agent_type": "dispatcher",
                "status": "idle",
                "model_config": {"model_name": "ollama/qwen2.5:7b"},
                "metadata": {
                    "display_name": "Dispatcher Agent",
                    "role": "Express Fulfillment & Intent Router",
                    "color": "#06b6d4",
                    "room_id": "showroom",
                    "phaser_agent_id": "agt_dispatcher",
                    "sprite_key": "char_06",
                    "is_dispatcher": True,
                },
                "created_at": now,
                "updated_at": now,
                "last_active_at": None,
                "error_message": None,
            },
            {
                "agent_id": "agt_review",
                "name": "Review and Feedback Manager",
                "slug": "review_manager",
                "description": "Customer Sentiment & AI Feedback Lead",
                "agent_type": "reviews",
                "status": "idle",
                "model_config": {"model_name": "ollama/qwen2.5:7b"},
                "metadata": {
                    "display_name": "Review Manager",
                    "role": "Customer Sentiment & Reviews Lead",
                    "color": "#ec4899",
                    "room_id": "meeting",
                    "phaser_agent_id": "agt_review",
                    "sprite_key": "char_07",
                    "is_dispatcher": False,
                },
                "created_at": now,
                "updated_at": now,
                "last_active_at": None,
                "error_message": None,
            },
        ]

    def _load_or_seed(self) -> Dict[str, Any]:
        with _store_lock:
            data = None
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = None

            if not data or not isinstance(data, dict) or not data.get("agents"):
                data = {
                    "agents": self._get_default_agents(),
                    "skills": [],
                    "agent_skills": [],
                    "costs": [],
                    "conversations": [],
                    "messages": [],
                    "tasks": [],
                    "events": [],
                }
                self._save(data)
            return data

    def _save(self, data: Dict[str, Any]) -> None:
        with _store_lock:
            try:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Error saving agents_office.json: {e}")

    # ================================================================
    # Agent CRUD
    # ================================================================

    def create_agent(self, agent_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        db = self._load_or_seed()
        now = datetime.now(timezone.utc).isoformat()
        agent = {
            "agent_id": agent_id,
            "name": data["name"],
            "slug": data["slug"],
            "description": data.get("description", ""),
            "agent_type": data.get("agent_type", "general"),
            "status": "idle",
            "model_config": data.get("model_config", {}),
            "metadata": data.get("metadata", {}),
            "created_at": now,
            "updated_at": now,
            "last_active_at": None,
            "error_message": None,
        }
        db["agents"].append(agent)
        self._save(db)
        return agent

    def list_agents(
        self,
        status: Optional[str] = None,
        agent_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        db = self._load_or_seed()
        agents = db.get("agents", [])
        if status:
            agents = [a for a in agents if a.get("status") == status]
        if agent_type:
            agents = [a for a in agents if a.get("agent_type") == agent_type]
        return agents

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        db = self._load_or_seed()
        for a in db.get("agents", []):
            if a.get("agent_id") == agent_id or a.get("slug") == agent_id:
                return a
        return None

    def update_agent(self, agent_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        db = self._load_or_seed()
        for a in db.get("agents", []):
            if a.get("agent_id") == agent_id or a.get("slug") == agent_id:
                if "name" in data and data["name"] is not None:
                    a["name"] = data["name"]
                if "description" in data and data["description"] is not None:
                    a["description"] = data["description"]
                if "agent_type" in data and data["agent_type"] is not None:
                    a["agent_type"] = data["agent_type"]
                if "model_config" in data and data["model_config"] is not None:
                    a["model_config"] = data["model_config"]
                if "metadata" in data and data["metadata"] is not None:
                    a["metadata"] = data["metadata"]
                a["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save(db)
                return a
        return None

    def update_agent_status(
        self,
        agent_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        db = self._load_or_seed()
        for a in db.get("agents", []):
            if a.get("agent_id") == agent_id or a.get("slug") == agent_id:
                a["status"] = status
                a["error_message"] = error_message
                if status == "running":
                    a["last_active_at"] = datetime.now(timezone.utc).isoformat()
                a["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save(db)
                return a
        return None

    def get_agent_detail(self, agent_id: str) -> Optional[Dict[str, Any]]:
        agent = self.get_agent(agent_id)
        if not agent:
            return None
        res = dict(agent)
        res["skills"] = []
        res["recent_events"] = []
        res["total_cost"] = 0.0
        return res

    def get_all_agent_configs(self) -> Dict[str, Any]:
        db = self._load_or_seed()
        configs = {}
        for a in db.get("agents", []):
            slug = a.get("slug")
            if slug:
                m_cfg = a.get("model_config") or {}
                meta = a.get("metadata") or {}
                configs[slug] = {
                    "model_name": m_cfg.get("model_name", "ollama/qwen2.5:7b"),
                    "temperature": m_cfg.get("temperature", 0.7),
                    "max_tokens": m_cfg.get("max_tokens", 2048),
                    "api_base": m_cfg.get("api_base"),
                    "api_key": m_cfg.get("api_key"),
                    "display_name": meta.get("display_name", a.get("name")),
                    "role": meta.get("role", a.get("description")),
                    "system_prompt": a.get("system_prompt", ""),
                    "color": meta.get("color", "#4ade80"),
                    "active": a.get("status") != "offline",
                }
        return configs

    def update_agent_config_by_slug(self, slug: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        db = self._load_or_seed()
        for a in db.get("agents", []):
            if a.get("slug") == slug:
                m_cfg = a.setdefault("model_config", {})
                meta = a.setdefault("metadata", {})
                if "model_name" in config and config["model_name"]:
                    m_cfg["model_name"] = config["model_name"]
                if "temperature" in config and config["temperature"] is not None:
                    m_cfg["temperature"] = config["temperature"]
                if "max_tokens" in config and config["max_tokens"] is not None:
                    m_cfg["max_tokens"] = config["max_tokens"]
                if "api_base" in config:
                    m_cfg["api_base"] = config["api_base"]
                if "api_key" in config:
                    m_cfg["api_key"] = config["api_key"]

                if "display_name" in config and config["display_name"] is not None:
                    meta["display_name"] = config["display_name"]
                    a["name"] = config["display_name"]
                if "role" in config and config["role"] is not None:
                    meta["role"] = config["role"]
                    a["description"] = config["role"]
                if "color" in config and config["color"] is not None:
                    meta["color"] = config["color"]
                if "system_prompt" in config and config["system_prompt"] is not None:
                    a["system_prompt"] = config["system_prompt"]

                a["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save(db)
                return a
        return None

    # ================================================================
    # Skills, Costs, Conversations, Tasks, Query
    # ================================================================

    def create_skill(self, skill_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        db = self._load_or_seed()
        skill = {"skill_id": skill_id, **data, "created_at": now_iso()}
        db.setdefault("skills", []).append(skill)
        self._save(db)
        return skill

    def list_skills(self, skill_type: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        db = self._load_or_seed()
        skills = db.get("skills", [])
        if skill_type:
            skills = [s for s in skills if s.get("skill_type") == skill_type]
        return skills

    def bind_skill(self, agent_id: str, skill_id: str, config: Dict[str, Any] = {}) -> bool:
        db = self._load_or_seed()
        db.setdefault("agent_skills", []).append({"agent_id": agent_id, "skill_id": skill_id, "config": config})
        self._save(db)
        return True

    def unbind_skill(self, agent_id: str, skill_id: str) -> bool:
        db = self._load_or_seed()
        db["agent_skills"] = [bs for bs in db.get("agent_skills", []) if not (bs.get("agent_id") == agent_id and bs.get("skill_id") == skill_id)]
        self._save(db)
        return True

    def record_cost(self, agent_id: str, model_name: str, input_tokens: int, output_tokens: int, total_cost: float = 0.0, **kwargs: Any) -> Dict[str, Any]:
        db = self._load_or_seed()
        cost_entry = {
            "record_id": f"cst_{now_iso()}",
            "agent_id": agent_id,
            "model_name": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost": total_cost,
            "created_at": now_iso(),
        }
        db.setdefault("costs", []).append(cost_entry)
        self._save(db)
        return cost_entry

    def get_costs_by_agent(self) -> List[Dict[str, Any]]:
        db = self._load_or_seed()
        costs = db.get("costs", [])
        by_agent: Dict[str, Dict[str, Any]] = {}
        for c in costs:
            aid = c.get("agent_id", "unknown")
            if aid not in by_agent:
                by_agent[aid] = {"agent_id": aid, "total_input_tokens": 0, "total_output_tokens": 0, "total_cost": 0.0, "request_count": 0}
            by_agent[aid]["total_input_tokens"] += c.get("input_tokens", 0)
            by_agent[aid]["total_output_tokens"] += c.get("output_tokens", 0)
            by_agent[aid]["total_cost"] += c.get("total_cost", 0.0)
            by_agent[aid]["request_count"] += 1
        return list(by_agent.values())

    def get_cost_summary(self) -> Dict[str, Any]:
        costs = self.get_costs_by_agent()
        return {
            "total_cost": sum(c.get("total_cost", 0.0) for c in costs),
            "total_input_tokens": sum(c.get("total_input_tokens", 0) for c in costs),
            "total_output_tokens": sum(c.get("total_output_tokens", 0) for c in costs),
            "agents": costs,
        }

    def list_conversations(self, limit: int = 30) -> List[Dict[str, Any]]:
        db = self._load_or_seed()
        return db.get("conversations", [])[:limit]

    def create_conversation(self, conv_id: str, title: str, metadata: Dict[str, Any] = {}) -> Dict[str, Any]:
        db = self._load_or_seed()
        conv = {"conversation_id": conv_id, "title": title, "metadata": metadata, "created_at": now_iso()}
        db.setdefault("conversations", []).insert(0, conv)
        self._save(db)
        return conv

    def add_message(self, msg_id: str, conversation_id: str, role: str, content: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        db = self._load_or_seed()
        msg = {
            "message_id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "agent_id": agent_id,
            "created_at": now_iso(),
        }
        db.setdefault("messages", []).append(msg)
        self._save(db)
        return msg

    def list_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        db = self._load_or_seed()
        return [m for m in db.get("messages", []) if m.get("conversation_id") == conversation_id]

    def list_tasks(self, **kwargs: Any) -> List[Dict[str, Any]]:
        db = self._load_or_seed()
        return db.get("tasks", [])

    def list_events(self, **kwargs: Any) -> List[Dict[str, Any]]:
        db = self._load_or_seed()
        return db.get("events", [])

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"model_name": "ollama/qwen2.5:7b", "provider": "ollama", "input_price": 0.0, "output_price": 0.0},
        ]

    def execute_query(self, query: str) -> Dict[str, Any]:
        """Read directly from data/inventory.json for data manager queries without SQL."""
        if os.path.exists(INVENTORY_FILE):
            try:
                with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
                    inv = json.load(f)
                return {"success": True, "rows": inv, "count": len(inv)}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": True, "rows": [], "count": 0}


def _create_office_store() -> OfficeStore:
    return OfficeStore()


office_store: OfficeStore = _create_office_store()
