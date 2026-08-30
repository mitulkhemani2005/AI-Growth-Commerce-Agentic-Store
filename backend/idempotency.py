"""
Idempotency System — Safe, Non-Duplicate Mutation Engine
=========================================================
Guarantees that state-changing and financial operations (refunds, restocks,
dispatches, salary disbursements, and payment captures) cannot be executed
more than once for the same operation ID.

Status lifecycle:
  - IN_PROGRESS: Operation is currently executing
  - SUCCESS: Operation completed successfully (cached result returned on replay)
  - FAILED: Operation failed (retry permitted)
"""

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, Awaitable, Tuple, List
import inspect


IDEMPOTENCY_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "idempotency_records.json"))
_idempotency_lock = threading.RLock()


class IdempotencyManager:
    """Thread-safe persistent idempotency store."""

    def __init__(self, file_path: str = IDEMPOTENCY_FILE):
        self.file_path = file_path
        self._records: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        with _idempotency_lock:
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, "r", encoding="utf-8") as f:
                        self._records = json.load(f)
                except Exception:
                    self._records = {}
            else:
                self._records = {}

    def _save(self):
        try:
            tmp_file = f"{self.file_path}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._records, f, indent=2)
            os.replace(tmp_file, self.file_path)
        except Exception:
            try:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(self._records, f, indent=2)
            except Exception:
                pass

    def check(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Checks if an operation ID has already been recorded."""
        with _idempotency_lock:
            return self._records.get(operation_id)

    def start_operation(
        self,
        operation_id: str,
        operation_type: str,
        actor: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Attempts to acquire the execution lock for this operation ID.
        Returns:
            (acquired: bool, existing_record: Optional[dict])
        """
        with _idempotency_lock:
            rec = self._records.get(operation_id)
            if rec:
                status = rec.get("status")
                # If already completed successfully, return the cached result
                if status == "SUCCESS":
                    return False, rec
                # If in progress and started within the last 60s, treat as locked
                elif status == "IN_PROGRESS":
                    started_at = rec.get("started_at_ts", 0.0)
                    if (time.time() - started_at) < 60.0:
                        return False, rec
                    # Stale in-progress operation timed out; allow take-over
                # If failed, allow retry

            now_iso = datetime.now(timezone.utc).isoformat()
            self._records[operation_id] = {
                "operation_id": operation_id,
                "operation_type": operation_type,
                "actor": actor,
                "status": "IN_PROGRESS",
                "started_at": now_iso,
                "started_at_ts": time.time(),
                "completed_at": None,
                "result": None,
                "error": None,
                "retry_count": (rec.get("retry_count", 0) + 1) if rec else 0,
                "metadata": metadata or {}
            }
            self._save()
            return True, None

    def complete_operation(
        self,
        operation_id: str,
        result: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Marks operation as SUCCESS and caches the result."""
        with _idempotency_lock:
            rec = self._records.get(operation_id, {})
            rec["status"] = "SUCCESS"
            rec["completed_at"] = datetime.now(timezone.utc).isoformat()
            rec["result"] = result
            rec["error"] = None
            if metadata:
                rec["metadata"] = {**rec.get("metadata", {}), **metadata}
            self._records[operation_id] = rec
            self._save()
            return rec

    def fail_operation(
        self,
        operation_id: str,
        error_message: str,
        allow_retry: bool = True
    ) -> Dict[str, Any]:
        """Marks operation as FAILED."""
        with _idempotency_lock:
            rec = self._records.get(operation_id, {})
            rec["status"] = "FAILED"
            rec["completed_at"] = datetime.now(timezone.utc).isoformat()
            rec["error"] = error_message
            rec["allow_retry"] = allow_retry
            self._records[operation_id] = rec
            self._save()
            return rec

    def get_all_records(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Returns recent idempotency records."""
        with _idempotency_lock:
            sorted_recs = sorted(
                self._records.values(),
                key=lambda x: x.get("started_at", ""),
                reverse=True
            )
            return sorted_recs[:limit]

    def clear(self):
        """Clears all records (used during test reset)."""
        with _idempotency_lock:
            self._records.clear()
            self._save()


# Singleton
idempotency_manager = IdempotencyManager()


def check_idempotency(operation_id: str) -> Optional[Dict[str, Any]]:
    """Checks if operation has already been recorded."""
    return idempotency_manager.check(operation_id)


async def execute_idempotent_operation(
    operation_id: str,
    operation_type: str,
    actor: str,
    executor: Callable[..., Any],
    *args,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Safely executes an idempotent operation with automatic deduplication.
    If the operation already succeeded, returns the previous cached result.
    If in progress, returns in-progress lock message.
    Otherwise, executes the callable, marks status, and stores result.
    """
    acquired, existing = idempotency_manager.start_operation(
        operation_id=operation_id,
        operation_type=operation_type,
        actor=actor,
        metadata=metadata
    )

    if not acquired and existing:
        if existing.get("status") == "SUCCESS":
            return {
                "success": True,
                "idempotent_replay": True,
                "operation_id": operation_id,
                "message": f"Idempotent replay: operation '{operation_id}' was already executed successfully.",
                "cached_result": existing.get("result"),
                "result": existing.get("result")
            }
        elif existing.get("status") == "IN_PROGRESS":
            return {
                "success": False,
                "idempotent_in_progress": True,
                "operation_id": operation_id,
                "error": f"Operation '{operation_id}' is currently in progress. Please wait for completion."
            }

    # Execute callable
    try:
        if inspect.iscoroutinefunction(executor):
            res = await executor(*args, **kwargs)
        else:
            res = executor(*args, **kwargs)

        # Evaluate if result represents business success
        is_success = True
        if isinstance(res, dict):
            if res.get("success") is False or "error" in res and not res.get("success"):
                is_success = False

        if is_success:
            idempotency_manager.complete_operation(operation_id, res)
            if isinstance(res, dict):
                res["operation_id"] = operation_id
                res["idempotent"] = True
            return res
        else:
            err_msg = str(res.get("error", "Execution failed") if isinstance(res, dict) else "Execution failed")
            idempotency_manager.fail_operation(operation_id, err_msg)
            return res

    except Exception as e:
        err_str = str(e)
        idempotency_manager.fail_operation(operation_id, err_str)
        return {
            "success": False,
            "error": f"Operation '{operation_id}' failed with exception: {err_str}",
            "operation_id": operation_id
        }
