from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


TaskStatus = Literal["pending", "running", "succeeded", "failed"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


class TaskRecord(BaseModel):
    task_id: str
    trace_id: str
    task_type: str
    status: TaskStatus = "pending"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    input: dict[str, Any] = Field(default_factory=dict)
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class ApiEnvelope(BaseModel):
    trace_id: str
    request_id: str
    data: dict[str, Any]
    error: Optional[str] = None


class ProductImage(BaseModel):
    url: str = Field(min_length=1)
    type: str = "main"


class ProductSpec(BaseModel):
    name: str = Field(min_length=1)
    value: str


class ProductImportItem(BaseModel):
    """External catalog record; optional source metadata is retained."""
    model_config = ConfigDict(extra="allow", allow_inf_nan=False, str_strip_whitespace=True)

    product_id: str = Field(min_length=1, max_length=200)
    platform: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=500)
    price: float = Field(ge=0)
    url: str = ""
    category: Optional[str] = None
    images: list[ProductImage] = Field(default_factory=list)
    specs: list[ProductSpec] = Field(default_factory=list)


class ProductImportRequest(BaseModel):
    source: str = Field(min_length=1, max_length=200)
    batch_id: Optional[str] = None
    products: list[ProductImportItem] = Field(min_length=1, max_length=500)
