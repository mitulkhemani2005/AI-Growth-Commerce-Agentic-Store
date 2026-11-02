"""Snapshot-based JSON storage with atomic replacement and shared file locks.

This backend supports a single application process. Commerce-level mutations use
backend.transactions; file locks alone cannot make a read/modify/write atomic.
"""

import asyncio
import copy
import json
import os
import logging
import threading
import time
import uuid
from typing import Any, Callable

_locks = {}
_registry_lock = threading.Lock()
logger = logging.getLogger(__name__)


def _replace_snapshot(source: str, destination: str) -> None:
    """Keep atomic replacement while tolerating short Windows reader/AV locks.

    Never truncate the destination as a fallback. Real permission failures still
    surface after a bounded wait, leaving the previous snapshot intact.
    """
    for attempt in range(10):
        try:
            os.replace(source, destination)
            return
        except OSError as error:
            if getattr(error, "winerror", None) not in {5, 32, 33} or attempt == 9:
                raise
            time.sleep(min(0.01 * (2 ** attempt), 0.25))


class AsyncJSONStore:
    def __init__(self, file_path: str, default_factory: Callable = list):
        self.file_path = os.path.abspath(file_path)
        self.default_factory = default_factory
        self._cache = None
        self._stamp = None
        with _registry_lock:
            self._lock = _locks.setdefault(os.path.normcase(self.file_path), threading.RLock())

    def _file_stamp(self):
        try:
            stat = os.stat(self.file_path)
            return stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return None

    def get(self) -> Any:
        with self._lock:
            stamp = self._file_stamp()
            if self._cache is None or stamp != self._stamp:
                if stamp is None:
                    data = self.default_factory()
                else:
                    # Surface corruption instead of silently replacing business data.
                    with open(self.file_path, encoding="utf-8") as source:
                        data = json.load(source)
                self._cache = copy.deepcopy(data)
                self._stamp = stamp
            return copy.deepcopy(self._cache)

    def set(self, data: Any) -> None:
        with self._lock:
            snapshot = copy.deepcopy(data)
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            temporary = f"{self.file_path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            try:
                with open(temporary, "w", encoding="utf-8") as destination:
                    json.dump(snapshot, destination, indent=2, ensure_ascii=False, allow_nan=False)
                    destination.flush()
                    os.fsync(destination.fileno())
                _replace_snapshot(temporary, self.file_path)
            finally:
                try:
                    os.remove(temporary)
                except FileNotFoundError:
                    pass  # A successful replacement already consumed the file.
                except OSError:
                    logger.warning("Could not remove temporary snapshot %s", temporary, exc_info=True)
            self._cache = snapshot
            self._stamp = self._file_stamp()

    def invalidate(self) -> None:
        with self._lock:
            self._cache = None
            self._stamp = None

    def mutate(self, mutate_fn: Callable[[Any], Any]) -> Any:
        with self._lock:
            result = mutate_fn(self.get())
            self.set(result)
            return copy.deepcopy(result)

    async def get_async(self) -> Any:
        return await asyncio.to_thread(self.get)

    async def set_async(self, data: Any) -> None:
        await asyncio.to_thread(self.set, data)

    async def mutate_async(self, mutate_fn: Callable[[Any], Any]) -> Any:
        return await asyncio.to_thread(self.mutate, mutate_fn)
