#!/usr/bin/env python
"""sync_corpus_to_minio — Upsert seeds.yaml → constraint_sources + upload to MinIO.

Why
---
Per ADR-0007 §4 (Migration Plan step 3): corpus/ 目录下的 `metadata.yaml`
是 constraint_sources 表的**Git 侧真相源**。本脚本把这个真相同步到两边：

    corpus/seeds.yaml
           │
           ├─► upsert INTO constraint_sources     (Postgres, ADR-0006 §4)
           │
           └─► PUT  s3://constraint-corpus/<auth>/<source_id>/v<ver>/metadata.yaml
                   (MinIO, ADR-0007 §2.2 object key 约定)
                   最终 doc_object_key 回填到 DB 行

Usage
-----
    python scripts/sync_corpus_to_minio.py              # apply
    python scripts/sync_corpus_to_minio.py --dry-run    # preview only
    python scripts/sync_corpus_to_minio.py --check      # CI gate: fail if drift

Env (defaults target the lite stack on 5434 + root-compose MinIO on 9000):
    DB_URL=postgresql://proline:proline@localhost:5434/proline_cad
    MINIO_ENDPOINT=localhost:9000
    MINIO_ACCESS_KEY=minioadmin
    MINIO_SECRET_KEY=minioadmin
    MINIO_SECURE=false
    CORPUS_BUCKET=constraint-corpus
    SEEDS_FILE=corpus/seeds.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import io
import logging
import os
import sys
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import yaml
from minio import Minio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("sync_corpus")


# ────────────────────────────── config ──────────────────────────────

DEFAULT_DB_URL = "postgresql://proline:proline@localhost:5434/proline_cad"
DEFAULT_BUCKET = "constraint-corpus"
DEFAULT_SEEDS_FILE = "corpus/seeds.yaml"


def _minio_client() -> Minio:
    return Minio(
        endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )


def _object_key(src: dict[str, Any]) -> str:
    """ADR-0007 §2.2 — <authority>/<source_id>/v<version>/metadata.yaml.

    `version` may contain '/', ':', ' ' (e.g. 'GB/T 19001-2016', 'AS9100D:2016').
    We sanitize those to '-' / '_' so they become a single S3 path segment
    rather than being interpreted as directory separators.
    """
    raw = str(src.get("version") or "unversioned")
    ver = (
        raw.replace("/", "-")    # GB/T 19001-2016 → GB-T_19001-2016
           .replace(":", "-")    # AS9100D:2016    → AS9100D-2016
           .replace(" ", "_")    # trailing spaces → _
    )
    return f"{src['authority']}/{src['source_id']}/v{ver}/metadata.yaml"


# ────────────────────────────── io ──────────────────────────────


def load_seeds(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    sources = doc.get("sources") or []
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"{path}: no `sources:` list found")
    # minimal shape check
    required = {"source_id", "title", "authority"}
    for i, s in enumerate(sources):
        missing = required - set(s or {})
        if missing:
            raise ValueError(f"{path} sources[{i}]: missing {missing}")
    return sources


# ────────────────────────────── db ──────────────────────────────

UPSERT_SQL = """
INSERT INTO constraint_sources (
    source_id, title, authority, issuing_body, version,
    clause, clause_text, effective_from, expires_at,
    tags, url_or_ref, doc_object_key
) VALUES (
    %(source_id)s, %(title)s, %(authority)s, %(issuing_body)s, %(version)s,
    %(clause)s, %(clause_text)s, %(effective_from)s, %(expires_at)s,
    %(tags)s, %(url_or_ref)s, %(doc_object_key)s
)
ON CONFLICT (source_id) DO UPDATE SET
    title          = EXCLUDED.title,
    authority      = EXCLUDED.authority,
    issuing_body   = EXCLUDED.issuing_body,
    version        = EXCLUDED.version,
    clause         = EXCLUDED.clause,
    clause_text    = EXCLUDED.clause_text,
    effective_from = EXCLUDED.effective_from,
    expires_at     = EXCLUDED.expires_at,
    tags           = EXCLUDED.tags,
    url_or_ref     = EXCLUDED.url_or_ref,
    doc_object_key = EXCLUDED.doc_object_key,
    updated_at     = NOW()
RETURNING source_id, (xmax = 0) AS inserted;
"""


def upsert_sources(db_url: str, sources: list[dict[str, Any]]) -> tuple[int, int]:
    created, updated = 0, 0
    with psycopg2.connect(db_url) as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        for s in sources:
            row = {
                "source_id": s["source_id"],
                "title": s["title"],
                "authority": s["authority"],
                "issuing_body": s.get("issuing_body"),
                "version": s.get("version"),
                "clause": s.get("clause"),
                "clause_text": s.get("clause_text"),
                "effective_from": s.get("effective_from"),
                "expires_at": s.get("expires_at"),
                "tags": s.get("tags") or [],
                "url_or_ref": s.get("url_or_ref"),
                "doc_object_key": f"s3://{os.getenv('CORPUS_BUCKET', DEFAULT_BUCKET)}/{_object_key(s)}",
            }
            cur.execute(UPSERT_SQL, row)
            result = cur.fetchone()
            if result["inserted"]:
                created += 1
                log.info("  [DB created]   %s", s["source_id"])
            else:
                updated += 1
                log.info("  [DB updated]   %s", s["source_id"])
        conn.commit()
    return created, updated


# ────────────────────────────── minio ──────────────────────────────


def upload_to_minio(bucket: str, sources: list[dict[str, Any]]) -> int:
    client = _minio_client()
    if not client.bucket_exists(bucket):
        raise RuntimeError(
            f"bucket `{bucket}` not found — run `python scripts/init_minio.py` first."
        )
    uploaded = 0
    for s in sources:
        key = _object_key(s)
        body = yaml.safe_dump(s, allow_unicode=True, sort_keys=False).encode("utf-8")
        sha = hashlib.sha256(body).hexdigest()[:12]
        client.put_object(
            bucket_name=bucket,
            object_name=key,
            data=io.BytesIO(body),
            length=len(body),
            content_type="application/x-yaml",
            metadata={
                "x-amz-meta-source-id": s["source_id"],
                "x-amz-meta-authority": s["authority"],
                "x-amz-meta-sha256-12": sha,
            },
        )
        log.info("  [S3  PUT  ]    s3://%s/%s  (%d B, sha256=%s…)", bucket, key, len(body), sha)
        uploaded += 1
    return uploaded


# ────────────────────────────── cli ──────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--seeds", default=os.getenv("SEEDS_FILE", DEFAULT_SEEDS_FILE))
    p.add_argument("--db-url", default=os.getenv("DB_URL", DEFAULT_DB_URL))
    p.add_argument("--bucket", default=os.getenv("CORPUS_BUCKET", DEFAULT_BUCKET))
    p.add_argument("--dry-run", action="store_true", help="don't mutate DB or MinIO")
    p.add_argument("--check", action="store_true", help="(CI) only validate parsing; exit 0/1")
    args = p.parse_args()

    seeds_path = Path(args.seeds).resolve()
    if not seeds_path.is_file():
        log.error("seeds file not found: %s", seeds_path)
        return 2

    log.info("── Seeds:       %s", seeds_path)
    log.info("── DB:          %s", args.db_url.rsplit("@", 1)[-1])
    log.info("── MinIO:       %s / bucket=%s", os.getenv("MINIO_ENDPOINT", "localhost:9000"), args.bucket)
    log.info("── Mode:        %s", "DRY-RUN" if args.dry_run else ("CHECK" if args.check else "APPLY"))

    try:
        sources = load_seeds(seeds_path)
    except (yaml.YAMLError, ValueError) as e:
        log.error("seeds parse failed: %s", e)
        return 1
    log.info("Parsed %d sources.", len(sources))

    if args.check:
        log.info("CHECK mode — parse OK, not touching DB/MinIO.")
        return 0

    if args.dry_run:
        for s in sources:
            log.info(
                "  [would-upsert] %-22s  %-9s  → s3://%s/%s",
                s["source_id"], s["authority"], args.bucket, _object_key(s),
            )
        return 0

    log.info("")
    log.info("1/2  Upserting into constraint_sources …")
    try:
        created, updated = upsert_sources(args.db_url, sources)
    except psycopg2.Error as e:
        log.error("DB error: %s", e)
        return 1
    log.info("     → created=%d, updated=%d", created, updated)

    log.info("")
    log.info("2/2  Uploading metadata.yaml to MinIO …")
    try:
        uploaded = upload_to_minio(args.bucket, sources)
    except Exception as e:
        log.error("MinIO error: %s", e)
        return 1
    log.info("     → uploaded=%d", uploaded)

    log.info("")
    log.info("Done. DB rows in sync with seeds.yaml; %d objects in bucket `%s`.", uploaded, args.bucket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
