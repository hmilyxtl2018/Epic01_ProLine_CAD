"""Pydantic v2 schemas for /dashboard/quarantine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


DECISION_VALUES = ("approve", "reject", "merge")


class QuarantineItem(BaseModel):
    """One row from quarantine_terms."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    term_normalized: str
    term_display: str
    asset_type: str
    count: int
    evidence: list[Any] = Field(default_factory=list)
    first_seen: datetime
    last_seen: datetime
    decision: str | None = None
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    merge_target_id: str | None = None
    mcp_context_id: str | None = None
    created_at: datetime


class QuarantineListResponse(BaseModel):
    items: list[QuarantineItem]
    total: int
    page: int
    page_size: int


class DecideRequest(BaseModel):
    """Reviewer decision payload for a single quarantine row."""

    decision: Literal["approve", "reject", "merge"]
    merge_target_id: str | None = Field(
        default=None,
        description="Required when decision='merge'; must point to an existing taxonomy_terms.id.",
    )
    reason: str | None = Field(default=None, max_length=500)


class DecideResponse(BaseModel):
    id: str
    decision: str
    reviewer: str
    reviewed_at: datetime
