"""ProLine CAD — Pydantic 域模型定义。

基于 Agent Profile 设计文档中的 JSON Schema，
定义所有 Agent 共享的核心数据结构。

参考文档:
- ExcPlan/产线 Multi-Agent 协同 — 三个 Agent 实例化 Profile 设计.md
- PRD/PRD全局附录_数据模型与接口规范.md
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ════════════════ 枚举类型 ════════════════


class AssetType(str, Enum):
    """资产类型枚举。

    14 个原始类型 + Phase 1.1 (2026-04-22) 新增 8 个产线常用类型，
    覆盖冲压/焊接/装配/物流/工位/缓存六大类。新增类型须同步 0012 CHECK 迁移
    与 shared/models.py 的 AssetType。详见 docs/ROADMAP_3D_SIM.md Phase 1。
    """
    EQUIPMENT = "Equipment"
    CONVEYOR = "Conveyor"
    LIFTING_POINT = "LiftingPoint"
    ZONE = "Zone"
    WALL = "Wall"
    DOOR = "Door"
    PIPE = "Pipe"
    COLUMN = "Column"
    WINDOW = "Window"
    CNC_MACHINE = "CncMachine"
    ELECTRICAL_PANEL = "ElectricalPanel"
    STORAGE_RACK = "StorageRack"
    ANNOTATION = "Annotation"
    OTHER = "Other"
    # ── Phase 1.1: production-line domain types ──
    STAMPING_PRESS = "StampingPress"          # 冲压机/压力机
    WELDING_ROBOT = "WeldingRobot"            # 焊接机器人
    HANDLING_ROBOT = "HandlingRobot"          # 搬运/上下料机器人
    AGV = "Agv"                               # 自动导引车
    BUFFER = "Buffer"                         # 缓存区/料仓
    OPERATOR_STATION = "OperatorStation"     # 人工工位
    INSPECTION_STATION = "InspectionStation"  # 检测工位
    ROBOT_CELL = "RobotCell"                  # 机器人工作单元（围栏内）


class ConstraintType(str, Enum):
    """约束类型：硬约束（MUST）vs 软约束（SHOULD）。"""
    HARD = "HARD"
    SOFT = "SOFT"


class ConstraintCategory(str, Enum):
    """约束业务类别（migration 0019 / blueprint G1）。

    与 ``kind``（求解器形状：predecessor/resource/takt/exclusion）正交：
    ``kind`` 决定如何被消费，``category`` 决定如何被人审视、归类、配色。
    枚举为闭集；新增需 ADR（[CLAUDE.md](../CLAUDE.md) §10）。
    """
    SPATIAL = "SPATIAL"
    SEQUENCE = "SEQUENCE"
    TORQUE = "TORQUE"
    SAFETY = "SAFETY"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    REGULATORY = "REGULATORY"
    QUALITY = "QUALITY"
    RESOURCE = "RESOURCE"
    LOGISTICS = "LOGISTICS"
    OTHER = "OTHER"


class ConstraintReviewStatus(str, Enum):
    """单条约束行级审核生命周期（migration 0020 / blueprint G2）。

    与 ``constraint_sets.status``（draft/active/archived）独立：
    集合层管发布版本，行层管审核工作流。仅 ``approved`` 行可进入
    publish gate（INV-5）。
    """
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ConstraintParseMethod(str, Enum):
    """约束行的来源通道（migration 0020）。

    用于审计 + 可观测性：UI 列表里区分人工与自动产物，
    ADR-0006 §8.1 Q1 要求每条约束可追溯。
    """
    MANUAL_UI = "MANUAL_UI"
    EXCEL_IMPORT = "EXCEL_IMPORT"
    MBOM_IMPORT = "MBOM_IMPORT"
    PMI_ENGINE = "PMI_ENGINE"
    LLM_INFERENCE = "LLM_INFERENCE"


class ConstraintSourceClassification(str, Enum):
    """``constraint_sources.classification`` 取值（migration 0021）。

    决定 LLM 路由：``CONFIDENTIAL`` / ``SECRET`` 强制走本地模型。
    见 PRD-2 §6.2。
    """
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"


class LifecyclePhase(str, Enum):
    """资产 / 约束生命周期阶段（migration 0024 / ADR-0009 §2.1）。

    8 阶段对齐 ISO 55000 资产管理 + CAPEX 阶段划分。约束的
    ``applicable_phases`` 是该枚举的子集，至少 1 个值（INV-14）。
    """
    CONCEPT = "CONCEPT"
    DESIGN = "DESIGN"
    CONSTRUCTION = "CONSTRUCTION"
    COMMISSIONING = "COMMISSIONING"
    OPERATION = "OPERATION"
    MODIFICATION = "MODIFICATION"
    MAINTENANCE = "MAINTENANCE"
    DECOMMISSION = "DECOMMISSION"


class HierarchyAspect(str, Enum):
    """IEC 81346 三视角参考标识系统（migration 0022 / ADR-0009 §2.1）。

    同一物理对象可被三个视角同时引用，但每个 HierarchyNode 行只属于
    单一视角；跨视角等价由 ``properties`` 内的 ``aspect_alias`` 维护。
    """
    FUNCTION = "FUNCTION"  # 工艺/工序视角，前缀 "="
    PRODUCT = "PRODUCT"    # 设备/工装/物料视角，前缀 "-"
    LOCATION = "LOCATION"  # 场所/工位视角，前缀 "+"


class HierarchyNodeKind(str, Enum):
    """HierarchyNode 节点类型（migration 0022 / ADR-0009 §2.1）。

    ISA-95 / IEC 62264 Equipment Hierarchy 扩展：在标准 8 层之外
    叠加 Procedure / Document / AssetTypeTemplate 以承载 FUNCTION 与
    模板视角；INV-16 限定 aspect ↔ node_kind 的合法组合。
    """
    # ── ISA-95 Equipment Hierarchy（LOCATION 视角主用）──
    ENTERPRISE = "Enterprise"
    SITE = "Site"
    AREA = "Area"
    LINE = "Line"
    WORK_CENTER = "WorkCenter"
    STATION = "Station"
    # ── PRODUCT 视角主用 ──
    EQUIPMENT = "Equipment"
    TOOL = "Tool"
    FIXTURE = "Fixture"
    MATERIAL = "Material"
    ASSET_TYPE_TEMPLATE = "AssetTypeTemplate"  # S2 类型匹配的模板节点
    # ── FUNCTION 视角主用 ──
    PROCEDURE = "Procedure"
    DOCUMENT = "Document"


class ConstraintBindingStrategy(str, Enum):
    """约束 ↔ 实体绑定策略 S1–S4（migration 0023 / ADR-0009 §2.4）。"""
    EXPLICIT_ID = "explicit_id"   # S1: SOP/PMI 直写 ID
    ASSET_TYPE = "asset_type"     # S2: 类型匹配模板
    SEMANTIC = "semantic"         # S3: 向量召回
    MANUAL = "manual"             # S4: UI 人工绑定


class LinkType(str, Enum):
    """本体语义关系类型。"""
    APPLIES_TO = "APPLIES_TO"
    GOVERNED_BY = "GOVERNED_BY"
    FEEDS = "FEEDS"
    PAIR_WITH = "PAIR_WITH"
    TRAVERSES = "TRAVERSES"
    LOCATED_IN = "LOCATED_IN"
    LABELED_BY = "LABELED_BY"
    CONTAINS = "CONTAINS"


class CADFormat(str, Enum):
    """支持的 CAD 文件格式。"""
    DWG = "DWG"
    IFC = "IFC"
    STEP = "STEP"
    DXF = "DXF"
    AUTO = "AUTO"


class AgentStatus(str, Enum):
    """Agent 执行状态。"""
    SUCCESS = "SUCCESS"
    SUCCESS_WITH_WARNINGS = "SUCCESS_WITH_WARNINGS"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


class WorkflowState(str, Enum):
    """Orchestrator 工作流状态机。"""
    PENDING = "PENDING"
    PARSE_RUNNING = "PARSE_RUNNING"
    CONSTRAINT_CHECKING = "CONSTRAINT_CHECKING"
    LAYOUT_OPTIMIZING = "LAYOUT_OPTIMIZING"
    ITERATING = "ITERATING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


# ════════════════ 基础几何模型 ════════════════


class Coords(BaseModel):
    """三维坐标。"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class Footprint(BaseModel):
    """设备占地尺寸 (mm)。"""
    length_mm: float
    width_mm: float
    height_mm: float = 0.0


class Port(BaseModel):
    """设备关键点 / 端口（吊点、焊接点等）。"""
    port_name: str
    coords: Coords


# ════════════════ Agent1: ParseAgent 模型 ════════════════


class Asset(BaseModel):
    """本体资产 — CAD 实体映射后的参数化设备对象。"""
    asset_guid: str = Field(default_factory=lambda: f"MDI-{uuid.uuid4().hex[:8].upper()}")
    type: AssetType = AssetType.OTHER
    # GA-必含占位 (Phase 5 才做业务推理): Equipment 内部细分 ——
    # e.g. "HoningMachine" / "WashingMachine" / "LeakTester" / "DeepRolling"。
    # ConstraintAgent 的工艺约束推理需要这一层粒度;先留 schema 位,
    # ParseAgent v1.0 GA 期默认 None,以保持向前兼容旧 SiteModel 数据。
    # 详见 ExcPlan/parse_agent_evaluation_dimensions.md §5.1。
    sub_type: str | None = None
    coords: Coords = Field(default_factory=Coords)
    footprint: Footprint | None = None
    ports: list[Port] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    layer: str = ""
    label: str = ""
    block_name: str = ""
    coord_source: str = ""  # "insert" | "start" | "centroid" | "" (=default origin)

    # ── D5 可追溯 (provenance) — see ExcPlan/parse_agent_evaluation_dimensions.md §1, §2 ──
    # The next three fields are the in-memory mirror of the columns added by
    # `db/alembic/versions/0017_asset_provenance_extension.py`. They are the
    # ParseAgent's audit trail that lets ConstraintAgent / R5 Domain Expert
    # answer the "where did this asset come from?" question without
    # re-parsing the DXF.
    #
    # All three are Optional / default to None / [] so the model stays
    # backwards compatible with SiteModels persisted before §S1-T2 (GA
    # plan) wires up the finalize hook. A None here surfaces in the UI
    # as a yellow "未知 provenance" tag — the correct signal until the
    # ParseAgent finalize() backfills it.

    # H 阶映射 — drives `run_evaluations.h{1..4}_count`. Allowed values:
    #   "rule_block"   (H2 字面量, default 0.95 confidence)
    #   "rule_layer"   (H3 消歧 via layer)
    #   "rule_geom"    (H3 消歧 via geometry features)
    #   "heuristic"    (H3 / H4 boundary, e.g. heuristic.frequency)
    #   "llm_fallback" (H4 LLM 兜底, ≤ 0.8 × LLM self-reported confidence)
    classifier_kind: str | None = None

    # DXF entity handle / cluster_id. Lets R5 Domain Expert click
    # "selected object" → "open in DXF" to inspect the original geometry.
    source_entity_id: str | None = None

    # H5 anti-hallucination evidence words. For LLM-fallback rows this
    # MUST be a subset of the input tokens fed to the LLM, otherwise
    # `agents/parse_agent/hooks.py::H5_response_validator` rejects the
    # classification (post-hoc check; rejected rows fall back to "Other").
    # Empty list `[]` means "no LLM evidence required" (rule-based row).
    evidence_keywords: list[str] = Field(default_factory=list)




class OntologyLink(BaseModel):
    """本体语义关系边。"""
    source_guid: str
    target_guid: str
    link_type: LinkType
    metadata: dict[str, Any] = Field(default_factory=dict)


class CADSource(BaseModel):
    """CAD 文件来源信息。"""
    filename: str
    sha256: str = ""
    format: CADFormat = CADFormat.AUTO
    coord_system: str = "WCS"
    import_timestamp: datetime = Field(default_factory=datetime.utcnow)


class SiteModel(BaseModel):
    """底图模型 — ParseAgent 的核心输出。

    单一数据源（Single Source of Truth），包含所有解析后的资产、
    关系图和统计信息。site_model_id 格式: SM-xxx。
    """
    site_model_id: str = Field(default_factory=lambda: f"SM-{uuid.uuid4().hex[:6].upper()}")
    cad_source: CADSource | None = None
    assets: list[Asset] = Field(default_factory=list)
    links: list[OntologyLink] = Field(default_factory=list)
    geometry_integrity_score: float = Field(ge=0.0, le=1.0, default=0.0)
    statistics: dict[str, Any] = Field(default_factory=dict)


# ════════════════ Agent2: ConstraintAgent 模型 ════════════════


class Constraint(BaseModel):
    """单条约束定义。"""
    constraint_id: str
    type: ConstraintType = ConstraintType.HARD
    description: str = ""
    expression: str = ""
    source: str = ""
    authority: str = ""
    weight: float = Field(ge=0.0, le=1.0, default=1.0)
    affected_assets: list[str] = Field(default_factory=list)


class ConstraintSet(BaseModel):
    """约束集合（版本化）。"""
    constraint_set_id: str = "CS-001"
    version: str = "v1.0"
    hard_constraints: list[Constraint] = Field(default_factory=list)
    soft_constraints: list[Constraint] = Field(default_factory=list)


class Violation(BaseModel):
    """硬约束冲突。"""
    constraint_id: str
    description: str = ""
    affected_assets: list[str] = Field(default_factory=list)
    suggested_fix: str = ""
    source_reference: str = ""


class SoftScore(BaseModel):
    """软约束评分。"""
    constraint_id: str
    score: float = Field(ge=0.0, le=1.0, default=0.0)
    weight: float = Field(ge=0.0, le=1.0, default=1.0)


class ConstraintCheckResult(BaseModel):
    """ConstraintAgent 输出。"""
    sat_result: str = ""  # "SAT" | "UNSAT"
    hard_violations: list[Violation] = Field(default_factory=list)
    soft_scores: list[SoftScore] = Field(default_factory=list)
    reasoning_chain: list[dict[str, Any]] = Field(default_factory=list)
    unsat_core: list[str] = Field(default_factory=list)
    proof_artifact_url: str = ""


# ════════════════ Agent3: LayoutAgent 模型 ════════════════


class Placement(BaseModel):
    """单个资产的布局调整。"""
    asset_guid: str
    dx_mm: float = 0.0
    dy_mm: float = 0.0
    dz_mm: float = 0.0


class LayoutCandidate(BaseModel):
    """布局候选方案。"""
    plan_id: str = ""
    score: float = Field(ge=0.0, le=1.0, default=0.0)
    hard_pass: bool = False
    adjustments: list[Placement] = Field(default_factory=list)
    reasoning: str = ""


class LayoutResult(BaseModel):
    """LayoutAgent 输出 — Top-K 候选方案。"""
    candidates: list[LayoutCandidate] = Field(default_factory=list)
    reasoning_chain: list[dict[str, Any]] = Field(default_factory=list)
    convergence_info: dict[str, Any] = Field(default_factory=dict)


# ════════════════ 审计模型 ════════════════


class AuditRecord(BaseModel):
    """审计记录 — 完整链路追溯。"""
    audit_id: str = Field(default_factory=lambda: f"audit-{uuid.uuid4().hex[:12]}")
    decision: str = ""
    mcp_context_ids: list[str] = Field(default_factory=list)
    approver: str = ""
    signature: str = ""
    pdf_sha256: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
