"""0025 view ``v_active_constraints_at_node`` — flat business view.

Revision ID: 0025_v_constraints_at_node
Revises: 0024_process_constraints_phases
Create Date: 2026-05-08

Why
---
ADR-0009 时空本体落地后，"S20 工位在 OPERATION 阶段命中哪些约束"这类查询
需要：
  1. 沿 ``hierarchy_nodes`` 树向下展开 ``constraint_scopes.inherit_to_descendants``；
  2. 把 process_constraints 的全部业务列拉平到 (target_node × constraint) 行。

每个调用方都自己写一遍递归 CTE 既容易写错，也丢业务列。本视图把"约束 → 实际
覆盖到的目标节点"完全展开为一张可索引的扁平视图，前端 / Service 层只需：

    SELECT * FROM v_active_constraints_at_node
     WHERE target_rds_code = '-ENT.AC.SH01.A2.L1.S20'
       AND applicable_phases ? 'OPERATION'
       AND review_status     = 'approved';

Changes
-------
* 创建 VIEW ``v_active_constraints_at_node``。仅读，无业务列变更。
* 不影响 ORM；db_schemas.py 只声明物理表。
* 视图基于 LATERAL/递归 CTE，性能由 ``hierarchy_nodes(parent_id)`` 与
  ``constraint_scopes(node_id)`` 现有索引承担。

Rollback
--------
``alembic downgrade 0024_process_constraints_phases`` 直接 ``DROP VIEW``，
不丢任何数据。
"""

from __future__ import annotations

from alembic import op


revision = "0025_v_constraints_at_node"
down_revision = "0024_process_constraints_phases"
branch_labels = None
depends_on = None


_CREATE_VIEW = """
CREATE OR REPLACE VIEW v_active_constraints_at_node AS
WITH RECURSIVE descendants AS (
    -- 基础行：约束的直接绑定节点 (depth = 0，永远命中)
    SELECT
        cs.id                       AS scope_id,
        cs.constraint_id            AS constraint_uuid,
        cs.node_id                  AS scope_node_id,
        cs.binding_strategy,
        cs.confidence               AS binding_confidence,
        cs.inherit_to_descendants,
        cs.verified_by_user_id      AS scope_verified_by,
        cs.verified_at              AS scope_verified_at,
        hn.id                       AS target_node_id,
        hn.rds_code                 AS target_rds_code,
        hn.aspect                   AS target_aspect,
        hn.node_kind                AS target_kind,
        hn.name_zh                  AS target_name_zh,
        0::int                      AS binding_depth
      FROM constraint_scopes cs
      JOIN hierarchy_nodes hn
        ON hn.id = cs.node_id
       AND hn.deleted_at IS NULL
     WHERE cs.deleted_at IS NULL

    UNION ALL

    -- 递归：当且仅当 inherit_to_descendants = TRUE 时下钻到子孙
    SELECT
        d.scope_id,
        d.constraint_uuid,
        d.scope_node_id,
        d.binding_strategy,
        d.binding_confidence,
        d.inherit_to_descendants,
        d.scope_verified_by,
        d.scope_verified_at,
        child.id,
        child.rds_code,
        child.aspect,
        child.node_kind,
        child.name_zh,
        d.binding_depth + 1
      FROM descendants d
      JOIN hierarchy_nodes child
        ON child.parent_id = d.target_node_id
       AND child.deleted_at IS NULL
     WHERE d.inherit_to_descendants = TRUE
)
SELECT
    -- ── 目标节点（这条约束实际作用到的位置/对象）
    d.target_node_id,
    d.target_rds_code,
    d.target_aspect,
    d.target_kind,
    d.target_name_zh,

    -- ── 约束身份与业务语义
    pc.id                       AS constraint_uuid,
    pc.constraint_id,
    pc.constraint_set_id,
    pc.kind,
    pc.category,
    pc.class                    AS class,
    pc.severity,
    pc.authority,
    pc.conformance,
    pc.priority,
    pc.weight,
    pc.confidence               AS constraint_confidence,
    pc.review_status,
    pc.is_active,
    pc.needs_re_review,
    pc.rationale,
    pc.payload,

    -- ── 时空本体维度 (ADR-0009)
    pc.applicable_phases,
    pc.valid_from,
    pc.valid_to,

    -- ── 证据链
    pc.source_document_id,
    pc.source_span,

    -- ── 绑定来源（直接 / 继承自第 N 层祖先）
    d.scope_node_id,
    sn.rds_code                 AS scope_rds_code,
    sn.name_zh                  AS scope_name_zh,
    d.binding_strategy,
    d.binding_confidence,
    d.inherit_to_descendants,
    d.binding_depth,
    CASE
        WHEN d.binding_depth = 0 THEN 'direct'
        ELSE 'inherited'
    END                         AS binding_origin,
    d.scope_verified_by,
    d.scope_verified_at
  FROM descendants d
  JOIN process_constraints pc
    ON pc.id = d.constraint_uuid
   AND pc.deleted_at IS NULL
  JOIN hierarchy_nodes sn
    ON sn.id = d.scope_node_id
   AND sn.deleted_at IS NULL;

COMMENT ON VIEW v_active_constraints_at_node IS
'ADR-0009 时空本体扁平视图：每行 = (constraint × target_node)。已展开'
' constraint_scopes.inherit_to_descendants 沿 hierarchy_nodes 树向下传播。'
' 按 target_rds_code / applicable_phases / review_status 过滤即可。';
"""

_DROP_VIEW = "DROP VIEW IF EXISTS v_active_constraints_at_node;"


def upgrade() -> None:
    op.execute(_CREATE_VIEW)


def downgrade() -> None:
    op.execute(_DROP_VIEW)
