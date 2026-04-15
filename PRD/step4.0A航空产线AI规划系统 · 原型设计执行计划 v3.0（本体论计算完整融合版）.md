
# 航空产线 AI 规划系统
## 交互式原型 Dashboard 执行计划 v3.0
### 核心升级：Palantir 本体论计算五层架构 × 角色差异化 Dashboard 完整融合

---

## 〇、阅读指引

| 标记 | 含义 |
|------|------|
| 🔴 **[ONT]** | 本体论计算直接体现点（Object / Link / Provenance / Trust / Action Layer） |
| 🟡 **[ROLE]** | 角色差异化难点解决方案 |
| 🔵 **[LLM]** | LLM 能力展示场景，输出落地为 Ontology 变更 |
| 🟢 **[PRD]** | PRD 原文直接引用（对象字段、状态枚举、API 路径） |

---

## 一、AeroOntology v1.0 完整图谱（原型数据基础）

> 🔴 **[ONT]** 这是整个原型的"真理之源"。所有 Dashboard 展示的内容都是此图谱的角色投影，所有按钮点击都是对此图谱的 mutate 操作。

### 1.1 对象类型（Object Types）

```
┌─────────────────────────────────────────────────────────────────────────┐
│  AeroOntology v1.0  ·  PROJ-2024-007  ·  C919总装线03厂房               │
├────────────────────┬────────────────────────┬──────────────────────────┤
│ 对象类型           │ 精确 ID 字段            │ 生命周期状态枚举           │
├────────────────────┼────────────────────────┼──────────────────────────┤
│ SiteModel          │ site_guid               │ DRAFT → LOCKED → ARCHIVED│
│ Asset              │ ontology_object_id      │ ACTIVE / INACTIVE        │
│                    │ master_device_id (MDI)  │                          │
│ Station            │ station_id              │ ACTIVE / DECOMMISSIONED  │
│ CraneRunway        │ ontology_object_id      │ ACTIVE / MAINTENANCE     │
│ GroundPit          │ ontology_object_id      │ ACTIVE / COVERED         │
│ RestrictedZone     │ ontology_object_id      │ ACTIVE / SUSPENDED       │
│ FixtureFoundation  │ ontology_object_id      │ ACTIVE / RESERVED        │
├────────────────────┼────────────────────────┼──────────────────────────┤
│ Constraint         │ constraint_id           │ DRAFT → UNDER_REVIEW     │
│                    │                         │ → APPROVED → SUPERSEDED  │
│                    │                         │ / REJECTED               │
│ Document           │ doc_id                  │ ACTIVE / ARCHIVED        │
│ Operation          │ operation_id            │ PENDING / ACTIVE / DONE  │
│ ProcessGraph       │ graph_id + version      │ DRAFT / ACTIVE / LOCKED  │
├────────────────────┼────────────────────────┼──────────────────────────┤
│ LayoutCandidate    │ layout_id / layout_guid │ DRAFT → VALIDATED        │
│                    │ object_hash (sha256)    │ → LOCKED → ARCHIVED      │
│ SimResult          │ sim_id / object_hash    │ RUNNING → COMPLETED      │
│                    │                         │ → APPROVED / REJECTED    │
├────────────────────┼────────────────────────┼──────────────────────────┤
│ TrustToken         │ token_id (CP-A~E)       │ VALID → STALE            │
│                    │                         │ → EXPIRED / REVOKED      │
│ Decision           │ decision_id             │ DRAFT → PENDING_APPROVAL │
│                    │                         │ → FINAL (不可修改)        │
│ AuditLog           │ log_id                  │ Append-Only（无状态变更） │
└────────────────────┴────────────────────────┴──────────────────────────┘
```

### 1.2 链接类型（Link Types）—— 关系是一等公民

```
// 来自 PRD-2 AeroOntology v1.0 §2 精确定义

Asset      ──── PLACED_IN ──────────▶  Station
              （工装被放置于站位，包含坐标属性）

Asset      ──── GOVERNED_BY ─────────▶  Constraint
              （工装受约束支配，约束可有多个来源）

Constraint ──── SOURCED_FROM ─────────▶  Document
              （约束溯源自文档，携带 page + text_snippet）

Constraint ──── APPLIES_TO ──────────▶  Operation
              （约束作用于工序）

Constraint ──── CONFLICTS_WITH ──────▶  Constraint
              （Z3 引擎检测后写入，双向边）

Constraint ──── SUPERSEDES ──────────▶  Constraint
              （仲裁后高优约束替代低优约束，Append-Only 边）

Operation  ──── DOCUMENTED_IN ───────▶  ProcessGraph
              （工序记录于工序图谱）

TrustToken ──── CERTIFIES ───────────▶  [SiteModel / ConstraintSet /
              LayoutCandidate / SimResult / Decision]
              （Token 为对象状态变更的机器可验证证明）

TrustToken ──── DEPENDS_ON ──────────▶  TrustToken
              （下游 Token 依赖上游 Token，构成验证链）

Decision   ──── EVIDENCE_BOUND_TO ───▶  TrustToken
              （决策快照绑定所有引用 Token 的精确版本）

LLMAction  ──── MODIFIED ────────────▶  [任意对象]
              （LLM Agent 操作留下的审计边，带 session_id）
```

### 1.3 Action Catalog（动作注册表）

> 🔴 **[ONT]** 所有 Action 执行后自动在 AuditLog 追加一条不可篡改记录，这是 Action Layer 的核心。

```
┌──────────────────────────────┬────────────────────────┬──────────────┬────────────────────────┐
│ Action 名称                  │ 适用对象类型            │ 授权角色      │ PRD 来源               │
├──────────────────────────────┼────────────────────────┼──────────────┼────────────────────────┤
│ lockObject(object_id)        │ SiteModel/ConstraintSet │ APPROVER     │ PRD-1/2/3/4/5 §5       │
│                              │ Layout/SimResult/Dec   │ PM           │                        │
├──────────────────────────────┼────────────────────────┼──────────────┼────────────────────────┤
│ invalidateDownstream(token)  │ TrustToken             │ SYSTEM/ADMIN │ PRD-3 US-3-06 AC6      │
│                              │                        │              │ PRD-4 US-4-06          │
├──────────────────────────────┼────────────────────────┼──────────────┼────────────────────────┤
│ requestHumanReview(obj_id)   │ Constraint/Layout      │ ALL          │ PRD-2 §17              │
│                              │ SimResult              │              │ PRD-3 Gate C 阻断       │
├──────────────────────────────┼────────────────────────┼──────────────┼────────────────────────┤
│ suspendOperation(op_ids[])   │ Operation              │ PROCESS_ENG  │ PRD-2 AVC-003          │
│                              │                        │ SYSTEM       │ action_on_violation    │
├──────────────────────────────┼────────────────────────┼──────────────┼────────────────────────┤
│ escalateToHuman(obj_id)      │ Constraint/Operation   │ SYSTEM       │ PRD-2 AVC-004          │
│                              │                        │              │ block_downstream=true  │
├──────────────────────────────┼────────────────────────┼──────────────┼────────────────────────┤
│ notifyStakeholders(event)    │ 任意（事件驱动）         │ SYSTEM       │ PRD-2/3/4/5 §17        │
├──────────────────────────────┼────────────────────────┼──────────────┼────────────────────────┤
│ snapshotObject(obj_id)       │ Decision + Token refs  │ PM/规划总师  │ PRD-5 US-5-03          │
│                              │                        │              │ token_refs快照          │
├──────────────────────────────┼────────────────────────┼──────────────┼────────────────────────┤
│ approveDecision(dec_id)      │ Decision               │ PM（FINAL）  │ PRD-5 US-5-03          │
│                              │                        │              │ PENDING→FINAL          │
└──────────────────────────────┴────────────────────────┴──────────────┴────────────────────────┘
```

---

## 二、Demo 数据规划（精确对齐 PRD 数据模型）

### 2.1 SiteModel 对象

```json
{
  "site_guid": "SM-001",
  "ontology_version": "AeroOntology-v1.0",
  "version": "v1.3.0",
  "lifecycle_state": "LOCKED",
  "base_file_hash": "sha256:abc123def456",
  "active_trust_token": "CP-A-uuid-20260412-003",
  "cp_a_preconditions": {
    "SM001_coord_precision": true,
    "SM002_obstacles_100pct": true,
    "SM003_device_id_aligned": true,
    "SM004_pit_confirmed": true,
    "SM005_restricted_zone_confirmed": true,
    "SM006_crane_data_complete": true,
    "SM007_version_locked": true
  },
  "aviation_special_elements": {
    "ground_pits": [
      { "id": "PIT-001", "ontology_object_id": "uuid-pit-001",
        "depth_mm": 1500, "constraint": "TRAVERSE_PROHIBITED",
        "client_confirmed": true }
    ],
    "crane_runways": [
      { "id": "CRANE-A", "ontology_object_id": "uuid-crane-a",
        "span_mm": 24000, "rail_elevation_mm": 12000,
        "max_load_kg": 50000 }
    ],
    "restricted_zones": [
      { "id": "RZ-001", "ontology_object_id": "uuid-rz-001",
        "type": "EXPLOSION_PROOF", "client_confirmed": true }
    ]
  },
  "assets": [
    { "master_device_id": "MDI-2024-001",
      "ontology_object_id": "uuid-asset-001",
      "lifecycle_state": "ACTIVE",
      "category": "MAIN_JIGS",
      "constraints_ref": ["C001", "C008"] }
  ],
  "mcp_context_id": "ctx-uuid-001"
}
```

### 2.2 Constraint 对象样本（完整 Link 结构）

```json
// C045 - 软约束样本，携带完整 Link 关系
{
  "constraint_id": "C045",
  "type": "SOFT",
  "category": "SPATIAL",
  "authority_level": "MBOM",
  "lifecycle_state": "APPROVED",
  "conflicts_with": ["C023"],
  "supersedes": "C023",
  "superseded_by": null,
  "rule": {
    "relation": "MAX_LOGISTICS_PATH",
    "entity_a": "STATION_01", "entity_b": "STATION_03",
    "value": 1200, "unit": "mm"
  },
  "source_ref": {
    "doc_id": "doc-uuid-456",
    "document": "MBOM v3.2.xlsx",
    "page": 12,
    "section": "5.2.3",
    "text_snippet": "各站位间物流路径建议不超过1200mm以保证节拍"
  },
  "confidence": 0.92,
  "parse_method": "LLM",
  "verified_by": "user-process-eng-001",
  "verified_at": "2026-04-13T09:30:00Z"
}

// CONF-001 冲突仲裁记录（图谱中的 SUPERSEDES 边写入示例）
{
  "conflict_id": "CONF-001",
  "constraint_a": "C023", "constraint_b": "C045",
  "winner": "C045",
  "reason": "MBOM_IMPORT > SOP（authority_level规则BR-02）",
  "arbitration_by": "user-process-eng-001",
  "arbitration_reason": "MBOM数据优先级高于SOP，C045对应MBOM v3.2权威来源",
  "graph_edge_written": "C045 -[SUPERSEDES]-> C023",
  "audit_log_id": "LOG-20260413-0221"
}
```

### 2.3 TrustToken 对象（作为 Ontology 对象，非前端变量）

```json
// CP-C Token 完整对象
{
  "token_id": "CP-C-uuid-20260413-002",
  "token_type": "LAYOUT_LOCK",
  "status": "VALID",
  "certifies": {
    "object_type": "LayoutCandidate",
    "object_id": "LC-202604-007",
    "object_hash": "sha256:layoutContentHash_abc123",
    "object_version": "v3.1.0"
  },
  "depends_on": [
    { "token_id": "CP-A-uuid-20260412-003", "token_type": "SITEMODEL_LOCK" },
    { "token_id": "CP-B-uuid-20260413-001", "token_type": "CONSTRAINTSET_LOCK" }
  ],
  "depended_by": [
    { "token_id": "CP-D-uuid-20260413-002", "token_type": "SIM_APPROVAL" }
  ],
  "evidence_bound_in": ["DEC-20260413-001"],
  "issued_by": "user-layout-eng-001",
  "issued_at": "2026-04-13T10:30:00Z",
  "lifecycle_events": [
    { "event": "ISSUED",      "actor": "user-layout-eng-001", "at": "10:30" },
    { "event": "CONSUMED",    "actor": "user-sim-eng-001",    "at": "11:00" },
    { "event": "SNAPSHOTTED", "actor": "user-pm-zhangsan",    "at": "14:30" }
  ]
}
```

### 2.4 Decision 对象（完整 EVIDENCE_BOUND_TO 结构）

```json
{
  "decision_id": "DEC-20260413-001",
  "board_id": "BOARD-001",
  "project_id": "PROJ-2024-007",
  "decision_type": "APPROVE",
  "state": "FINAL",
  "decision_rationale": "LC-002节拍P50=66.8h满足T≤72h，硬约束违规0，软约束综合评分0.23为三方案最优，批准进入详细设计。S03瓶颈需详细设计阶段重点关注。",
  "layout_ref": { "layout_id": "LC-202604-007",
                  "layout_lock_token_id": "CP-C-uuid-20260413-002" },
  "sim_ref":    { "sim_id": "SIM-007",
                  "sim_approval_token_id": "CP-D-uuid-20260413-002" },
  "token_refs": [
    { "token_id": "CP-A-uuid-20260412-003", "token_type": "SITEMODEL_LOCK",
      "locked_object_hash": "sha256:abc123def456" },
    { "token_id": "CP-B-uuid-20260413-001", "token_type": "CONSTRAINTSET_LOCK",
      "locked_object_hash": "sha256:xyz789abc" },
    { "token_id": "CP-C-uuid-20260413-002", "token_type": "LAYOUT_LOCK",
      "locked_object_hash": "sha256:layoutContentHash_abc123" },
    { "token_id": "CP-D-uuid-20260413-002", "token_type": "SIM_APPROVAL",
      "locked_object_hash": "sha256:simResultHash_def456" }
  ],
  "evidence_state": "VALID",
  "authorized_by": "user-pm-zhangsan",
  "authorized_at": "2026-04-13T14:30:00Z",
  "decision_final_token": {
    "token_id": "CP-E-uuid-20260413-003",
    "token_type": "DECISION_FINAL"
  },
  "related_actions": [
    { "action_type": "notifyStakeholders", "triggered_at": "14:31:00" }
  ],
  "mcp_context_id": "ctx-uuid-005"
}
```

---

## 三、核心技术架构：本体论计算前端实现

### 3.1 OntologyStore（替代普通 Zustand KV Store）

> 🔴 **[ONT]** Token 是图谱对象，失效传播是图遍历，不是事件总线广播。

```typescript
// ontologyStore.ts  ——  原型层 Mock 实现
interface OntologyObject {
  objectType: string;
  objectId: string;
  lifecycleState: string;
  properties: Record<string, any>;
  links: OntologyLink[];         // 关系是对象的一部分
  auditLog: AuditLogEntry[];     // Append-Only
}

interface OntologyLink {
  linkType: string;              // GOVERNED_BY / SUPERSEDES / EVIDENCE_BOUND_TO ...
  targetObjectType: string;
  targetObjectId: string;
  properties?: Record<string, any>;
  createdAt: string;
  createdBy: string;             // HUMAN | LLM_AGENT | SYSTEM
}

// Token 失效 = 图遍历，而非事件广播
function invalidateTokenCascade(tokenId: string) {
  const token = ontologyStore.getObject("TrustToken", tokenId);
  token.lifecycleState = "STALE";
  appendAuditLog(token, "INVALIDATED", "SYSTEM");

  // 遍历 DEPENDED_BY 链接，级联失效
  const downstreamLinks = token.links.filter(l => l.linkType === "DEPENDED_BY");
  downstreamLinks.forEach(link => {
    invalidateTokenCascade(link.targetObjectId);  // 递归图遍历
  });

  // 遍历 EVIDENCE_BOUND_TO 反向链，标记 Decision
  const decisionLinks = token.links.filter(l => l.linkType === "EVIDENCE_BOUND_IN");
  decisionLinks.forEach(link => {
    mutateObjectProperty("Decision", link.targetObjectId,
      "evidence_state", "EVIDENCE_STALE");
  });
}

// 每次操作都落地为 Ontology 变更
function executeAction(
  actionName: string,
  targetObjectType: string,
  targetObjectId: string,
  params: Record<string, any>,
  actor: { id: string; type: "HUMAN" | "LLM_AGENT" | "SYSTEM" }
) {
  // 1. 执行业务逻辑（属性变更 / 链接创建）
  const result = actionCatalog[actionName](targetObjectId, params);

  // 2. 强制写入 AuditLog（不可绕过）
  appendAuditLog({
    event_type: "ACTION_EXECUTED",
    action_name: actionName,
    actor_id: actor.id,
    actor_type: actor.type,
    target_object_type: targetObjectType,
    target_object_id: targetObjectId,
    timestamp: new Date().toISOString(),
    result: result.status,
    downstream_effects: result.sideEffects
  });
}
```

### 3.2 RBAC 权限守卫（按钮级精确控制）

> 🟡 **[ROLE]** 同一对象在不同角色视角下，可见属性维度和可执行 Action 完全不同。

```typescript
// rbac.ts  ——  直接对齐 PRD-2/3/4/5 §6 权限矩阵
const RBAC: Record<string, string[]> = {
  // PRD-1
  "cp_a_lock":              ["APPROVER", "SYSTEM_ADMIN"],
  "layer_annotate":         ["PLANNER", "APPROVER"],

  // PRD-2
  "constraint_review":      ["PROCESS_ENGINEER"],
  "constraint_arbitrate":   ["PROCESS_ENGINEER"],
  "cp_b_lock":              ["PROCESS_ENGINEER", "APPROVER"],
  "knowledge_graph_edit":   ["PROCESS_ENGINEER"],

  // PRD-3
  "layout_canvas_edit":     ["LAYOUT_ENGINEER"],
  "layout_lock_request":    ["LAYOUT_ENGINEER"],
  "layout_lock_approve":    ["PROJECT_MANAGER"],

  // PRD-4
  "sim_gate_d_issue":       ["SIM_ENGINEER"],
  "sim_task_create":        ["SIM_ENGINEER"],

  // PRD-5  （直接来自 PRD-5 §6 权限矩阵）
  "decision_draft":         ["PROJECT_MANAGER", "PLANNER_CHIEF"],
  "decision_final":         ["PROJECT_MANAGER"],
  "snapshot_export":        ["PROJECT_MANAGER", "PLANNER_CHIEF", "AUDITOR", "SYSTEM_ADMIN"],
  "audit_log_view":         ["PROJECT_MANAGER", "PLANNER_CHIEF", "AUDITOR", "SYSTEM_ADMIN"],
  "audit_log_export":       ["AUDITOR", "SYSTEM_ADMIN"],
  "invalidate_downstream":  ["SYSTEM_ADMIN"],
};

// PermissionGate 组件（渗透到按钮级）
const PermissionGate = ({ permission, children, fallback = null }) => {
  const { currentRole } = useAppStore();
  return RBAC[permission]?.includes(currentRole) ? children : fallback;
};
```

### 3.3 视图投影层（同一对象，角色差异化渲染）

> 🟡 **[ROLE]** 这是解决"同一数据，不同视角"难点的核心机制。

```typescript
// viewProjection.ts
const VIEW_PROJECTIONS: Record<string, Record<string, string[]>> = {
  "LayoutCandidate": {
    "LAYOUT_ENGINEER":   ["canvas", "asset_placements", "violation_panel",
                          "crane_check", "soft_warnings", "lock_request_btn"],
    "PROCESS_ENGINEER":  ["violation_report", "constraint_source_links",
                          "arbitrate_shortcut"],
    "SIM_ENGINEER":      ["version_badge", "object_hash", "gate_c_token_status",
                          "bind_sim_btn"],
    "PROJECT_MANAGER":   ["kpi_matrix_row", "gate_c_approve_btn",
                          "comparison_delta"],
    "AUDITOR":           ["audit_log_entries", "token_hash_display",
                          "export_evidence_btn"],
  },
  "Constraint": {
    "PROCESS_ENGINEER":  ["card_full", "source_ref_panel", "review_actions",
                          "arbitrate_panel", "links_display"],
    "LAYOUT_ENGINEER":   ["card_readonly", "violation_context", "source_link"],
    "PROJECT_MANAGER":   ["summary_only", "violation_count"],
    "AUDITOR":           ["card_readonly", "audit_trail_only"],
  },
  "TrustToken": {
    "ALL":               ["token_id", "status_badge", "issued_at", "issued_by"],
    "PROJECT_MANAGER":   ["+ certifies_object", "+ depends_on_chain",
                          "+ depended_by_chain", "+ evidence_bound_decisions"],
    "AUDITOR":           ["+ full_lifecycle_events", "+ hash_verify",
                          "+ export_chain_btn"],
  }
};
```

---

## 四、全局公共组件（所有角色共享）

### 4.1 🔴 [ONT] Ontology Explorer 侧栏

> 「操作即本体变更」的可视化证明。任何角色在任意 Dashboard 操作后，此图谱实时联动。

```
┌─────────────────────────────────────────────────────────────────┐
│ 🌐 对象图谱浏览器 · PROJ-2024-007              [折叠] [全屏]    │
├────────────────┬────────────────────────────────────────────────┤
│ 对象统计（实时）│                                                │
│ Asset: 24      │  [MDI-2024-001  主装配型架] ──展开──           │
│ Station: 8     │   ├─ PLACED_IN ──────────▶ [STATION_01]       │
│ Constraint: 347│   ├─ GOVERNED_BY ─────────▶ [C001 HARD ✅]    │
│ TrustToken: 5  │   │   └─ SOURCED_FROM ────▶ [SOP v3.1 P12]   │
│ Decision: 2    │   ├─ GOVERNED_BY ─────────▶ [C008 HARD ✅]    │
│ AuditLog: 247  │   └─ PART_OF ─────────────▶ [LC-202604-007]  │
│                │       └─ CERTIFIES ◀──────── [CP-C Token ✅]  │
│ [筛选对象类型] │           └─ EVIDENCE_BOUND_TO ◀── [DEC-001]  │
│ [搜索对象ID]   │                                                │
├────────────────┴────────────────────────────────────────────────┤
│ 💡 此视图与所有 Dashboard 双向实时联动                           │
│    拖拽画布 MDI-001 = 更新 PLACED_IN 关系的 position 属性        │
│    审核约束 C002 = 更新 C002 的 lifecycle_state + 追加审计边     │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 🔴 [ONT] Object Context Header（对象上下文头部）

> 每个 Dashboard 顶部展示"我正在操作的是哪个本体对象"。

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 对象上下文 ·  LayoutCandidate  [LC-202604-007]                            │
│ lifecycle: LOCKED 🔒  ·  version: v3.1.0  ·  hash: sha256:layoutC...abc  │
│ 创建: 布局工程师张工 · 2026-04-13 09:00  锁版: 项目经理张三 · 10:30       │
├──────────────────────────────────────────────────────────────────────────┤
│ 上游依赖（DEPENDS_ON 链）：                                               │
│ [SM-001 v1.3 LOCKED🔒]──SHAPES──▶[CS-001 v2.1 LOCKED🔒]──INFORMS──▶[当前]│
├──────────────────────────────────────────────────────────────────────────┤
│ ⚠️ 下游影响（修改当前对象将影响）：                                        │
│ ──SIMULATED_IN──▶ [SIM-007]  ──EVIDENCE_BOUND_TO──▶ [DEC-001 FINAL]      │
│ 如修改此对象，CP-C Token 将失效，SIM-007 + DEC-001 将进入 STALE 状态      │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.3 🔴 [ONT] 统一 Action Catalog 面板

> 右键任意对象 / 点击 Actions▼，展示该对象当前角色可执行的全部 Action。

```
[右键 Constraint C045]
┌──────────────────────────────────────────────────────────────┐
│ 对 Constraint [C045] 可执行的 Actions                        │
│ 对象当前状态：APPROVED                                       │
├──────────────────────────────────────────────────────────────┤
│ ✅ requestHumanReview(C045)     ← PROCESS_ENGINEER 可执行    │
│    → 将 C045 重新进入 UNDER_REVIEW 队列                      │
│    → AuditLog.append({event: "REVIEW_REQUESTED"})           │
├──────────────────────────────────────────────────────────────┤
│ 🔒 supersede(C045, newConstraintId)   ← PROCESS_ENGINEER     │
│    前置：需填写仲裁理由（≥10字）                              │
│    → 写入 SUPERSEDES 边到知识图谱                            │
├──────────────────────────────────────────────────────────────┤
│ ⚠️ escalateToHuman(C045)       ← PROCESS_ENGINEER / SYSTEM   │
│    → block_downstream = true，通知 SYSTEM_ADMIN              │
├──────────────────────────────────────────────────────────────┤
│ 以下 Actions 当前角色无权执行（灰色隐藏）                      │
│ ❌ invalidateDownstream  ← 仅 SYSTEM_ADMIN                   │
│ ❌ lockObject            ← 仅 APPROVER                       │
└──────────────────────────────────────────────────────────────┘
执行后自动追加 AuditLog：
{ actor: "user-process-eng", action: "supersede",
  target: "C045", result: "SUPERSEDES_C023_WRITTEN", timestamp: ... }
```

### 4.4 🔵 [LLM] AI 操作溯源卡（LLM 建议落地为 Ontology 变更）

> 每次 AI 建议被应用，展示此卡片，证明 LLM 操作也有 Ontology 追踪。

```
┌──────────────────────────────────────────────────────────────────┐
│ 🤖 AI 建议已执行                               [撤销] [查看详情] │
├──────────────────────────────────────────────────────────────────┤
│ 建议内容："将 MDI-2024-001 向北移动 800mm"                       │
│ 触发依据：Constraint [C045] · SOURCED_FROM · [MBOM v3.2 P12]    │
├──────────────────────────────────────────────────────────────────┤
│ 本次 AI 操作产生的 Ontology 变更（已写入图谱 + AuditLog）：       │
│                                                                  │
│ 变更1：Asset [MDI-2024-001]                                      │
│   mutateProperty: position_y: 7500mm → 8300mm (+800mm)         │
│   AuditLog: LOG-20260413-0847                                   │
│                                                                  │
│ 变更2：LayoutCandidate [LC-202604-007]                           │
│   mutateProperty: soft_violation_score: 0.23 → 0.18 (优化)     │
│   mutateProperty: logistics_path_total_m: 1240 → 1190          │
│   AuditLog: LOG-20260413-0848                                   │
│                                                                  │
│ AI Agent 身份：LLM_AGENT-Qwen2.5-72B · session: ctx-uuid-003   │
│ Link 追加：LLMAction[session-003] ──MODIFIED──▶ [LC-202604-007] │
└──────────────────────────────────────────────────────────────────┘
```

### 4.5 🔴 [ONT] TrustToken 对象详情页（点击任意 Token 进入）

```
┌───────────────────────────────────────────────────────────────────┐
│ TrustToken 对象详情                [复制Token ID] [查看图谱] [关闭]│
│ token_id: CP-C-uuid-20260413-002                                  │
│ token_type: LAYOUT_LOCK  ·  status: ✅ VALID                      │
│ issued_by: [User 布局工程师张工]  ·  issued_at: 2026-04-13 10:30  │
│ object_hash: sha256:layoutContentHash_abc123（SHA-256，防篡改）   │
├───────────────────────────────────────────────────────────────────┤
│ CERTIFIES（此 Token 为谁签发的证明）：                            │
│ ──CERTIFIES──▶ LayoutCandidate [LC-202604-007] v3.1.0            │
├───────────────────────────────────────────────────────────────────┤
│ DEPENDS_ON（此 Token 生效的前提，上游链）：                        │
│ ──DEPENDS_ON──▶ TrustToken [CP-A] SITEMODEL_LOCK ✅              │
│ ──DEPENDS_ON──▶ TrustToken [CP-B] CONSTRAINTSET_LOCK ✅           │
├───────────────────────────────────────────────────────────────────┤
│ DEPENDED_BY（此 Token 失效将影响，下游链）：                       │
│ ──DEPENDED_BY──▶ TrustToken [CP-D] SIM_APPROVAL ✅               │
├───────────────────────────────────────────────────────────────────┤
│ EVIDENCE_BOUND_IN（被哪些 Decision 快照引用）：                   │
│ ──EVIDENCE_BOUND_IN──▶ Decision [DEC-001] FINAL                  │
├───────────────────────────────────────────────────────────────────┤
│ 生命周期事件（Append-Only）：                                      │
│ 2026-04-13 10:30  ISSUED       布局工程师张工（lockObject）        │
│ 2026-04-13 11:00  CONSUMED     仿真工程师陈工（POST /sim/tasks）  │
│ 2026-04-13 14:30  SNAPSHOTTED  项目经理张三（DEC-001 快照）        │
└───────────────────────────────────────────────────────────────────┘
```

---

## 五、各角色 Dashboard 详细设计（本体论计算完整融合）

### 🔵 角色一：产线规划设计师（PRD-1 · S1_底图）

**本体论核心**：上传解析后，每个识别到的航空特有要素都在 Ontology 中完成 **Object 注册**（`AC-1-01-09`：调用 `GET /api/v1/ontology/objects?site_model_id=` 验证数量），属性面板展示的是 Ontology 对象而非原始 CAD 属性。

**界面布局：三栏 + 顶部工具栏**

```
顶部: [解析底图] [导出OpenUSD] [版本v1.3.0▼ Diff视图] [签发CP-A Token 🔒 APPROVER Only]
      [MCP Context: ctx-uuid-001]  [未识别图层: 13个 🔴]

┌──────────────────┬──────────────────────────────────┬───────────────────────┐
│ 左：文件 + 对象树 │ 中：3D语义画布（主操作区）            │ 右：Ontology属性面板   │
│                  │                                  │                       │
│ 📁 文件上传      │ [选择|拖拽|测距|碰撞检测|吊运层]     │ 🔴[ONT] 选中对象：     │
│ DWG/IFC/点云     │                                  │ CRANE-A               │
│                  │ ┌─────────厂房边界──────────────┐ │ objectType: CraneRunway│
│ 🗂 图层树         │ │ 🔵[PIT-001]  [MDI-001🟡]     │ │ ontology_object_id:   │
│                  │ │                               │ │ uuid-crane-a          │
│ ▼ 已识别 (487)   │ │ ████ RZ-001防爆 ████          │ │ lifecycle_state: ACTIVE│
│  ✅ 地坑层        │ │                               │ │ span_mm: 24000        │
│  ✅ 吊车梁层      │ │ ════CRANE-A════               │ │ rail_elevation_mm:    │
│  ✅ 型架基础层    │ │    [MDI-003]  [FOUND-001🟡]   │ │ 12000                 │
│ ▼ 未识别 13个🔴  │ └───────────────────────────────┘ │ max_load_kg: 50000    │
│  🔴 LAYER-423    │                                  │                       │
│                  │ ⚠️ 拖拽 MDI-001 中...            │ Links（本对象关联）：   │
│ 🔑 CP-A前置条件  │ 碰撞检测: 🔴 违规               │ 🔴[ONT]               │
│ ✅ SM001 坐标精度│ [PIT-001 TRAVERSE_PROHIBITED]    │ GOVERNS ──▶           │
│ ✅ SM002 障碍100%│ 0.1mm ≤ 临界精度                 │  [C008 CRANE_PATH]    │
│ ✅ SM003 ID对齐  │                                  │ ACCESSED_BY ──▶       │
│ ✅ SM004 地坑确认│                                  │  [MDI-2024-001]       │
│ ✅ SM005 禁区确认│                                  │                       │
│ ✅ SM006 吊车完整│                                  │ Actions▼              │
│ ✅ SM007 版本锁定│                                  │ [requestHumanReview]  │
│                  │                                  │ [lockObject🔒]        │
└──────────────────┴──────────────────────────────────┴───────────────────────┘
```

**🔴 [ONT] 本体论关键交互**：
- 拖拽设备时：`Asset.mutateProperty("position", newPos)` + 碰撞检测 → `AuditLog.append({event: "POSITION_CHANGED"})`
- 点击地坑：弹出约束配置弹窗，确认后 `GroundPit.mutateProperty("client_confirmed", true)` + CP-A SM004 前置条件自动更新为 ✅
- 标注未识别图层：`OntologyService.registerObject({type: "FixtureFoundation", ...})` → 图层树实时更新
- 签发 CP-A：调用 `lockObject(SM-001)` Action → SiteModel.lifecycle_state = LOCKED → TrustToken CP-A 创建，`CERTIFIES` Link 写入图谱

**🔵 [LLM] 角色专属对话场景**（AI输出落地为 Ontology 变更）：
- 「分析这个未识别图层」→ AI 建议标注类型 → 用户确认 → `OntologyService.registerObject()` 执行，AI操作追加 `LLM_AGENT --MODIFIED--> LayerObject`
- 「CP-A 还差什么条件？」→ AI 实时查询 `SiteModel.cp_a_preconditions`，精确列出未通过项
- 「为什么 CRANE-A 净高是 12000mm？」→ AI 溯源：`CraneRunway[CRANE-A].rail_elevation_mm` 来源于 DWG 图层 `CRANE-A_TRACK`，GCP 锚定精度 0.08mm

---

### 🟠 角色二：工艺工程师（PRD-2 · S2_工艺约束）

**本体论核心**：约束列表不是数据表格，是 **Constraint 对象列表**，每行展示对象的 `lifecycle_state`、`authority_level`，以及 `SOURCED_FROM`/`CONFLICTS_WITH`/`SUPERSEDES` 等 **Link**。知识图谱和约束列表是**同一份 Ontology 图谱的两种投影**，双向实时联动。

**界面布局：三栏 + 三 Tab**

```
顶部: [项目名] [CP-A: ✅ VALID · CP-A-uuid-003] [解析进度100%] [锁版CP-B🔒]
      Object Context Header：ConstraintSet [CS-001] · DRAFT · 347对象 · 5冲突(3已解)

┌──────────────────┬──────────────────────────────────┬──────────────────────┐
│ 左：文档 + 审核队列│    中：三Tab主工作区                │ 右：Ontology 溯源面板 │
│                  │                                  │                      │
│ 📁 文档上传      │ Tab1 🔴[ONT] Constraint 对象列表   │ 📄 原文溯源          │
│ ✅ MBD.CAT       │                                  │ doc_id: doc-uuid-456  │
│ ✅ SOP.pdf       │ ┌────────────────────────────────┐│ 文档: MBOM v3.2.xlsx  │
│ ✅ MBOM导入      │ │C045  SOFT  SPATIAL  MBOM  0.92 ││ 第12页 §5.2.3        │
│                  │ │lifecycle: APPROVED              ││ "各站位间物流路径     │
│ 📊 三层处理状态  │ │Links:                           ││  建议不超过1200mm"   │
│ 🔵 PMI引擎 ✅   │ │ SOURCED_FROM──▶[MBOM v3.2 P12] ││                      │
│ 🟡 LLM解析 ✅   │ │ CONFLICTS_WITH──▶[C023]         ││ 3D PMI 定位          │
│ 🔴 人工审核 ⏳  │ │ SUPERSEDES──▶[C023 SUPERSEDED]  ││ ┌──────────────────┐ │
│                  │ │ Actions▼                        ││ │ CATIA://model/   │ │
│ 📋 审核队列      │ │ [requestHumanReview][supersede] ││ │ wing_skin.CAT    │ │
│ 28条待审🟡       │ └────────────────────────────────┘│ │ #PMI-00234        │ │
│ 3对冲突🔴        │                                  │ └──────────────────┘ │
│                  │ Tab2 🔴[ONT] 知识图谱（非独立组件）│                      │
│ 🔑 Gate B条件    │ [AntV G6 · 直接渲染 Ontology 图谱]│ 🔴[ONT] 人工审核操作  │
│ ✅ 无未仲裁冲突  │                                  │ C002 · confidence:0.75│
│ ✅ 溯源率≥99%   │ HARD边=红  SOFT边=橙虚线           │ authority: LLM        │
│ ✅ HARD约束全覆  │ SUPERSEDES边=蓝色(仲裁结果)        │ lifecycle: UNDER_REVIEW│
│ ✅ 审核队列空    │ CONFLICTS_WITH边=紫色闪烁          │                      │
│ ✅ Z3 SAT通过   │                                  │ [✅确认→APPROVED]     │
│ ✅ 低置信度=0   │ 拖拽两节点连线                     │ [❌驳回→REJECTED]     │
│                  │ → 弹出创建约束面板                │                      │
│ [签发CP-B Token] │ → 调用OntologyService.createLink │ 执行后：              │
│ 🔒 条件全满足时亮│ → AuditLog.append(LINK_CREATED)  │ lifecycle_state变更   │
│                  │                                  │ AuditLog追加          │
│                  │ Tab3 冲突仲裁（图谱视图子集）      │ 知识图谱实时联动      │
│                  │ CONF-001: C023 vs C045           │                      │
│                  │ 推荐C045（MBOM>SOP，规则BR-02）   │                      │
│                  │ [采纳→写入SUPERSEDES边]           │                      │
└──────────────────┴──────────────────────────────────┴──────────────────────┘
```

**🔴 [ONT] 本体论关键交互**：
- 审核确认：`Constraint.mutateProperty("lifecycle_state", "APPROVED")` + `Constraint.createLink("REVIEWED_BY", currentUser)` + `AuditLog.append()`
- 仲裁采纳（AC-2-06-2）：① C045保持APPROVED ② C023.lifecycle_state = "SUPERSEDED" ③ **知识图谱写入 `SUPERSEDES` 边** ④ 仲裁理由写入不可篡改 AuditLog
- 知识图谱连线：`OntologyService.createLink({type: "GOVERNED_BY", source: Asset[MDI-001], target: Constraint[C001]})` → 约束列表 Tab1 实时刷新

**🔵 [LLM] 角色专属对话场景**：
- 「C045 为什么优先级高于 C023？」→ AI 查询 `C045.authority_level (MBOM) > C023.authority_level (SOP)` + 仲裁规则 BR-02，返回带 Link 溯源的解释
- 「Gate B 差什么条件？」→ AI 实时查询 ConstraintSet 的 `gate_checks` 对象，逐条列出
- 「帮我理解这个知识图谱里连接最多的节点」→ AI 调用图拓扑分析：「MDI-2024-001 连接了 8 条 GOVERNED_BY 边，是约束密度最高的工装」

---

### 🟢 角色三：布局工程师（PRD-3 · S2_LAYOUT）

**本体论核心**：画布上的每个工装图标是 `Asset` 对象的坐标投影，拖拽 = `Asset.mutateProperty("position")` + 实时触发硬约束验证。右侧违规面板直接显示 `Constraint[C045].SOURCED_FROM.Document.page` 溯源。

**界面布局：三栏 + Object Context Header**

```
Object Context Header: LayoutCandidate [LC-202604-007] · VALIDATED · v3.1.0
上游: [SM-001 LOCKED🔒]──[CS-001 LOCKED🔒]  下游影响: [SIM-007]──[DEC-001]

顶部工具: [会话S-007] [SiteModel v1.3🔒] [ConstraintSet v2.1🔒] [Gate A✅ Gate B✅]
         [自动生成候选↓] [吊运干涉检测] [对比方案] [申请锁版🔒]

┌──────────────────┬──────────────────────────────────┬──────────────────────┐
│ 左：会话 + KPI    │ 中：布局画布（Ontology 投影）        │ 右：约束与违规对象面板│
│                  │                                  │                      │
│ 当前方案：       │ [工具栏] 拖拽中: MDI-2024-001      │ 🔴硬约束违规 [0] ✅  │
│ LC-202604-007    │                                  │                      │
│ hard_violation:0 │ ┌───────────厂房边界───────────┐ │ 🟡软约束警告 [2]     │
│ soft_score: 0.23 │ │[MDI-001🟡] [MDI-002🟡]      │ │                      │
│ space_util: 74%  │ │                               │ │ 🔴[ONT] 对象卡片：   │
│ crane_check: ✅  │ │ ████RZ-001防爆████            │ │ Constraint [C045]    │
│                  │ │                               │ │ type: SOFT           │
│ 已生成候选: 20   │ │ 🔵PIT-001  [FOUND-001]        │ │ lifecycle: APPROVED  │
│ [查看全部对比↗]  │ │                               │ │ Links:               │
│                  │ │ ════════CRANE-A════════       │ │ GOVERNED_BY ◀─       │
│ Gate C 条件：    │ └───────────────────────────────┘ │  Asset[MDI-001]      │
│ ✅ hard_viol=0   │                                  │ SOURCED_FROM ──▶     │
│ ✅ coverage≥95%  │ 位移: +800mm(北)                  │  Doc[MBOM v3.2 P12]  │
│ ✅ crane_done    │ 验证: ✅ C045 软约束score改善      │                      │
│ ⏳ 待PM审批      │ 碰撞: 无                          │ Actions▼             │
│                  │                                  │ [查看原文] [溯源跳转] │
│ [申请锁版🔒]     │ 🤖 AI建议：向北移 800mm           │ [requestHumanReview] │
│ (条件全满足高亮)  │ [一键应用→ONT变更+AuditLog]       │                      │
└──────────────────┴──────────────────────────────────┴──────────────────────┘
```

**方案对比矩阵子页**（US-3-05，每行=一个 LayoutCandidate Ontology 对象）：

```
LayoutCandidate 对象比选（仅显示 lifecycle_state ≠ ARCHIVED 且 hard_violation=0 的方案）
┌──────────────┬─────────────┬─────────────────┬─────────────┐
│ 指标          │ LC-001       │ LC-002⭐          │ LC-003       │
│ object_hash  │ sha256:aaa  │ sha256:abc123   │ sha256:bbb  │
│ lifecycle    │ VALIDATED   │ LOCKED🔒        │ VALIDATED   │
│ hard_viol    │ 0 ✅        │ 0 ✅            │ 0 ✅        │
│ soft_score   │ 0.68        │ 0.23 ▲          │ 0.41        │
│ space_util   │ 71%         │ 74% ▲           │ 68%         │
│ crane_check  │ ✅          │ ✅              │ ✅          │
│ CP-C Token   │ 无          │ CP-C-002 ✅     │ 无          │
└──────────────┴─────────────┴─────────────────┴─────────────┘
Actions▼（对 LC-001）: [lockObject🔒→申请Gate C] [snapshotObject] [markRecommended]
```

**🔴 [ONT] 本体论关键交互**：
- 「申请锁版」：调用 `lockObject(LC-202604-007)` → 系统自动检查 Gate C 3项条件 → 通知 PM 审批 → PM 批准后 `LayoutCandidate.lifecycle_state = LOCKED` + `LAYOUT_LOCK` Token 创建 + `CERTIFIES` Link 写入
- 违规报告每条展示 `constraint_id + SOURCED_FROM.document + page`（PRD-3 US-3-03 AC2 精确要求）
- 违规修复后：`AuditLog.append({layout_id, constraint_id, violation_type, resolved_at})` （AC4 精确要求）

---

### 🟣 角色四：仿真工程师（PRD-4 · S3_SIM）

**本体论核心**：仿真参数导入时，`operation_id` 必须能在 Ontology 中找到对应 `Operation` 对象（`AC-4-02-5` 精确要求）。`SimResult` 生成时写入 `object_hash`。Gate D 签发后，`SimResult.lifecycle_state = APPROVED` + `SIM_APPROVAL` Token 创建。

**界面布局：两段式（配置折叠 + 结果展开）**

```
Object Context Header: SimResult [SIM-007] · APPROVED · v1.0.0
对应布局: LayoutCandidate [LC-202604-007] · LOCKED🔒 · CP-C-uuid-002 VALID✅

顶部: [Gate C Token: CP-C-uuid-002 ✅] [运行时长: 12min] [申请Gate D ▼]

═══ 仿真配置区（已完成，折叠）═══
布局: ✅ LC-202604-007 v3.1.0 (layout_hash已绑定)
参数: PARAM-SET-001 · 🔴[ONT] operation_id全部在Ontology中验证✅
      A03-001 · operation_id: op-uuid-001 · 正态2.0h σ=0.1
      A03-002 · operation_id: op-uuid-002 · 韦布尔3.5h α=3.5 β=1.2
      [从ConstraintSet自动填充: Operation.mean_duration_s ← CS-001]
MC样本: 500 · 班制: 2班×8h · sim_scenario_version: v1.0.0 (锁定)

═══ 仿真结果区 · SIM-007 · object_hash: sha256:simResultHash_def456 ═══
┌────────────────────────┬──────────────────────────────────────────────┐
│ 关键 KPI               │ 站位利用率热力图（叠加在布局平面图Ontology投影上）│
│ 平均节拍: 68.5h ✅     │ [S01 62%][S02 71%][S03 92%🔴][S04 68%]      │
│ P95节拍: 73.2h ⚠️     │ [S05 65%][S06 58%][S07 75%][S08 61%]        │
│ 瓶颈: STATION_05 🔴   │ 🔴[ONT] 热力图节点 = Station对象 · 可点击     │
│ 年产能: 42架/年        │ 点击 STATION_05 → Station对象详情            │
│ hard_violation: 0 ✅  │   PLACED_IN ◀── [MDI-001, MDI-002]           │
│                        │   APPLIES_TO ◀── [C001, C008]               │
├────────────────────────┴──────────────────────────────────────────────┤
│ 节拍分布 (MC n=500): ████████████░░░  P50:66.8h  P