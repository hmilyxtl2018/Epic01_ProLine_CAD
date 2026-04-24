"""Pydantic v2 schemas for /sites/{site_model_id}/constraints (Phase 2.2).

Per-`kind` payload validation is enforced via a discriminated union so
clients get clear 422s instead of opaque DB CHECK errors.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── per-kind payload models ─────────────────────────────────────────────


class PredecessorPayload(BaseModel):
    """A must finish before B — a directed edge in the precedence DAG."""

    kind: Literal["predecessor"] = "predecessor"
    from_asset: str = Field(..., min_length=1, max_length=100, alias="from")
    to_asset: str = Field(..., min_length=1, max_length=100, alias="to")
    lag_s: float = Field(0.0, ge=0.0, description="Min wait between A end and B start.")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("to_asset")
    @classmethod
    def _no_self_edge(cls, v: str, info) -> str:
        if v == info.data.get("from_asset"):
            raise ValueError("predecessor edge cannot point at itself")
        return v


class ResourcePayload(BaseModel):
    """Two or more assets share a finite resource (worker / fixture)."""

    kind: Literal["resource"] = "resource"
    asset_ids: list[str] = Field(..., min_length=2, max_length=64)
    resource: str = Field(..., min_length=1, max_length=64)
    capacity: int = Field(1, ge=1, le=1000)


class TaktPayload(BaseModel):
    """Cycle-time bounds for an asset / line segment (seconds)."""

    kind: Literal["takt"] = "takt"
    asset_id: str = Field(..., min_length=1, max_length=100)
    min_s: float = Field(..., gt=0.0, le=86_400.0)
    max_s: float = Field(..., gt=0.0, le=86_400.0)

    @field_validator("max_s")
    @classmethod
    def _max_ge_min(cls, v: float, info) -> float:
        lo = info.data.get("min_s")
        if lo is not None and v < lo:
            raise ValueError("max_s must be >= min_s")
        return v


class ExclusionPayload(BaseModel):
    """A and B must NEVER run simultaneously (e.g. shared safety zone)."""

    kind: Literal["exclusion"] = "exclusion"
    asset_ids: list[str] = Field(..., min_length=2, max_length=64)
    reason: str | None = Field(None, max_length=200)


ConstraintPayload = Annotated[
    Union[PredecessorPayload, ResourcePayload, TaktPayload, ExclusionPayload],
    Field(discriminator="kind"),
]


# ── CRUD I/O ────────────────────────────────────────────────────────────


class ConstraintCreate(BaseModel):
    """POST body for creating a constraint."""

    constraint_id: str = Field(..., min_length=1, max_length=64,
                               pattern=r"^[A-Za-z0-9_\-:.]+$")
    payload: ConstraintPayload
    priority: int = Field(50, ge=0, le=100)
    is_active: bool = True


class ConstraintUpdate(BaseModel):
    """PATCH body — all fields optional. `kind` cannot change."""

    payload: ConstraintPayload | None = None
    priority: int | None = Field(None, ge=0, le=100)
    is_active: bool | None = None


class ConstraintItem(BaseModel):
    """One row from process_constraints."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    constraint_id: str
    site_model_id: str
    kind: str
    payload: dict
    priority: int
    is_active: bool
    created_by: str | None = None
    mcp_context_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ConstraintListResponse(BaseModel):
    items: list[ConstraintItem]
    total: int
    page: int
    page_size: int


# ── Validator output (DAG cycle / resource overlap) ─────────────────────


class ValidationIssue(BaseModel):
    """One problem found by the constraint validator."""

    severity: Literal["error", "warning"]
    code: str  # e.g. "cycle", "resource_overcommit", "takt_inverted"
    message: str
    constraint_ids: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    site_model_id: str
    ok: bool
    checked_count: int
    issues: list[ValidationIssue]
