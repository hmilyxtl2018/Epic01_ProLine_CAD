-- ════════════════════════════════════════════════════════════════════════
-- 查询：某节点（工位/设备/工序）当前命中的所有有效约束
--
-- 业务问题
--   "S20 工位现在执行（OPERATION 阶段）时受哪些约束？谁说的？硬还是软？
--    是直接绑定还是从 Line 继承下来的？"
--
-- 数据基础
--   依赖 ADR-0009 时空本体三张表 + migration 0025 的扁平视图：
--     hierarchy_nodes       三视角层级 (LOCATION / PRODUCT / FUNCTION)
--     constraint_scopes     约束 ↔ 节点 N:M + inherit_to_descendants
--     process_constraints   约束本体（业务列：class/severity/category/...）
--     v_active_constraints_at_node
--                           已展开继承的扁平视图（每行 = constraint × target_node）
--
-- 用法
--   把 :target_rds 替换为目标节点 RDS 编码，例如 '-ENT.AC.SH01.A2.L1.S20'。
--   :phase 替换为 LifecyclePhase 枚举值之一，例如 'OPERATION'。
--   :now   通常传 NOW()；做"如果某天怎样"的反事实分析时改成具体时间戳。
-- ════════════════════════════════════════════════════════════════════════

SELECT
    target_rds_code                                   AS "目标节点",
    target_name_zh                                    AS "节点名",
    target_aspect                                     AS "视角",
    target_kind                                       AS "节点类型",

    constraint_id                                     AS "约束ID",
    kind                                              AS "求解类型",
    category                                          AS "业务分类",
    class                                             AS "硬/软",
    conformance                                       AS "符合性",
    severity                                          AS "严重度",
    authority                                         AS "权威来源",
    priority                                          AS "优先级",
    weight                                            AS "权重",
    review_status                                     AS "审核状态",
    rationale                                         AS "工程依据",

    binding_origin                                    AS "命中方式",  -- direct / inherited
    binding_depth                                     AS "继承层数",
    scope_rds_code                                    AS "绑定来源节点",
    scope_name_zh                                     AS "绑定来源名",
    binding_strategy                                  AS "绑定策略",
    binding_confidence                                AS "绑定置信度",
    scope_verified_by                                 AS "绑定审核人",

    applicable_phases                                 AS "适用阶段",
    COALESCE(to_char(valid_from, 'YYYY-MM-DD'), '—')
        || ' ~ ' ||
    COALESCE(to_char(valid_to,   'YYYY-MM-DD'), '—') AS "时间窗",

    source_document_id                                AS "证据文档",
    payload                                           AS "求解 payload"
  FROM v_active_constraints_at_node
 WHERE target_rds_code     = :target_rds
   AND is_active           = TRUE
   AND review_status       IN ('approved', 'under_review')   -- draft 不污染业务结果
   AND applicable_phases   ? :phase                          -- 时间维度
   AND (valid_from IS NULL OR valid_from <= :now)
   AND (valid_to   IS NULL OR valid_to   >  :now)
 ORDER BY
    CASE class WHEN 'hard' THEN 0 WHEN 'soft' THEN 1 ELSE 2 END,
    priority DESC,
    binding_depth ASC;

-- ────────────────────────────────────────────────────────────────────────
-- 演示数据上的预期结果（依赖 scripts/seed_constraint_demo.py）
-- :target_rds = '-ENT.AC.SH01.A2.L1.S20', :phase = 'OPERATION', :now = NOW()
--
--   1) PC-DEMO-PRED-01  hard / MUST / SEQUENCE   direct       (depth=0)
--      —— 冲压完成后方可进入焊装；prio=80
--   2) PC-DEMO-RES-01   hard / MUST / RESOURCE   inherited    (depth=1)
--      —— 来自父节点 Line `-ENT.AC.SH01.A2.L1` 的"压缩空气总管 ≤ 600 kPa"
--
--   • PC-DEMO-EXCL-01 不出现 —— applicable_phases=["DESIGN"]，OPERATION 不命中
--   • PC-DEMO-TAKT-01 不出现 —— review_status='draft'，不参与业务过滤
-- ────────────────────────────────────────────────────────────────────────
