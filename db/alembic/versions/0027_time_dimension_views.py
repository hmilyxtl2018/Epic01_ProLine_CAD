"""0027 time-dimension constraint views — 时间维度自解释视图.

Revision ID: 0027_time_dimension_views
Revises: 0026_data_architect_views
Create Date: 2026-05-08

Why
---
0024 给 ``process_constraints`` 加了 ``applicable_phases / valid_from /
valid_to`` 三列，落地了 ADR-0009 "时空本体" 里的**时间**这一维。但 0025 /
0026 的视图只是把这三列原样拉出来，没人能"一眼"看出某条约束**现在到底生不
生效**、生命周期阶段对不对。每次都得在 SQL 里写 ``NOW() BETWEEN valid_from
AND valid_to`` + ``applicable_phases ? '<phase>'``，既冗长又容易写错。

本迁移落两张只读 VIEW，把时间维度全部铺平：

* ``v_constraint_temporal`` —— 单条 process_constraint 的时间档案：阶段
  数组、生效窗口、距生效起 / 失效的天数，外加一列 ``temporal_status``
  ('pending' | 'active' | 'expired' | 'permanent') 直接结论化。
* ``v_active_constraints_now`` —— ``v_active_constraints_at_node`` 的
  时间过滤 + 相位展开版：只保留**当前** NOW() 处于生效窗口的行，并把
  ``applicable_phases`` 数组 ``unnest`` 成 ``phase`` 列。前端 / Service
  按相位查询直接 ``WHERE phase = 'OPERATION'`` 即可。

Changes
-------
* 仅 ``CREATE OR REPLACE VIEW``，无业务列变更，无表结构改动。
* 时间判断使用 ``NOW()``，每次查询时刻被动评估。

Rollback
--------
``alembic downgrade 0026_data_architect_views`` 一次性 ``DROP VIEW``，
不丢任何数据。
"""

from __future__ import annotations

from alembic import op

revision = "0027_time_dimension_views"
down_revision = "0026_data_architect_views"
branch_labels = None
depends_on = None


# ════════════════════════ 1. v_constraint_temporal ════════════════════════
#
# 用法：
#   -- 列出所有"已经过期"的约束
#   SELECT constraint_id, rationale, valid_to
#     FROM v_constraint_temporal
#    WHERE temporal_status = 'expired';
#
#   -- 列出 30 天内即将失效的约束
#   SELECT constraint_id, valid_to, days_until_expiry
#     FROM v_constraint_temporal
#    WHERE temporal_status = 'active'
#      AND days_until_expiry IS NOT NULL
#      AND days_until_expiry <= 30
#    ORDER BY days_until_expiry;
_CREATE_TEMPORAL = """
CREATE OR REPLACE VIEW v_constraint_temporal AS
SELECT
    pc.id                       AS constraint_uuid,
    pc.constraint_id,
    pc.constraint_set_id        AS set_uuid,
    pc.class                    AS constraint_class,
    pc.review_status,
    pc.is_active,
    pc.valid_from,
    pc.valid_to,
    pc.applicable_phases,
    COALESCE(jsonb_array_length(pc.applicable_phases), 0)   AS phase_count,

    -- 距生效起的天数（负数表示已经在窗口里 / 已过期）
    CASE
        WHEN pc.valid_from IS NULL THEN NULL
        ELSE EXTRACT(EPOCH FROM (pc.valid_from - NOW())) / 86400.0
    END                                                     AS days_until_start,

    -- 距失效的天数（负数表示已过期）
    CASE
        WHEN pc.valid_to IS NULL THEN NULL
        ELSE EXTRACT(EPOCH FROM (pc.valid_to - NOW())) / 86400.0
    END                                                     AS days_until_expiry,

    -- 时间状态结论：四态
    CASE
        WHEN pc.valid_from IS NULL AND pc.valid_to IS NULL
            THEN 'permanent'
        WHEN pc.valid_from IS NOT NULL AND NOW() < pc.valid_from
            THEN 'pending'
        WHEN pc.valid_to   IS NOT NULL AND NOW() >= pc.valid_to
            THEN 'expired'
        ELSE 'active'
    END                                                     AS temporal_status
FROM process_constraints pc
WHERE pc.deleted_at IS NULL;
"""


# ════════════════════════ 2. v_active_constraints_now ════════════════════════
#
# 用法：
#   -- S20 工位 OPERATION 阶段当前生效约束（替代手写时间 + 相位过滤）
#   SELECT constraint_id, class, category, binding_origin
#     FROM v_active_constraints_now
#    WHERE target_rds_code = '-ENT.AC.SH01.A2.L1.S20'
#      AND phase = 'OPERATION';
#
#   -- 找出所有 phase=COMMISSIONING 阶段会命中的约束
#   SELECT DISTINCT constraint_id, target_rds_code
#     FROM v_active_constraints_now
#    WHERE phase = 'COMMISSIONING';
_CREATE_ACTIVE_NOW = """
CREATE OR REPLACE VIEW v_active_constraints_now AS
SELECT
    v.target_node_id,
    v.target_rds_code,
    v.target_aspect,
    v.target_kind,
    v.constraint_uuid,
    v.constraint_id,
    v.kind,
    v.class,
    v.severity,
    v.category,
    v.review_status,
    v.is_active,
    v.binding_strategy,
    v.binding_confidence,
    v.binding_depth,
    v.binding_origin,
    v.priority,
    v.weight,
    v.rationale,
    v.constraint_confidence,
    v.valid_from,
    v.valid_to,
    -- 把 applicable_phases JSON 数组展平为单行 phase 列
    phase_elem.value #>> '{}'    AS phase
FROM v_active_constraints_at_node v
CROSS JOIN LATERAL jsonb_array_elements(v.applicable_phases) AS phase_elem(value)
WHERE v.is_active
  AND (v.valid_from IS NULL OR NOW() >= v.valid_from)
  AND (v.valid_to   IS NULL OR NOW() <  v.valid_to);
"""


_VIEW_NAMES = (
    "v_active_constraints_now",
    "v_constraint_temporal",
)


def upgrade() -> None:
    op.execute(_CREATE_TEMPORAL)
    op.execute(_CREATE_ACTIVE_NOW)


def downgrade() -> None:
    for name in _VIEW_NAMES:
        op.execute(f"DROP VIEW IF EXISTS {name};")
