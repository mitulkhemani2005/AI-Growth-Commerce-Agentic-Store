"""
Agent Task Management — Shared Structured Delegation & Task Lifecycle
======================================================================
Provides structured task creation, claiming, completion, and failure handling.
Enables CEO Agent and Store Owner to delegate complex, asynchronous objectives
to specialist agents without relying on unstructured text commands.
"""

import asyncio
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

from backend.events import event_router, create_event, EventType


TASKS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "agent_tasks.json"))
_task_lock = threading.RLock()


@dataclass
class AgentTask:
    task_id: str
    created_by: str
    assigned_to: str
    objective: str
    priority: str = "normal"  # low, normal, high, critical
    status: str = "pending"  # pending, running, completed, failed
    constraints: List[str] = field(default_factory=list)
    deadline: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: f"corr_{uuid.uuid4().hex[:8]}")
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    claimed_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentTask':
        fields_set = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in fields_set}
        return cls(**filtered)


class TaskManager:
    """Thread-safe persistent task manager."""

    def __init__(self, file_path: str = TASKS_FILE):
        self.file_path = file_path
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        with _task_lock:
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        self._tasks = json.load(f)
                except Exception:
                    self._tasks = {}
            else:
                self._tasks = {}

    def _save(self):
        try:
            tmp_file = f"{self.file_path}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._tasks, f, indent=2)
            os.replace(tmp_file, self.file_path)
        except Exception:
            try:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(self._tasks, f, indent=2)
            except Exception:
                pass

    def create_task(
        self,
        created_by: str,
        assigned_to: str,
        objective: str,
        priority: str = "normal",
        constraints: Optional[List[str]] = None,
        deadline: Optional[str] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentTask:
        """Creates and persists a new agent task."""
        t_id = f"task_{uuid.uuid4().hex[:8]}"
        task = AgentTask(
            task_id=t_id,
            created_by=created_by,
            assigned_to=assigned_to,
            objective=objective,
            priority=priority,
            constraints=constraints or [],
            deadline=deadline,
            correlation_id=correlation_id or f"corr_{uuid.uuid4().hex[:8]}",
            metadata=metadata or {}
        )
        with _task_lock:
            self._tasks[t_id] = task.to_dict()
            self._save()

        # Emit event
        evt = create_event(
            event_type=EventType.AGENT_TASK_CREATED,
            source_agent=created_by,
            target_agent=assigned_to,
            payload={"task_id": t_id, "objective": objective, "priority": priority},
            priority=priority,
            correlation_id=task.correlation_id
        )
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(event_router.emit_event(evt))
        except RuntimeError:
            pass

        return task

    def claim_task(self, task_id: str, agent_name: str) -> Optional[AgentTask]:
        """Claims a pending task."""
        with _task_lock:
            t_data = self._tasks.get(task_id)
            if not t_data or t_data.get("status") != "pending":
                return None
            t_data["status"] = "running"
            t_data["claimed_at"] = datetime.now(timezone.utc).isoformat()
            self._tasks[task_id] = t_data
            self._save()
            return AgentTask.from_dict(t_data)

    def complete_task(self, task_id: str, result: Any, metadata: Optional[Dict[str, Any]] = None) -> Optional[AgentTask]:
        """Marks a task as completed with result."""
        with _task_lock:
            t_data = self._tasks.get(task_id)
            if not t_data:
                return None
            t_data["status"] = "completed"
            t_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            t_data["result"] = result
            if metadata:
                t_data["metadata"] = {**t_data.get("metadata", {}), **metadata}
            self._tasks[task_id] = t_data
            self._save()
            task = AgentTask.from_dict(t_data)

        # Emit event
        evt = create_event(
            event_type=EventType.AGENT_TASK_COMPLETED,
            source_agent=task.assigned_to,
            target_agent=task.created_by,
            payload={"task_id": task_id, "result": result},
            priority=task.priority,
            correlation_id=task.correlation_id
        )
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(event_router.emit_event(evt))
        except RuntimeError:
            pass

        return task

    def fail_task(self, task_id: str, error: str) -> Optional[AgentTask]:
        """Marks a task as failed."""
        with _task_lock:
            t_data = self._tasks.get(task_id)
            if not t_data:
                return None
            t_data["status"] = "failed"
            t_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            t_data["error"] = error
            self._tasks[task_id] = t_data
            self._save()
            task = AgentTask.from_dict(t_data)

        # Emit event
        evt = create_event(
            event_type=EventType.AGENT_TASK_FAILED,
            source_agent=task.assigned_to,
            target_agent=task.created_by,
            payload={"task_id": task_id, "error": error},
            priority="high",
            correlation_id=task.correlation_id
        )
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(event_router.emit_event(evt))
        except RuntimeError:
            pass

        return task

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        with _task_lock:
            t_data = self._tasks.get(task_id)
            return AgentTask.from_dict(t_data) if t_data else None

    def get_tasks(
        self,
        assigned_to: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        with _task_lock:
            all_t = list(self._tasks.values())
            if assigned_to:
                all_t = [t for t in all_t if assigned_to.lower() in t.get("assigned_to", "").lower()]
            if status:
                all_t = [t for t in all_t if t.get("status") == status]
            sorted_t = sorted(all_t, key=lambda x: x.get("created_at", ""), reverse=True)
            return sorted_t[:limit]

    def clear(self):
        with _task_lock:
            self._tasks.clear()
            self._save()


# Singleton
task_manager = TaskManager()
