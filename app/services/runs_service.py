"""Business logic for /dashboard/runs.

Treats `mcp_contexts WHERE agent='ParseAgent' AND deleted_at IS NULL` as the
canonical "runs" surface. Joins to site_models when present.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.security.upload import (
    DEFAULT_MAX_BYTES,
    UploadRejected,
    ValidatedUpload,
    validate_upload,
)
from shared.db_schemas import McpContext, SiteModel


PARSE_AGENT_NAME = "ParseAgent"

# Upload root: configurable via env so CI / Docker can override.
UPLOAD_ROOT = Path(os.getenv("DASHBOARD_UPLOAD_ROOT", "exp/uploads"))

# Hard cap on upload size (50 MB) -- larger files should go through Temporal
# direct-to-MinIO flow added in M2.
MAX_UPLOAD_BYTES = int(os.getenv("DASHBOARD_MAX_UPLOAD_MB", "50")) * 1024 * 1024

# Filename safety -- only basename, no dotdot, no slashes.
def _safe_filename(name: str) -> str:
    base = Path(name).name  # strip directory components
    cleaned = "".join(c for c in base if c.isalnum() or c in "._-")
    return cleaned or "upload.bin"


def list_runs(
    db: Session, *, page: int = 1, page_size: int = 20
) -> tuple[list[McpContext], int]:
    if page < 1:
        page = 1
    page_size = max(1, min(page_size, 200))
    base = (
        select(McpContext)
        .where(McpContext.agent == PARSE_AGENT_NAME)
        .where(McpContext.deleted_at.is_(None))
    )
    total = db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0
    rows = (
        db.execute(
            base.order_by(McpContext.timestamp.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


def get_run_detail(db: Session, mcp_context_id: str) -> dict[str, Any] | None:
    """Return full run record + (optional) site_model summary, or None if missing."""
    ctx = db.scalar(
        select(McpContext)
        .where(McpContext.mcp_context_id == mcp_context_id)
        .where(McpContext.deleted_at.is_(None))
    )
    if ctx is None:
        return None
    sm = db.scalar(
        select(SiteModel)
        .where(SiteModel.mcp_context_id == mcp_context_id)
        .where(SiteModel.deleted_at.is_(None))
    )
    return {
        "mcp_context_id": ctx.mcp_context_id,
        "agent": ctx.agent,
        "agent_version": ctx.agent_version,
        "status": ctx.status,
        "timestamp": ctx.timestamp,
        "latency_ms": ctx.latency_ms,
        "input_payload": ctx.input_payload or {},
        "output_payload": ctx.output_payload or {},
        "error_message": ctx.error_message,
        "site_model_id": sm.site_model_id if sm else None,
        "geometry_integrity_score": (
            float(sm.geometry_integrity_score) if sm and sm.geometry_integrity_score is not None else None
        ),
    }


def create_run(
    db: Session, *, filename: str, file_bytes: bytes, actor: str
) -> dict[str, Any]:
    """Persist upload + insert pending mcp_context row.

    Returns dict with run_id / status / upload_path / detected_format.
    Raises `UploadRejected` (mapped to 4xx by the route) on validation
    failure -- empty / oversize / suffix not allowed / magic-byte mismatch.
    """
    validated = validate_upload(
        filename=filename, file_bytes=file_bytes, max_bytes=MAX_UPLOAD_BYTES
    )

    run_id = uuid.uuid4().hex
    safe_name = _safe_filename(filename)
    target_dir = UPLOAD_ROOT / run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / safe_name
    target_path.write_bytes(file_bytes)

    ctx = McpContext(
        mcp_context_id=run_id,
        agent=PARSE_AGENT_NAME,
        agent_version="v1.0",
        input_payload={
            "upload_path": str(target_path),
            "filename": safe_name,
            "size_bytes": validated.size_bytes,
            "detected_format": validated.detected_format,
            "submitted_by": actor,
        },
        timestamp=datetime.now(tz=timezone.utc),
        status="PENDING",
    )
    db.add(ctx)
    db.flush()  # surface FK / unique violations early; commit happens in get_db()
    return {
        "run_id": run_id,
        "mcp_context_id": run_id,
        "status": "PENDING",
        "upload_path": str(target_path),
        "detected_format": validated.detected_format,
    }
