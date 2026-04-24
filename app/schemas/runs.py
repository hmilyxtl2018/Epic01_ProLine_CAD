"""Pydantic v2 schemas for /dashboard/runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunSummary(BaseModel):
    """Compact run record for list views."""

    model_config = ConfigDict(from_attributes=True)

    mcp_context_id: str = Field(..., description="Stable run identifier.")
    agent: str
    agent_version: str | None = None
    status: str
    timestamp: datetime
    latency_ms: int = 0
    # ── Source file metadata (mirrored from input_payload for list views) ──
    filename: str | None = None
    size_bytes: int | None = None
    detected_format: str | None = None


class RunListResponse(BaseModel):
    items: list[RunSummary]
    total: int
    page: int
    page_size: int


class RunDetail(RunSummary):
    """Full run record + linked SiteModel summary."""

    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    site_model_id: str | None = None
    geometry_integrity_score: float | None = None
    site_model_statistics: dict[str, Any] = Field(default_factory=dict)
    site_model_cad_source: dict[str, Any] = Field(default_factory=dict)
    site_model_assets_count: int = 0


class RunCreatedResponse(BaseModel):
    """Returned by POST /dashboard/runs."""

    run_id: str = Field(..., description="Alias for mcp_context_id.")
    mcp_context_id: str
    status: str = Field(..., description="Initial status, typically 'PENDING'.")
    upload_path: str = Field(..., description="Server-side path of the stored CAD file.")
