#!/usr/bin/env python3
"""ProLine CAD — GitHub Issues 批量创建脚本。

用法:
  # 预览（不实际创建）
  python scripts/create_github_issues.py --dry-run

  # 实际创建（需要 gh CLI 已登录）
  python scripts/create_github_issues.py

前置条件:
  1. 安装 GitHub CLI: https://cli.github.com/
  2. 登录: gh auth login
  3. 在 GitHub 上创建 7 个 Milestones (M0-M6)，记下对应编号
"""

import subprocess
import sys
import json
from dataclasses import dataclass

# ════════════════ Milestone 定义 ════════════════

MILESTONES = {
    "M0": "M0: 项目准备与发现 (Week 1)",
    "M1": "M1: 基础设施与 MCP Toolbelt (Week 2-3)",
    "M2": "M2: ParseAgent (Week 4-5)",
    "M3": "M3: ConstraintAgent (Week 6-7)",
    "M4": "M4: LayoutAgent (Week 8-9)",
    "M5": "M5: 编排+LLM+UI (Week 10)",
    "M6": "M6: 测试+部署 (Week 11-12)",
}


@dataclass
class Issue:
    title: str
    milestone: str
    labels: list[str]
    body: str


# ════════════════ Issue 定义（42 个） ════════════════

ISSUES: list[Issue] = [
    # ── M0: 项目准备与发现 (6 issues) ──
    Issue(
        title="[M0] 收集 5-10 个代表性 CAD 样本并建立回归测试集",
        milestone="M0",
        labels=["enhancement", "M0"],
        body="""## 任务描述
收集不同格式(DWG/IFC/STEP/DXF)、不同规模(small/medium/large)的 CAD 样本文件。
手工标注标准答案（本体资产、约束状态、预期方案）。

## 验收准则
- [ ] 至少 5 个 CAD 样本文件已下载并分类
- [ ] 每个样本有标注的 ground truth（assets 列表、关系）
- [ ] 文件按 tier1/tier2/tier3 分级存放

## 参考
- ExcPlan/执行计划 §0.1
- PRD/step6.1-航空制造领域测试数据方案.md
""",
    ),
    Issue(
        title="[M0] 定义约束库 CS-001 (15+ 约束, PRD-3/SOP/HB-Z 来源)",
        milestone="M0",
        labels=["enhancement", "M0"],
        body="""## 任务描述
基于 PRD-3、SOP 蒙皮装配工艺规程、HB/Z 223-2013 标准，定义版本化的约束库。
至少包含 12 个硬约束和 3 个软约束。

## 验收准则
- [ ] 约束库 CS-001 以 YAML/JSON 格式定义
- [ ] 包含 15+ 约束条目
- [ ] 每条约束含 source 引用、authority 标注、type (HARD/SOFT)
- [ ] 版本化管理

## 参考
- ExcPlan/执行计划 §0.1 约束库定义
- PRD/step3.3-PRD-3 §2.1.4
""",
    ),
    Issue(
        title="[M0] 技术评估: Z3/CAD库/GraphDB 选型报告",
        milestone="M0",
        labels=["enhancement", "M0"],
        body="""## 任务描述
评估关键技术组件的可行性和选型决策。

## 评估项
- Z3 部署方式（pip vs 自编译）
- CAD 库（IfcOpenShell、Teigha/ODA、ezdxf）
- GraphDB（Blazegraph vs JanusGraph）
- 向量 DB（Milvus vs FAISS）

## 验收准则
- [ ] 每个组件有选型决策和理由
- [ ] 关键性能指标验证（Z3 solve time, 解析延迟等）
""",
    ),
    Issue(
        title="[M0] 需求确认: CAD 格式/用户角色/审批流程",
        milestone="M0",
        labels=["enhancement", "M0"],
        body="""## 任务描述
确认最小支持 CAD 格式、用户角色权限、审批签名策略。

## 验收准则
- [ ] 确认优先支持的 CAD 格式（DWG/IFC 优先）
- [ ] 用户角色定义（设计/审查/批准）
- [ ] 审批流程文档化
""",
    ),
    Issue(
        title="[M0] 基础设施规划: K8s/Docker 环境准备",
        milestone="M0",
        labels=["enhancement", "M0", "infra"],
        body="""## 任务描述
准备 Docker Compose 本地开发环境和基础镜像。

## 验收准则
- [ ] docker-compose up -d 可正常启动所有服务
- [ ] PostgreSQL 可连接
- [ ] MinIO 可访问
- [ ] Kafka 主题可创建
""",
    ),
    Issue(
        title="[M0] CI/CD 基础管道搭建",
        milestone="M0",
        labels=["enhancement", "M0", "infra"],
        body="""## 任务描述
配置 GitHub Actions CI 管道，确保代码质量门禁。

## 验收准则
- [ ] Push/PR 自动触发 CI
- [ ] ruff lint 检查通过
- [ ] P0 测试必须通过
- [ ] 测试报告作为 artifact 上传
""",
    ),

    # ── M1: 基础设施与 MCP Toolbelt (8 issues) ──
    Issue(
        title="[M1] PostgreSQL DDL + mcp_context 表设计",
        milestone="M1",
        labels=["enhancement", "M1", "infra"],
        body="""## 任务描述
实现数据库初始 DDL，包含 mcp_contexts 表的分区策略。

## 验收准则
- [ ] DDL 可在 PostgreSQL 13+ 上执行
- [ ] mcp_context 表可写入/读取 100K+ 记录
- [ ] 索引优化（on agent, timestamp, status）
""",
    ),
    Issue(
        title="[M1] GraphDB + AeroOntology-v1.0 初始导入",
        milestone="M1",
        labels=["enhancement", "M1", "infra"],
        body="""## 任务描述
配置 Blazegraph，导入 AeroOntology-v1.0 初始本体。

## 验收准则
- [ ] SPARQL 端点可访问
- [ ] 初始本体已导入（RDFS/OWL 类和属性）
- [ ] 中等复杂度查询 < 100ms
""",
    ),
    Issue(
        title="[M1] AuditStore 实现 (S3+DB 双冗余)",
        milestone="M1",
        labels=["enhancement", "M1"],
        body="""## 任务描述
实现 shared/audit_store.py 中定义的接口。

## 验收准则
- [ ] save_context / get_context 可正常工作
- [ ] get_context_chain 可追溯完整链路
- [ ] save_artifact 可存储 PDF/SMT2 到 MinIO
- [ ] 检索接口（by mcp_context_id, by time range）
""",
    ),
    Issue(
        title="[M1] Milvus 部署 + SOP 向量化导入",
        milestone="M1",
        labels=["enhancement", "M1", "infra"],
        body="""## 任务描述
部署 Milvus 向量数据库，将 SOP 文本分段并向量化导入。

## 验收准则
- [ ] Milvus 可连接
- [ ] SOP 段落已向量化并导入
- [ ] Top-5 检索 < 50ms
""",
    ),
    Issue(
        title="[M1] Kafka 主题 + 消费者组 + DLQ 配置",
        milestone="M1",
        labels=["enhancement", "M1", "infra"],
        body="""## 任务描述
配置 Kafka 主题（cad_import, agent1_output, agent2_output, agent3_output），
消费者组和死信队列。

## 验收准则
- [ ] 4 个主题已创建
- [ ] 消费者组可正常消费
- [ ] DLQ + exponential backoff 重试策略
""",
    ),
    Issue(
        title="[M1] mcp_context JSON Schema 定义与约定文档",
        milestone="M1",
        labels=["enhancement", "M1", "documentation"],
        body="""## 任务描述
发布 mcp_context 的 JSON Schema 和命名规则约定。

## 验收准则
- [ ] shared/schemas/mcp_context.json 定义完成
- [ ] 命名规则文档（ctx-<agent_prefix>-<hex>）
- [ ] 必填字段清单
""",
    ),
    Issue(
        title="[M1] /mcp/tool/retrieve_sop 接口实现",
        milestone="M1",
        labels=["enhancement", "M1"],
        body="""## 任务描述
实现 SOP 段落检索 MCP Tool。

## 输入/输出
- Input: {query, top_k}
- Output: {segments, segment_ids, scores}

## 验收准则
- [ ] 接口可调用
- [ ] 返回格式符合 MCPToolResponse schema
- [ ] 每次调用生成 mcp_context_id
""",
    ),
    Issue(
        title="[M1] /mcp/tool/publish_audit_record 接口实现",
        milestone="M1",
        labels=["enhancement", "M1"],
        body="""## 任务描述
实现审计记录发布 MCP Tool。

## 输入/输出
- Input: {mcp_context_ids, decision, signatures}
- Output: {audit_id, storage_url}

## 验收准则
- [ ] 审计记录可写入 DB + S3
- [ ] 支持 PDF 签名附件
- [ ] 返回可检索的 audit_id
""",
    ),

    # ── M2: ParseAgent (7 issues) ──
    Issue(
        title="[M2] CAD 解析模块 (format_detect + entity_extract)",
        milestone="M2",
        labels=["enhancement", "M2", "parse-agent"],
        body="""## 任务描述
实现 ParseService.format_detect() 和 entity_extract()。
集成 ezdxf/IfcOpenShell/ODA，构建 R-Tree 空间索引。

## 验收准则
- [ ] 支持 DWG/DXF 格式检测
- [ ] 实体提取覆盖 LWPOLYLINE、CIRCLE、3DSOLID 等
- [ ] R-Tree 空间索引可查询
- [ ] 5 个样本 CAD 通过率 100%

## 参考
- ExcPlan/Agent Profile §1.3 步骤 1
- spikes/spike_01_dwg_parse/
""",
    ),
    Issue(
        title="[M2] 几何修补与标准化 (topology_repair + coord_normalize)",
        milestone="M2",
        labels=["enhancement", "M2", "parse-agent"],
        body="""## 任务描述
实现 ParseService.topology_repair() 和 coord_normalize()。

## 验收准则
- [ ] 开放 polyline 自动闭合
- [ ] 重复实体去除
- [ ] WCS/UCS 变换正确
- [ ] 单位归一化到 mm
- [ ] geometry_integrity_score >= 0.85 (wing_fal baseline: 0.92)
""",
    ),
    Issue(
        title="[M2] 本体资产识别 (classify_entity + confidence_scoring)",
        milestone="M2",
        labels=["enhancement", "M2", "parse-agent"],
        body="""## 任务描述
实现 ParseService.classify_entity()。
置信度 = 0.3×layer_match + 0.3×geometry_valid + 0.2×port_detection + 0.2×reference_check

## 验收准则
- [ ] avg_confidence >= 0.90 (Thresholds)
- [ ] 低置信度项 (<0.90) 标记为 NEED_REVIEW
- [ ] 支持 Equipment、Conveyor、LiftingPoint 等类型

## 参考
- ExcPlan/Agent Profile §1.3 步骤 2
""",
    ),
    Issue(
        title="[M2] Ontology 图谱生成 (JSON-LD + GraphDB 导入)",
        milestone="M2",
        labels=["enhancement", "M2", "parse-agent"],
        body="""## 任务描述
实现 ParseService.build_ontology_graph()。
生成 APPLIES_TO、PAIR_WITH、TRAVERSES 等语义关系，序列化为 JSON-LD。

## 验收准则
- [ ] 关系类型覆盖 6 种 LinkType
- [ ] JSON-LD 可导入 GraphDB
- [ ] 图谱可通过 SPARQL 查询
""",
    ),
    Issue(
        title="[M2] SiteModel 持久化 + 检索接口",
        milestone="M2",
        labels=["enhancement", "M2", "parse-agent"],
        body="""## 任务描述
实现 SiteModel 到 PostgreSQL 的序列化、存储和按 site_model_id 检索。

## 验收准则
- [ ] SiteModel 可写入 site_models 表
- [ ] 按 site_model_id 可快速检索
- [ ] mcp_context 记录自动关联
""",
    ),
    Issue(
        title="[M2] ParseAgent REST API (/mcp/agent/parse)",
        milestone="M2",
        labels=["enhancement", "M2", "parse-agent"],
        body="""## 任务描述
实现 agents/parse_agent/app.py 中的 parse_cad 端点，串联所有步骤。

## 验收准则
- [ ] POST /mcp/agent/parse 可接收 CAD 文件
- [ ] 返回完整 SiteModel + mcp_context_id
- [ ] p95_latency <= 5s (wing_fal ~2.3s baseline)
- [ ] 错误处理（不支持格式、损坏文件）

## 参考
- ExcPlan/Agent Profile §1.4 输入/输出 Schema
""",
    ),
    Issue(
        title="[M2] ParseAgent 单元+集成测试",
        milestone="M2",
        labels=["enhancement", "M2", "parse-agent", "test"],
        body="""## 任务描述
完善 agents/parse_agent/tests/ 中的测试，覆盖所有核心功能。

## 验收准则
- [ ] 回归测试集 (5 个样本) 100% 通过
- [ ] 测试覆盖率 > 80%
- [ ] 边界情况测试（corrupted CAD、oversized files）
- [ ] latency histogram 性能测试
""",
    ),

    # ── M3: ConstraintAgent (6 issues) ──
    Issue(
        title="[M3] 约束集加载与管理 (ConstraintLoader)",
        milestone="M3",
        labels=["enhancement", "M3", "constraint-agent"],
        body="""## 任务描述
实现 ConstraintService.load_constraint_set()。

## 验收准则
- [ ] 从 DB 读取约束集（CS-001）
- [ ] 分类 HARD/SOFT
- [ ] 含 authority 和 source 引用
""",
    ),
    Issue(
        title="[M3] Z3 集成 + SolverInvoker 实现",
        milestone="M3",
        labels=["enhancement", "M3", "constraint-agent"],
        body="""## 任务描述
实现 Z3Gateway 和 ConstraintService 的 Z3 相关方法。

## 注意
- 避免 sqrt 非线性表达，使用平方距离比较
- 超时设置 10s，有 fallback 策略

## 验收准则
- [ ] 约束可编码为 Z3 LIA 表达式
- [ ] Z3 solve time p95 <= 2s (中等模型)
- [ ] UNSAT Core 可正确提取
- [ ] proof artifact 保存为 SMT-LIB2 格式到 S3

## 参考
- 修正版执行计划 §四.4 (Z3 编码建议)
""",
    ),
    Issue(
        title="[M3] 软约束评分器 (SoftScorer)",
        milestone="M3",
        labels=["enhancement", "M3", "constraint-agent"],
        body="""## 任务描述
实现 ConstraintService.compute_soft_scores()。

## 评分公式
score = 0.4×间距合规 + 0.3×物流效率 + 0.2×吊运安全 + 0.1×扩展性

## 验收准则
- [ ] 每项评分可独立计算
- [ ] 总分归一化到 [0, 1]
- [ ] 手工抽检正确性
""",
    ),
    Issue(
        title="[M3] 硬约束冲突报告 + Reasoning Chain",
        milestone="M3",
        labels=["enhancement", "M3", "constraint-agent"],
        body="""## 任务描述
实现 ConstraintService.generate_violation_report()。

## 验收准则
- [ ] 每个冲突含 {id, type, affected_assets, description, suggested_fix}
- [ ] 附带源标准引用
- [ ] reasoning_chain 人类可读
""",
    ),
    Issue(
        title="[M3] LLM-assisted ConstraintTranslator",
        milestone="M3",
        labels=["enhancement", "M3", "constraint-agent", "llm"],
        body="""## 任务描述
实现 /mcp/tool/constraint_translate 接口。
LLM 仅作为翻译器，输出必须经 Z3 验证。

## 验收准则
- [ ] SOP 段落 → 结构化约束 JSON
- [ ] LLM→Z3 一致率 >= 95%
- [ ] Hallucination 检测（检查 source_id 是否存在）
- [ ] 最大 3 次自动迭代

## 参考
- 修正版执行计划 §五 LLM 定位
""",
    ),
    Issue(
        title="[M3] ConstraintAgent REST API + 测试",
        milestone="M3",
        labels=["enhancement", "M3", "constraint-agent", "test"],
        body="""## 任务描述
实现 POST /mcp/agent/constraint/check 并完善测试。

## 验收准则
- [ ] 硬约束检出率 = 100%（无漏检）
- [ ] 假阳性率 < 0.2%
- [ ] 所有冲突附带 reasoning 与源标准引用
- [ ] mcp_context 完整记录
""",
    ),

    # ── M4: LayoutAgent (6 issues) ──
    Issue(
        title="[M4] 搜索空间定义 + GA 遗传算法实现",
        milestone="M4",
        labels=["enhancement", "M4", "layout-agent"],
        body="""## 任务描述
实现 LayoutService 的搜索空间定义、种群初始化和 GA 主循环。

## GA 参数
- population_size = 100
- max_generations = 50
- delta_threshold = 0.005
- converge_n = 3

## 验收准则
- [ ] 搜索空间支持 1000+ 候选
- [ ] GA 收敛稳定（Δscore 趋势单调递增）
- [ ] 不同初值收敛性测试通过
""",
    ),
    Issue(
        title="[M4] R-Tree 碰撞检测集成",
        milestone="M4",
        labels=["enhancement", "M4", "layout-agent"],
        body="""## 任务描述
实现 LayoutService.collision_check()，使用 R-Tree 空间索引。

## 验收准则
- [ ] 碰撞 → score penalty
- [ ] 避免 N² 暴力比较
- [ ] 与 spike_03_collision 验证结果一致

## 参考
- spikes/spike_03_collision/
""",
    ),
    Issue(
        title="[M4] 候选方案 Z3 验证 + 评分排序",
        milestone="M4",
        labels=["enhancement", "M4", "layout-agent"],
        body="""## 任务描述
实现 verify_candidates() 和 select_top_k()。

## 验收准则
- [ ] 仅保留满足所有硬约束的方案
- [ ] 按软约束评分降序排序
- [ ] Top3 输出
""",
    ),
    Issue(
        title="[M4] Reasoning Chain 生成",
        milestone="M4",
        labels=["enhancement", "M4", "layout-agent"],
        body="""## 任务描述
记录搜索过程: SEARCH → EVALUATE → VERIFY → RECOMMEND。

## 验收准则
- [ ] 每步附带 PRD 引用
- [ ] Top3 方案有详细说明
- [ ] reasoning_chain 可审计
""",
    ),
    Issue(
        title="[M4] LayoutAgent REST API (/mcp/agent/layout/optimize)",
        milestone="M4",
        labels=["enhancement", "M4", "layout-agent"],
        body="""## 任务描述
实现 POST /mcp/agent/layout/optimize 端点。

## 验收准则
- [ ] 输出 Top3 方案
- [ ] 最佳方案 hard_pass=true 且 score >= 0.80
- [ ] p95_latency <= 6s
- [ ] mcp_context 完整记录
""",
    ),
    Issue(
        title="[M4] LayoutAgent 单元+集成测试",
        milestone="M4",
        labels=["enhancement", "M4", "layout-agent", "test"],
        body="""## 任务描述
完善 agents/layout_agent/tests/。

## 验收准则
- [ ] GA 收敛性测试
- [ ] Top3 方案硬约束验证 100% 通过
- [ ] 性能基准 (latency histogram)
""",
    ),

    # ── M5: 编排+LLM+UI (5 issues) ──
    Issue(
        title="[M5] Orchestrator 工作流状态机实现",
        milestone="M5",
        labels=["enhancement", "M5", "orchestrator"],
        body="""## 任务描述
实现 WorkflowStateMachine，管理 Agent 链路调度。

## 工作流
PENDING → PARSE_RUNNING → CONSTRAINT_CHECKING → LAYOUT_OPTIMIZING → COMPLETE

## 验收准则
- [ ] 状态转换合法性校验
- [ ] 超时与重试策略（Agent1: 8s/2次, Agent2: 5s/1次, Agent3: 10s/1次）
- [ ] mcp_context 链路传递（parent_context_id）
""",
    ),
    Issue(
        title="[M5] 迭代循环管理 (Agent3→Agent2 回环)",
        milestone="M5",
        labels=["enhancement", "M5", "orchestrator"],
        body="""## 任务描述
实现 should_iterate() 和迭代回环逻辑。

## 收敛条件
满足度 >= 0.80 且无硬约束违规，或达 max_iterations (3)。

## 验收准则
- [ ] 自动回环工作
- [ ] 最大迭代次数限制
- [ ] 每次迭代 mcp_context 独立记录
""",
    ),
    Issue(
        title="[M5] LLM Tool-calling 适配 + Prompt 模板",
        milestone="M5",
        labels=["enhancement", "M5", "llm"],
        body="""## 任务描述
实现 LLM 的 tool-calling 适配层和 prompt 模板管理。

## 验收准则
- [ ] 支持 OpenAI 和本地 LLM
- [ ] Prompt 模板版本化管理
- [ ] 结构化 JSON 输出（不依赖自由文本）
""",
    ),
    Issue(
        title="[M5] Hallucination 检测器",
        milestone="M5",
        labels=["enhancement", "M5", "llm"],
        body="""## 任务描述
实现 LLM 输出的幻觉检测。

## 检测项
- 引用的 source_id 是否存在于系统
- 引用的 asset_guid 是否在 SiteModel 中
- confidence < threshold 自动进入人工复核

## 验收准则
- [ ] 不存在的引用自动标记并 reject
- [ ] 低置信度自动路由到 HumanReviewQueue
""",
    ),
    Issue(
        title="[M5] 前端 Demo (CAD upload + 图谱 + Top3 对比 + 审批PDF)",
        milestone="M5",
        labels=["enhancement", "M5", "frontend"],
        body="""## 任务描述
实现演示级前端，展示完整闭环流程。

## 功能
- CAD 文件上传
- Ontology 图谱可视化
- Top3 方案对比表
- 审批 PDF 导出

## 验收准则
- [ ] 端到端演示可运行
- [ ] UI 风格遵循 CLAUDE.md 约定（无 emoji、简洁留白）
""",
    ),

    # ── M6: 测试+部署 (4 issues) ──
    Issue(
        title="[M6] 端到端集成测试 + 性能基准",
        milestone="M6",
        labels=["enhancement", "M6", "test"],
        body="""## 任务描述
完整的端到端测试和性能基准。

## 验收准则
- [ ] CAD→Agent1→Agent2→Agent3 完整链路测试
- [ ] 端到端 < 10min (目标 8min)
- [ ] 硬约束检出率 100%
- [ ] mcp_context 链路 100% 完整
""",
    ),
    Issue(
        title="[M6] CI/CD 完善 + Docker 镜像构建",
        milestone="M6",
        labels=["enhancement", "M6", "infra"],
        body="""## 任务描述
完善 CI/CD 管道，添加 Docker 镜像构建。

## 验收准则
- [ ] 每个 Agent 有独立 Dockerfile
- [ ] CI 自动构建镜像
- [ ] 镜像推送到 registry
""",
    ),
    Issue(
        title="[M6] Staging 部署",
        milestone="M6",
        labels=["enhancement", "M6", "infra"],
        body="""## 任务描述
部署到 staging 环境。

## 验收准则
- [ ] 所有服务在 staging 可访问
- [ ] 健康检查通过
- [ ] 基础监控（Prometheus/Grafana）
""",
    ),
    Issue(
        title="[M6] UAT + 用户培训 + 交付文档",
        milestone="M6",
        labels=["enhancement", "M6", "documentation"],
        body="""## 任务描述
用户验收测试和交付准备。

## 验收准则
- [ ] UAT 用例全部通过
- [ ] 用户操作手册
- [ ] 维护手册（部署、监控、故障排除）
- [ ] API 文档（OpenAPI/Swagger）
""",
    ),
]


def create_milestones(dry_run: bool = True) -> None:
    """创建 GitHub Milestones（已通过 API 创建，此函数仅作展示）。"""
    for key, title in MILESTONES.items():
        if dry_run:
            print(f"[DRY-RUN] 创建 Milestone: {title}")
        else:
            try:
                subprocess.run(
                    ["gh", "api", "-X", "POST", f"repos/{REPO}/milestones",
                     "-f", f"title={title}", "-f", "state=open"],
                    check=True, capture_output=True, text=True, encoding="utf-8"
                )
                print(f"  OK Milestone: {title}")
            except subprocess.CalledProcessError:
                print(f"  SKIP Milestone (exists): {title}")


REPO = "hmilyxtl2018/Epic01_ProLine_CAD"

# Milestone 短名 → GitHub milestone 标题映射
MILESTONE_TITLES = {
    "M0": "M0: 项目准备与发现",
    "M1": "M1: 基础设施与MCP Toolbelt",
    "M2": "M2: ParseAgent",
    "M3": "M3: ConstraintAgent",
    "M4": "M4: LayoutAgent",
    "M5": "M5: 编排+LLM+UI",
    "M6": "M6: 测试+部署",
}


def create_issues(dry_run: bool = True) -> None:
    """批量创建 GitHub Issues（含 milestone 关联）。"""
    for i, issue in enumerate(ISSUES, 1):
        labels_args = []
        for label in issue.labels:
            labels_args.extend(["-l", label])

        milestone_title = MILESTONE_TITLES.get(issue.milestone, "")
        milestone_args = ["-m", milestone_title] if milestone_title else []

        if dry_run:
            print(f"[DRY-RUN] #{i:02d} [{issue.milestone}] {issue.title}")
        else:
            try:
                cmd = [
                    "gh", "issue", "create",
                    "--repo", REPO,
                    "--title", issue.title,
                    "--body", issue.body,
                    *labels_args,
                    *milestone_args,
                ]
                result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
                print(f"  OK #{i:02d} {issue.title}")
                print(f"     URL: {result.stdout.strip()}")
            except subprocess.CalledProcessError as e:
                print(f"  FAIL #{i:02d} {issue.title} -- {e.stderr.strip()}")


def main():
    dry_run = "--dry-run" in sys.argv or len(sys.argv) == 1

    if dry_run:
        print("=" * 60)
        print("  DRY RUN — 预览模式（不会实际创建）")
        print("  实际创建请运行: python scripts/create_github_issues.py --execute")
        print("=" * 60)
    else:
        print("=" * 60)
        print("  EXECUTE — 正在创建 GitHub Issues")
        print("=" * 60)

    print(f"\n[Milestones] ({len(MILESTONES)} 个):")
    create_milestones(dry_run)

    print(f"\n[Issues] ({len(ISSUES)} 个):")
    create_issues(dry_run)

    print(f"\n{'预览' if dry_run else '创建'}完成！")
    print(f"  - Milestones: {len(MILESTONES)}")
    print(f"  - Issues: {len(ISSUES)}")

    if dry_run:
        print("\n提示: 运行 `python scripts/create_github_issues.py --execute` 实际创建")
        print("前置条件: gh auth login (GitHub CLI)")


if __name__ == "__main__":
    main()
