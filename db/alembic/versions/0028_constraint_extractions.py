"""0028 constraint_extractions — LLM 抽取过程的原始 span 痕迹.

Revision ID: 0028_constraint_extractions
Revises: 0027_time_dimension_views
Create Date: 2026-05-11

Why
---
ADR-0010 §2.1 决定的"两层证据"：

* **过程层** ``constraint_extractions``（本迁移）—— LLM/regex/手工 抽取的
  原始 span，含 ``prompt_version / llm_model / extraction_payload / span_hash``。
* **策展层** ``constraint_citations``（0016 已存在）—— 工艺师审核确认的
  约束 ↔ 标准条款引用，带 ``reviewed_at_version``。

两层职责分离避免 0016 的 ``reviewed_at_version`` 语义被未审痕迹污染。

Changes
-------
1. 表 ``constraint_extractions``（4 个索引 + 1 个 UNIQUE + 5 个 CHECK）。
2. 不动 ``process_constraints / constraint_citations / constraint_sources``。

Rollback
--------
``alembic downgrade -1`` ``DROP TABLE constraint_extractions CASCADE``；
0027 视图、0016 策展层均不受影响。
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0028_constraint_extractions"
down_revision = "0027_time_dimension_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS constraint_extractions (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            process_constraint_id   UUID NOT NULL
                                        REFERENCES process_constraints(id)
                                        ON DELETE CASCADE,
            document_id             TEXT NOT NULL,
            chunk_id                TEXT,
            page                    INTEGER,
            char_start              INTEGER,
            char_end                INTEGER,
            span_text               TEXT NOT NULL,
            span_hash               TEXT NOT NULL,
            extractor_kind          VARCHAR(20) NOT NULL,
            llm_model               VARCHAR(60),
            prompt_version          VARCHAR(40),
            extraction_run_id       TEXT,
            extraction_confidence   NUMERIC(3, 2),
            extraction_payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
            extracted_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            mcp_context_id          VARCHAR(100)
                                        REFERENCES mcp_contexts(mcp_context_id),
            schema_version          SMALLINT NOT NULL DEFAULT 1,
            deleted_at              TIMESTAMPTZ,

            -- ── CHECK 约束（与 ADR-0010 §3 表对齐） ──
            CONSTRAINT ck_ce_extractor_kind CHECK (
                extractor_kind IN ('llm', 'regex', 'manual_ui', 'imported')
            ),
            CONSTRAINT ck_ce_span_text_len CHECK (
                length(span_text) BETWEEN 1 AND 1000
            ),
            CONSTRAINT ck_ce_span_hash_format CHECK (
                span_hash ~ '^[0-9a-f]{64}$'
            ),
            CONSTRAINT ck_ce_page_nonneg CHECK (
                page IS NULL OR page >= 0
            ),
            CONSTRAINT ck_ce_char_range CHECK (
                char_start IS NULL OR char_start >= 0
            ),
            CONSTRAINT ck_ce_char_end_after_start CHECK (
                char_end IS NULL OR char_start IS NULL OR char_end > char_start
            ),
            CONSTRAINT ck_ce_confidence_range CHECK (
                extraction_confidence IS NULL
                OR (extraction_confidence >= 0 AND extraction_confidence <= 1)
            ),
            CONSTRAINT ck_ce_payload_object CHECK (
                jsonb_typeof(extraction_payload) = 'object'
            ),
            -- LLM 抽取必带模型 + prompt 版本，便于回放
            CONSTRAINT ck_ce_llm_metadata CHECK (
                extractor_kind <> 'llm'
                OR (llm_model IS NOT NULL AND prompt_version IS NOT NULL)
            )
        );
        """
    )

    # ── 索引 ──
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ce_constraint
            ON constraint_extractions (process_constraint_id)
            WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_ce_document
            ON constraint_extractions (document_id, page)
            WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_ce_run
            ON constraint_extractions (extraction_run_id)
            WHERE extraction_run_id IS NOT NULL
              AND deleted_at IS NULL;

        -- 同一 (constraint, span_hash) 只算一次，防止重复抽取写脏
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_hash_per_constraint
            ON constraint_extractions (process_constraint_id, span_hash)
            WHERE deleted_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS constraint_extractions CASCADE;")
