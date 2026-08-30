"""Agent 注册表 — 从 DB 加载自定义配置，与内置默认合并。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.services.agents.definitions import BUILTIN_AGENTS, DISPATCHER_DEFINITION

log = logging.getLogger(__name__)


def load_agent_registry() -> Dict[str, Dict[str, Any]]:
    """从 DB 加载活跃 Agent 定义，与内置默认合并。

    优先级：DB 自定义 > 内置默认。
    DB 中 active=True 的 agent 会覆盖内置默认。
    DB 中新增的 agent（不在内置列表中）也会被加入。
    """
    # 以内置默认为基础
    registry: Dict[str, Dict[str, Any]] = {}
    for slug, defn in BUILTIN_AGENTS.items():
        registry[slug] = {**defn, "slug": slug}

    # 从 DB 加载自定义配置
    try:
        from app.office.store import office_store
        if office_store is not None:
            db_agents = office_store.get_active_agent_definitions()
            for agent in db_agents:
                slug = agent["slug"]
                if slug == "dispatcher":
                    continue  # 调度员不作为可分配目标

                if slug in registry:
                    # DB 配置覆盖内置默认（仅覆盖非空字段）
                    if agent.get("system_prompt"):
                        registry[slug]["system_prompt"] = agent["system_prompt"]
                    if agent.get("display_name"):
                        registry[slug]["display_name"] = agent["display_name"]
                    if agent.get("role"):
                        registry[slug]["role"] = agent["role"]
                    if agent.get("color"):
                        registry[slug]["color"] = agent["color"]
                    if agent.get("room_id"):
                        registry[slug]["room_id"] = agent["room_id"]
                    if agent.get("phaser_agent_id"):
                        registry[slug]["phaser_agent_id"] = agent["phaser_agent_id"]
                    if agent.get("model_name"):
                        registry[slug]["model_name"] = agent["model_name"]
                else:
                    # 用户自定义的全新 Agent
                    if not agent.get("system_prompt"):
                        continue  # 没有提示词的 agent 无法工作
                    registry[slug] = {
                        "slug": slug,
                        "display_name": agent.get("display_name", slug),
                        "role": agent.get("role", ""),
                        "system_prompt": agent["system_prompt"],
                        "color": agent.get("color", "#cccccc"),
                        "room_id": agent.get("room_id", "workspace"),
                        "phaser_agent_id": agent.get("phaser_agent_id", ""),
                        "model_name": agent.get("model_name", ""),
                    }
    except Exception as e:
        log.warning("从 DB 加载 Agent 定义失败，使用内置默认: %s", e)

    return registry


def get_full_registry() -> Dict[str, Dict[str, Any]]:
    """返回完整注册表（含 dispatcher），供前端 API 使用。"""
    registry = load_agent_registry()
    # 加入调度员
    full = {"dispatcher": {**DISPATCHER_DEFINITION, "slug": "dispatcher"}}
    full.update(registry)
    return full


def build_dispatcher_prompt(registry: Dict[str, Dict[str, Any]]) -> str:
    """Dynamically construct Dispatcher system prompt based on active store fleet agents."""
    agent_descriptions = []
    for i, (slug, defn) in enumerate(registry.items(), 1):
        name = defn.get("display_name", slug)
        role = defn.get("role", "")
        agent_descriptions.append(
            f"{i}. **{name} ({slug})** — {role}"
        )

    agents_section = "\n".join(agent_descriptions)

    # Load available skills if any
    skills_section = ""
    try:
        from app.services.skills.registry import list_skills as list_registered_skills
        skills = list_registered_skills()
        if skills:
            skill_lines = []
            for s in skills:
                agents_str = ", ".join(s.get("agent_slugs", []))
                skill_lines.append(
                    f"- **{s['display_name']}** (`{s['name']}`) — {s['description']} (Assigned Agents: {agents_str})"
                )
            skills_section = "\n## Available Skills\n\n" + "\n".join(skill_lines) + "\n"
    except Exception:
        pass

    return f"""You are the Dispatcher Agent of the AI Growth Commerce Store. You analyze customer and administrative requests and route them to the appropriate specialist agent in the fleet.

## Store Fleet Agents:

{agents_section}
{skills_section}
## Routing Rules:
- Carefully evaluate the user's intent.
- Assign the task to the most suitable specialist agent (e.g. price_manager for prices/margins, inventory_manager for stock/warehouse, order_manager for orders/tracking, finance_manager for refunds/treasury, review_manager for customer reviews, or ceo for high-level business strategy).
- If the user is just casually greeting or making small talk, reply warmly and directly without routing.
- When delegating to an agent, call `assign_task`.
- Always respond in English.

## Output Format:
- Delegating task → Call assign_task
- Small talk / greeting → Reply directly in English"""


def build_dispatcher_tools(registry: Dict[str, Dict[str, Any]]) -> List[Dict]:
    """Dynamically construct Dispatcher tool schemas."""
    agent_slugs = list(registry.keys())

    tools: List[Dict] = [
        {
            "type": "function",
            "function": {
                "name": "assign_task",
                "description": "Assign the user task to a specialist store agent in the fleet",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_slug": {
                            "type": "string",
                            "enum": agent_slugs,
                            "description": "Target Agent Slug identifier",
                        },
                        "task_summary": {
                            "type": "string",
                            "description": "Concise summary of the task assigned to the agent in English",
                        },
                        "needs_collaboration": {
                            "type": "boolean",
                            "description": "Whether multi-agent boardroom collaboration is required",
                        },
                    },
                    "required": ["agent_slug", "task_summary"],
                },
            },
        },
    ]

    # Dynamically add skill trigger tool if registered
    try:
        from app.services.skills.registry import list_skills as list_registered_skills
        skills = list_registered_skills()
        if skills:
            skill_names = [s["name"] for s in skills]
            tools.append({
                "type": "function",
                "function": {
                    "name": "trigger_skill",
                    "description": "Trigger an interactive multi-step skill session",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {
                                "type": "string",
                                "enum": skill_names,
                                "description": "Identifier of the skill to trigger",
                            },
                            "query": {
                                "type": "string",
                                "description": "Core search query extracted from user message",
                            },
                        },
                        "required": ["skill_name", "query"],
                    },
                },
            })
    except Exception:
        pass

    return tools

