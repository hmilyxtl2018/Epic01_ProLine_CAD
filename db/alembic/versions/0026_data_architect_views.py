"""0026 data-architect views — 实体关系自解释视图三件套.

Revision ID: 0026_data_architect_views
Revises: 0025_v_constraints_at_node
Create Date: 2026-05-08

Why
---
HierarchyService 落地之前，Data Architect / 工艺师 / Service 作者需要在
psql / DBeaver 里"一句话看懂实体之间的连接"，否则每个人都得自己写多表
JOIN，既容易错也无法形成共识。本迁移落 4 张只读 VIEW，把 ADR-0009 时空
本体里"层级树 → 约束集合 → 单条约束 → 节点绑定"这条主链路全部铺平：

* ``v_hierarchy_tree``       —— 每个层级节点的完整祖先链 + 深度，按 RDS 排序。
* ``v_constraint_set_summary`` —— 每个 ConstraintSet 的健康度（按 class /
  category / review_status 维度的计数 + 已绑定比例）。
* ``v_constraint_bindings``  —— 单条约束 ↔ 节点的原始绑定（不展开继承），
  两端都带可读标签。和 ``v_active_constraints_at_node``（展开继承）互补。
* ``v_node_constraint_load`` —— 每个层级节点上"实际命中"的活跃且已审批
  约束数（含继承），从 ``v_active_constraints_at_node`` 聚合而来。

Changes
-------
* 仅 ``CREATE OR REPLACE VIEW``，无业务列变更，无表结构改动。
* 视图全部建立在已有索引（``hierarchy_nodes(parent_id)``、
  ``constraint_scopes(constraint_id, node_id)``、
  ``process_constraints(constraint_set_id, review_status, is_active)``）之上，
  无需新增索引。

Rollback
--------
``alembic downgrade 0025_v_constraints_at_node`` 一次性 ``DROP VIEW``，
不丢任何数据。
"""

from __future__ import annotations

from alembic import op


revision = "0026_data_architect_views"
down_revision = "0025_v_constraints_at_node"
branch_labels = None
depends_on = None


# ════════════════════════ 1. v_hierarchy_tree ════════════════════════
#
# 用法：
#   SELECT rds_code, depth, ancestor_path
#     FROM v_hierarchy_tree
#    WHERE root_rds_code = '-ENT.AC'
#    ORDER BY ancestor_path;
_CREATE_HIERARCHY_TREE = """
CREATE OR REPLACE VIEW v_hierarchy_tree AS
WITH RECURSIVE walk AS (
    -- 根节点：parent_id IS NULL
    SELECT
        hn.id                    AS node_id,
        hn.rds_code,
        hn.aspect,
        hn.node_kind,
        hn.name_zh,
        hn.parent_id,
        0                        AS depth,
        hn.rds_code::text         AS root_rds_code,
        ARRAY[hn.rds_code::text]  AS ancestor_rds_path,
        ARRAY[hn.id]              AS ancestor_id_path,
        hn.site_model_id,
        hn.deleted_at
    FROM hierarchy_nodes hn
    WHERE hn.parent_id IS NULL
      AND hn.deleted_at IS NULL

    UNION ALL

    -- 递归：子节点继承 root + 路径
    SELECT
        c.id,
        c.rds_code,
        c.aspect,
        c.node_kind,
        c.name_zh,
        c.parent_id,
        w.depth + 1,
        w.root_rds_code,
        w.ancestor_rds_path || c.rds_code::text,
        w.ancestor_id_path || c.id,
        c.site_model_id,
        c.deleted_at
    FROM hierarchy_nodes c
    JOIN walk w ON c.parent_id = w.node_id
    WHERE c.deleted_at IS NULL
)
SELECT
    node_id,
    rds_code,
    aspect,
    node_kind,
    name_zh,
    parent_id,
    depth,
    root_rds_code,
    ancestor_rds_path,
    ancestor_id_path,
    array_to_string(ancestor_rds_path, ' / ') AS ancestor_path,
    site_model_id
FROM walk;
"""


# ════════════════════════ 2. v_constraint_set_summary ════════════════════════
#
# 用法：
#   SELECT * FROM v_constraint_set_summary
#    WHERE site_model_id = 'SM-001'
#    ORDER BY status, version DESC;
_CREATE_SET_SUMMARY = """
CREATE OR REPLACE VIEW v_constraint_set_summary AS
SELECT
    cs.id                                               AS constraint_set_uuid,
    cs.constraint_set_id,
    cs.version,
    cs.project_id,
    cs.site_model_id,
    cs.status,
    cs.description,
    cs.tags,
    cs.published_at,
    cs.published_by,
    cs.created_at,
    cs.updated_at,

    -- 总量
    COUNT(pc.id)                                        AS total_constraints,
    COUNT(pc.id) FILTER (WHERE pc.is_active)            AS active_constraints,
    COUNT(pc.id) FILTER (WHERE pc.deleted_at IS NULL)   AS live_constraints,

    -- 按 class
    COUNT(pc.id) FILTER (WHERE pc.class = 'hard')        AS hard_count,
    COUNT(pc.id) FILTER (WHERE pc.class = 'soft')        AS soft_count,
    COUNT(pc.id) FILTER (WHERE pc.class = 'preference')  AS preference_count,

    -- 按 review_status
    COUNT(pc.id) FILTER (WHERE pc.review_status = 'draft')         AS draft_count,
    COUNT(pc.id) FILTER (WHERE pc.review_status = 'under_review')  AS under_review_count,
    COUNT(pc.id) FILTER (WHERE pc.review_status = 'approved')      AS approved_count,
    COUNT(pc.id) FILTER (WHERE pc.review_status = 'rejected')      AS rejected_count,
    COUNT(pc.id) FILTER (WHERE pc.review_status = 'superseded')    AS superseded_count,

    -- 健康度：已审批占比
    CASE WHEN COUNT(pc.id) FILTER (WHERE pc.is_active) > 0
         THEN ROUND(
             100.0
             * COUNT(pc.id) FILTER (WHERE pc.review_status = 'approved' AND pc.is_active)
             / COUNT(pc.id) FILTER (WHERE pc.is_active),
             2)
         ELSE NULL
    END                                                  AS approved_percent,

    -- 绑定状态：是否每条约束都至少有一个 scope（INV-15 的非阻塞观察口径）
    COUNT(DISTINCT pc.id) FILTER (
        WHERE pc.review_status = 'approved'
          AND pc.is_active
          AND EXISTS (
              SELECT 1 FROM constraint_scopes sc
               WHERE sc.constraint_id = pc.id
                 AND sc.deleted_at IS NULL)
    )                                                    AS approved_with_scope_count,
    COUNT(DISTINCT pc.id) FILTER (
        WHERE pc.review_status = 'approved'
          AND pc.is_active
          AND NOT EXISTS (
              SELECT 1 FROM constraint_scopes sc
               WHERE sc.constraint_id = pc.id
                 AND sc.deleted_at IS NULL)
    )                                                    AS approved_without_scope_count
FROM constraint_sets cs
LEFT JOIN process_constraints pc
       ON pc.constraint_set_id = cs.id
      AND pc.deleted_at IS NULL
WHERE cs.deleted_at IS NULL
GROUP BY cs.id;
"""


# ════════════════════════ 3. v_constraint_bindings ════════════════════════
#
# 用法：
#   SELECT * FROM v_constraint_bindings
#    WHERE constraint_id = 'PC-DEMO-PRED-01';
_CREATE_BINDINGS = """
CREATE OR REPLACE VIEW v_constraint_bindings AS
SELECT
    sc.id                       AS scope_id,
    pc.id                       AS constraint_uuid,
    pc.constraint_id,
    pc.class                    AS constraint_class,
    pc.severity                 AS constraint_severity,
    pc.category                 AS constraint_category,
    pc.review_status,
    pc.is_active,
    pc.constraint_set_id        AS set_uuid,
    cs.constraint_set_id        AS set_business_id,
    cs.version                  AS set_version,
    cs.status                   AS set_status,

    hn.id                       AS node_id,
    hn.rds_code                 AS node_rds_code,
    hn.aspect                   AS node_aspect,
    hn.node_kind                AS node_kind,
    hn.name_zh                  AS node_name_zh,

    sc.binding_strategy,
    sc.inherit_to_descendants,
    sc.confidence               AS binding_confidence,
    sc.verified_by_user_id      AS binding_verified_by,
    sc.verified_at              AS binding_verified_at,
    sc.binding_evidence,
    sc.created_by               AS binding_created_by,
    sc.mcp_context_id           AS binding_mcp_context_id
FROM constraint_scopes sc
JOIN process_constraints pc
  ON pc.id = sc.constraint_id
 AND pc.deleted_at IS NULL
JOIN hierarchy_nodes hn
  ON hn.id = sc.node_id
 AND hn.deleted_at IS NULL
LEFT JOIN constraint_sets cs
  ON cs.id = pc.constraint_set_id
 AND cs.deleted_at IS NULL
WHERE sc.deleted_at IS NULL;
"""


# ════════════════════════ 4. v_node_constraint_load ════════════════════════
#
# 用法：
#   SELECT * FROM v_node_constraint_load
#    WHERE node_kind = 'Station'
#    ORDER BY active_approved_total DESC;
_CREATE_NODE_LOAD = """
CREATE OR REPLACE VIEW v_node_constraint_load AS
SELECT
    hn.id                           AS node_id,
    hn.rds_code,
    hn.aspect,
    hn.node_kind,
    hn.name_zh,
    hn.site_model_id,

    -- 命中：直接绑定 (binding_origin='direct') 行数
    COUNT(*) FILTER (
        WHERE v.binding_origin = 'direct'
          AND v.is_active
          AND v.review_status = 'approved')              AS active_approved_direct,
    -- 命中：祖先继承 (binding_origin='inherited') 行数
    COUNT(*) FILTER (
        WHERE v.binding_origin = 'inherited'
          AND v.is_active
          AND v.review_status = 'approved')              AS active_approved_inherited,
    -- 总命中：直接 + 继承
    COUNT(*) FILTER (
        WHERE v.is_active AND v.review_status = 'approved')
                                                        AS active_approved_total,

    -- 按 class 拆分
    COUNT(*) FILTER (
        WHERE v.class = 'hard'
          AND v.is_active AND v.review_status = 'approved')
                                                        AS hard_active_approved,
    COUNT(*) FILTER (
        WHERE v.class = 'soft'
          AND v.is_active AND v.review_status = 'approved')
                                                        AS soft_active_approved
FROM hierarchy_nodes hn
LEFT JOIN v_active_constraints_at_node v
       ON v.target_node_id = hn.id
WHERE hn.deleted_at IS NULL
GROUP BY hn.id;
"""


_VIEW_NAMES = (
    "v_node_constraint_load",
    "v_constraint_bindings",
    "v_constraint_set_summary",
    "v_hierarchy_tree",
)


def upgrade() -> None:
    op.execute(_CREATE_HIERARCHY_TREE)
    op.execute(_CREATE_SET_SUMMARY)
    op.execute(_CREATE_BINDINGS)
    op.execute(_CREATE_NODE_LOAD)


def downgrade() -> None:
    for name in _VIEW_NAMES:
        op.execute(f"DROP VIEW IF EXISTS {name};")
