"""Backfill for migration 0015: attach legacy process_constraints to a default ConstraintSet.

Context
-------
Before 0015, `process_constraints` rows were keyed only on `site_model_id` and
the `constraint_sets` table stored two JSONB arrays that nobody referenced.
After 0015, every `process_constraints` row *should* have a
`constraint_set_id` pointing at a `constraint_sets` row with
`status='active'` and `site_model_id = <that site>`.

This script (idempotent) does:

1. For each distinct `site_model_id` found in `process_constraints` with
   `constraint_set_id IS NULL`, create (or reuse) a default
   `constraint_set` with id `cs_default_<site_model_id>` at `status='draft'`.
2. `UPDATE` the orphan `process_constraints` rows with the new
   `constraint_set_id`.
3. Optionally `--publish` to flip the default sets to `status='active'`
   and set `published_at = NOW()`. Defaults to **draft** so operators
   get a chance to review before freezing.
4. `--dry-run` prints the plan without writing.

Usage
-----
    # Export env first (see scripts/dev_up.ps1):
    $env:POSTGRES_DSN = "postgresql+psycopg2://proline:proline_dev@localhost:5432/proline_cad"
    python scripts/backfill_0015.py --dry-run
    python scripts/backfill_0015.py
    python scripts/backfill_0015.py --publish      # promote to active

Safe to re-run: the `cs_default_<sid>` naming is deterministic and
`ON CONFLICT DO NOTHING` guards the insert.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

log = logging.getLogger("backfill_0015")


DEFAULT_SET_PREFIX = "cs_default_"
DEFAULT_SET_VERSION = "v1.0"
DEFAULT_SET_DESCRIPTION = (
    "Auto-created by scripts/backfill_0015.py to adopt pre-0015 "
    "process_constraints rows. Review membership and publish via "
    "POST /constraint-sets/{id}/publish."
)


@dataclass(frozen=True)
class Plan:
    site_model_id: str
    orphan_count: int
    set_exists: bool
    target_set_id: str  # business key, e.g. 'cs_default_sm_alpha01'

    def describe(self) -> str:
        return (
            f"site={self.site_model_id!r:<30} "
            f"orphans={self.orphan_count:>4}  "
            f"set={self.target_set_id!r} "
            f"(exists={self.set_exists})"
        )


def _resolve_engine() -> Engine:
    dsn = os.environ.get("POSTGRES_DSN", "").strip()
    if not dsn:
        print(
            "POSTGRES_DSN is not set. Export it before running (see docstring).",
            file=sys.stderr,
        )
        sys.exit(2)
    return create_engine(dsn, future=True, pool_pre_ping=True)


def _compute_plans(engine: Engine) -> list[Plan]:
    sql = text(
        """
        SELECT pc.site_model_id          AS site_model_id,
               COUNT(*)                  AS orphan_count,
               EXISTS (
                   SELECT 1 FROM constraint_sets cs
                   WHERE cs.constraint_set_id = :prefix || pc.site_model_id
                     AND cs.deleted_at IS NULL
               )                         AS set_exists
          FROM process_constraints pc
         WHERE pc.constraint_set_id IS NULL
           AND pc.deleted_at IS NULL
           AND pc.site_model_id IS NOT NULL
         GROUP BY pc.site_model_id
         ORDER BY orphan_count DESC, pc.site_model_id
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"prefix": DEFAULT_SET_PREFIX}).all()

    plans: list[Plan] = []
    for r in rows:
        sid = r.site_model_id
        plans.append(
            Plan(
                site_model_id=sid,
                orphan_count=int(r.orphan_count),
                set_exists=bool(r.set_exists),
                target_set_id=f"{DEFAULT_SET_PREFIX}{sid}",
            )
        )
    return plans


def _upsert_default_set(engine: Engine, plan: Plan) -> str:
    """Create the default constraint_set if missing; return its UUID id."""
    ins = text(
        """
        INSERT INTO constraint_sets (
            constraint_set_id, version, site_model_id, status,
            description, tags, metadata, created_at, updated_at
        )
        VALUES (
            :csid, :ver, :sid, 'draft',
            :desc, '{backfill,default}'::text[], '{}'::jsonb, NOW(), NOW()
        )
        ON CONFLICT (constraint_set_id) DO NOTHING
        RETURNING id
        """
    )
    sel = text(
        """
        SELECT id FROM constraint_sets
         WHERE constraint_set_id = :csid
           AND deleted_at IS NULL
         LIMIT 1
        """
    )
    with engine.begin() as conn:
        row = conn.execute(
            ins,
            {
                "csid": plan.target_set_id,
                "ver": DEFAULT_SET_VERSION,
                "sid": plan.site_model_id,
                "desc": DEFAULT_SET_DESCRIPTION,
            },
        ).first()
        if row is None:
            # already existed — fetch id
            row = conn.execute(sel, {"csid": plan.target_set_id}).first()
        if row is None:
            raise RuntimeError(
                f"Failed to upsert constraint_set {plan.target_set_id!r}"
            )
        return str(row.id)


def _attach_orphans(engine: Engine, set_uuid: str, site_model_id: str) -> int:
    sql = text(
        """
        UPDATE process_constraints
           SET constraint_set_id = :cs_uuid,
               updated_at        = NOW()
         WHERE constraint_set_id IS NULL
           AND site_model_id     = :sid
           AND deleted_at        IS NULL
        """
    )
    with engine.begin() as conn:
        result = conn.execute(sql, {"cs_uuid": set_uuid, "sid": site_model_id})
        return int(result.rowcount or 0)


def _publish_default(engine: Engine, set_uuid: str) -> None:
    sql = text(
        """
        UPDATE constraint_sets
           SET status       = 'active',
               published_at = NOW(),
               published_by = 'backfill_0015',
               updated_at   = NOW()
         WHERE id = :cs_uuid
           AND status = 'draft'
           AND deleted_at IS NULL
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, {"cs_uuid": set_uuid})


def run(
    engine: Engine,
    *,
    dry_run: bool,
    publish: bool,
) -> None:
    plans = _compute_plans(engine)

    if not plans:
        log.info("No orphan process_constraints rows found — nothing to do.")
        return

    log.info("Plan (%d site_models with orphans):", len(plans))
    total_orphans = 0
    for p in plans:
        log.info("  %s", p.describe())
        total_orphans += p.orphan_count
    log.info("Total orphans: %d", total_orphans)

    if dry_run:
        log.info("--dry-run specified; no writes.")
        return

    for plan in plans:
        set_uuid = _upsert_default_set(engine, plan)
        attached = _attach_orphans(engine, set_uuid, plan.site_model_id)
        log.info(
            "site=%s → set_id=%s attached=%d%s",
            plan.site_model_id, set_uuid, attached,
            " (publish)" if publish else "",
        )
        if publish and attached > 0:
            _publish_default(engine, set_uuid)

    log.info("Backfill complete.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without writing.",
    )
    ap.add_argument(
        "--publish",
        action="store_true",
        help=(
            "After attaching orphans, flip each default set "
            "from draft → active (NOTE: membership becomes immutable; "
            "run only when you've validated the assignments)."
        ),
    )
    ap.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose logging."
    )
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    engine = _resolve_engine()
    try:
        run(engine, dry_run=args.dry_run, publish=args.publish)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
