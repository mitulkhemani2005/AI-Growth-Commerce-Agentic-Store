"""Regressions for API schema generation and Windows file sharing conflicts."""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend import async_store
from backend.async_store import AsyncJSONStore
from backend.main import app


def test_openapi_includes_office_import_request():
    app.openapi_schema = None
    with TestClient(app) as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        operation = schema["paths"]["/api/v1/office/products/import"]["post"]
        assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/ProductImportRequest")
        assert client.get("/docs").status_code == 200
        assert client.get("/api/v1/office/products/schema").status_code == 200
        assert client.post("/api/v1/office/products/import", json={"source": "test", "products": []}).status_code == 422


def test_atomic_write_retries_windows_sharing_conflict(tmp_path, monkeypatch):
    path = tmp_path / "activity.json"
    store = AsyncJSONStore(str(path))
    store.set(["original"])
    replace = async_store.os.replace
    calls = []

    def temporarily_locked(source, destination):
        calls.append(destination)
        if len(calls) < 4:
            error = PermissionError("Windows sharing conflict")
            error.winerror = 5 if len(calls) == 1 else 32
            raise error
        replace(source, destination)

    monkeypatch.setattr(async_store.os, "replace", temporarily_locked)
    store.set(["updated"])
    assert len(calls) == 4
    assert json.loads(path.read_text()) == ["updated"]
    assert store.get() == ["updated"]
    assert not list(tmp_path.glob("*.tmp"))


def test_office_import_validates_persists_and_updates_records(tmp_path, monkeypatch):
    from app.office import store as office_storage
    monkeypatch.setattr(office_storage, "DATA_DIR", str(tmp_path))
    payload = {"source": "regression", "products": [{
        "product_id": "nova-test-1", "platform": "test", "name": "Nova keyboard",
        "price": 100, "category": "Accessories", "images": [{"url": "https://example.com/keyboard.png"}],
        "specs": [{"name": "Layout", "value": "75%"}],
    }]}
    with TestClient(app) as client:
        result = client.post("/api/v1/office/products/import", json=payload).json()
        assert result["error"] is None
        assert result["data"]["imported_count"] == 1
        payload["products"][0]["price"] = 90
        assert client.post("/api/v1/office/products/import", json=payload).json()["error"] is None
        listing = client.get("/api/v1/office/products", params={"keyword": "keyboard"}).json()["data"]
        assert listing["total"] == 1
        assert listing["products"][0]["price"] == 90
        assert listing["products"][0]["specs"] == [{"name": "Layout", "value": "75%"}]
        payload["products"][0]["price"] = -1
        assert client.post("/api/v1/office/products/import", json=payload).status_code == 422


def test_windows_lock_retry_is_bounded_and_preserves_data(tmp_path, monkeypatch):
    path = tmp_path / "activity.json"
    store = AsyncJSONStore(str(path))
    store.set(["original"])
    attempts = []

    def locked(*_):
        attempts.append(1)
        error = PermissionError("Persistent Windows lock")
        error.winerror = 32
        raise error

    monkeypatch.setattr(async_store.os, "replace", locked)
    monkeypatch.setattr(async_store.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError, match="Persistent"):
        store.set(["updated"])
    assert len(attempts) == 10
    assert store.get() == ["original"]
    assert json.loads(path.read_text()) == ["original"]


def test_permanent_write_failure_preserves_previous_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "activity.json"
    store = AsyncJSONStore(str(path))
    store.set(["original"])

    def denied(*_):
        raise PermissionError("Permanent permission failure")

    monkeypatch.setattr(async_store.os, "replace", denied)
    with pytest.raises(PermissionError, match="Permanent"):
        store.set(["lost"])
    assert store.get() == ["original"]
    assert json.loads(path.read_text()) == ["original"]
    assert not list(tmp_path.glob("*.tmp"))


def test_concurrent_activity_writers_do_not_lose_events(tmp_path):
    path = str(tmp_path / "activity.json")

    def append(number):
        AsyncJSONStore(path).mutate(lambda events: [*events, number])

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(100)))
    assert sorted(AsyncJSONStore(path).get()) == list(range(100))


@pytest.mark.skipif(os.name != "nt", reason="Requires Windows sharing semantics")
def test_actual_windows_reader_lock_is_retried(tmp_path):
    import ctypes
    from ctypes import wintypes

    path = tmp_path / "activity.json"
    store = AsyncJSONStore(str(path))
    store.set(["original"])
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    released = threading.Event()

    def release_reader():
        kernel.CloseHandle(handle)
        released.set()

    timer = threading.Timer(0.1, release_reader)
    timer.start()
    try:
        store.set(["updated"])
    finally:
        timer.join()
    assert released.is_set()
    assert json.loads(path.read_text()) == ["updated"]
