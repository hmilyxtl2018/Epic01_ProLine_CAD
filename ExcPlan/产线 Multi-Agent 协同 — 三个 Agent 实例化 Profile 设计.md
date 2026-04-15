

# 产线 Multi-Agent 协同闭环系统 — 三个 Agent 实例化 Profile 设计

**文档版本**: v1.0  
**创建日期**: 2026-04-15  
**基线案例**: 航空工艺产线 FAL 布局优化（wing_fal.dwg）

---

## 核心设计原则

1. **实例化策略**：每个 Agent 为**独立容器化服务**，支持水平扩展，通过 mcp_context 完整链路追踪
2. **Action Flow**：Step-wise 设计，每一步都在 mcp_context 中记录，便于审计与故障诊断
3. **资源编排**：基于输入规模（CAD 文件大小、约束数、搜索空间）动态分配计算资源
4. **收敛定义**：多层次收敛准则（硬约束 100% 满足 + 软约束单调递增 + Δ threshold）

---

## Agent1 — ParseAgent（本体识别 / 语义抽取）

### 1.1 Agent 定义与职责

| 属性 | 值 |
|------|-----|
| **Agent ID** | `agent-parse-v1.0` |
| **Name** | ParseAgent / 语义识别 Agent |
| **Role** | CAD 解析 + 几何修补 + 本体映射 |
| **Owner** | 系统前端（CAD 导入模块） |
| **Status** | 首轮执行 Agent；阻塞后续流程 |
| **Input Format** | CAD 文件 (DWG/IFC/STEP/DXF) + 坐标系设置 |
| **Output Format** | SiteModel + Ontology Graph + Confidence Stats |
| **Expected Latency** | < 5s (p95) — 示例基线 2.3s |

---

### 1.2 实例化资源模型

#### 计算资源需求

```yaml
# 基于 CAD 文件大小的资源动态配置
resource_profile:
  small_file:  # < 50MB
    cpu: "0.5"
    memory: "512Mi"
    timeout: 3s
    
  medium_file:  # 50-200MB
    cpu: "2"
    memory: "2Gi"
    timeout: 8s
    
  large_file:  # 200-500MB
    cpu: "4"
    memory: "8Gi"
    timeout: 15s

# 示例：wing_fal.dwg (~30MB) → small_file profile
```

#### 依赖组件与库

| 组件 | 用途 | 版本 |
|------|------|------|
| **DWG Parser** | DWG (R14–R2024) 格式解析 | OPEN_DESIGN_ALLIANCE |
| **IFC Parser** | IFC 2×3/4 模型读取 | IfcOpenShell |
| **Geometry Repair** | 拓扑闭合、重复消除 | CGAL / TopologySuite |
| **Ontology Engine** | 本体映射与推理 | Protégé / OWL 2.0 |
| **Confidence Model** | 置信度评分 | Rule-based + lightweight ML |

#### 部署拓扑

```
┌─────────────────────────────────────────────────┐
│  ParseAgent Service (Docker Container)          │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │ CAD File Input Queue (RabbitMQ/Kafka)    │  │
│  └──────────────────────────────────────────┘  │
│           ↓                                     │
│  ┌──────────────────────────────────────────┐  │
│  │ CAD Parsing Pipeline                     │  │
│  │  • Format Detection                      │  │
│  │  • Version Conversion                    │  │
│  │  • Geometry Extraction                   │  │
│  └──────────────────────────────────────────┘  │
│           ↓                                     │
│  ┌──────────────────────────────────────────┐  │
│  │ Geometry Repair Engine                   │  │
│  │  • Topology Closure                      │  │
│  │  • Deduplicate                           │  │
│  │  • Coordinate Normalization              │  │
│  └──────────────────────────────────────────┘  │
│           ↓                                     │
│  ┌──────────────────────────────────────────┐  │
│  │ Ontology Mapper                          │  │
│  │  • Asset Classification                  │  │
│  │  • Semantic Link Generation              │  │
│  │  • Confidence Scoring                    │  │
│  └──────────────────────────────────────────┘  │
│           ↓                                     │
│  ┌──────────────────────────────────────────┐  │
│  │ SiteModel + Graph Output Queue           │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

### 1.3 Action Flow — 分步执行流程

#### 步骤 1: CAD 文件预处理 (Pre-parsing)
**输入**: `{cad_file, format, coord_system}`  
**输出**: `{normalized_geometry, geometry_stats}`  
**耗时**: ~400ms (wing_fal.dwg)

```
1.1 Format Detection
    • Read file header & magic bytes
    • Match DWG version (R14 vs. R2024)
    → Status: SUCCESS / UNSUPPORTED_FORMAT
    
1.2 Geometry Extraction
    • Parse all entities (LWPOLYLINE, CIRCLE, 3DSOLID, etc.)
    • Build spatial index (R-Tree)
    → Entity count, Bounding box
    
1.3 Coordinate System Normalization
    • Detect WCS/UCS (current, reference)
    • Transform to WCS ± mm units
    • Center to origin if needed
    → Normalized coords, Transform matrix
    
1.4 Geometry Integrity Check
    • Closed vs. open polylines
    • Self-intersections
    • Duplicate/overlapping geometry
    → Repair candidates list
```

**Record in MCP Context**:
```json
{
  "step": "pre_parse",
  "timestamp": "2026-04-14T09:12:34.567Z",
  "actions": [
    {"action": "format_detect", "result": "DWG_R2024", "latency_ms": 45},
    {"action": "entity_extract", "count": 127, "latency_ms": 180},
    {"action": "coord_normalize", "ucs_transforms": 3, "latency_ms": 95},
    {"action": "geometry_check", "integrity_score": 0.92, "repairs": 8, "latency_ms": 80}
  ],
  "total_latency_ms": 400
}
```

---

#### 步骤 2: 本体资产识别 (Asset Recognition)
**输入**: `{normalized_geometry, ontology_v}`  
**输出**: `{assets[], asset_guid, type, coords, footprint, ports[]}`  
**耗时**: ~1,200ms (wing_fal.dwg)

```
2.1 Entity Classification
    FOR each geometry entity:
      • Match layer name → Ontology class (Equipment, Conveyor, LiftingPoint, etc.)
      • If no match → UNRESOLVED (confidence < threshold)
      • Extract bounding box → Footprint (length, width, height)
    → Asset candidates list
    
2.2 Geometric Parameter Extraction
    FOR each asset candidate:
      • Center point: (x, y, z) 
      • Footprint: L×W (mm)
      • Key points (吊点, WELD_TIP, etc.) → Port extraction
      • Polyline segments: count & direction
    → Asset geometry record
    
2.3 Confidence Scoring (Rule-based)
    confidence = 0.3×layer_match + 0.3×geometry_validation + 0.2×port_detection + 0.2×reference_check
    
    Examples:
      焊接枪 A: layer="EQUIPMENT_WELD" (0.95) + geometry_valid (1.0) + WELD_TIP found (0.95) + ref_found (0.95)
        → confidence = 0.3×0.95 + 0.3×1.0 + 0.2×0.95 + 0.2×0.95 = 0.97 ✓
      
      吊点 P1: layer="STRUCT_LIFT_?" (inferred, 0.70) + geometry_valid (0.8) + bearing_info (0.9) + ref uncertain (0.7)
        → confidence = 0.3×0.70 + 0.3×0.8 + 0.2×0.9 + 0.2×0.7 = 0.79 ⚠ (LOW)
    
    IF confidence < 0.90:
      → Mark as "NEED_REVIEW", assign to human review queue
      → Include "标记复核 / 修正类型 / 修正坐标" UI hooks

2.4 Asset Finalization
    • Assign unique asset_guid (MD5 hash of layer + coords + type)
    • Create asset record with all metadata
    → Assets: [MDI-2024-001, MDI-2024-002, MDI-2024-003, LIFT-001]
```

**Record in MCP Context**:
```json
{
  "step": "asset_recognition",
  "timestamp": "2026-04-14T09:12:35.800Z",
  "actions": [
    {"action": "classification", "candidates": 7, "recognized": 4, "unresolved": 0},
    {"action": "geometry_extract", "assets": 4, "ports": 6},
    {"action": "confidence_score", "avg": 0.94, "low_confidence": 1, "latency_ms": 1200}
  ]
}
```

---

#### 步骤 3: 语义关系映射 (Ontology Linking)
**输入**: `{assets[], ontology_schema}`  
**输出**: `{ontology_graph, links[]}`  
**耗时**: ~600ms

```
3.1 Entity-to-Ontology Mapping
    FOR each asset:
      • Map to Ontology class: Equipment | Conveyor | LiftingPoint | Zone | Constraint | Standard
      • Create RDF triple: <asset_guid, rdf:type, Ontology:Class>
    
3.2 Relationship Discovery (Rule + Heuristic)
    Link types: APPLIES_TO | GOVERNED_BY | FEEDS | PAIR_WITH | TRAVERSES | LOCATED_IN
    
    Examples from wing_fal:
      • 焊接枪 A APPLIES_TO Station-01
      • 焊接枪 B PAIR_WITH 焊接枪 A (proximity-based, distance 480mm)
      • 传送带 Main TRAVERSES Zone-Main
      • 传送带 Main FEEDS Station-01, Station-02
      • C-001 (约束) APPLIES_TO MDI-2024-001, MDI-2024-002
      • C-001 GOVERNED_BY HB/Z 223-2013 (标准参考)

3.3 Ontology Graph Serialization
    Export as RDF/Turtle or JSON-LD:
    {
      "@context": "http://aeroontology.org/v1.0",
      "@graph": [
        {
          "@id": "MDI-2024-001",
          "@type": "aero:WeldingGun",
          "aero:appliesTo": {"@id": "Station-01"},
          "aero:governedBy": {"@id": "C-001"}
        },
        ...
      ]
    }

3.4 Graph Statistics
    • Nodes: 7 (Assets + Zones + Constraints + Standards)
    • Links (Edges): 9
    • Entity Types: 5
    • Average confidence: 94%
    → Output: Ontology Stats
```

**Record in MCP Context**:
```json
{
  "step": "ontology_linking",
  "timestamp": "2026-04-14T09:12:36.500Z",
  "ontology_stats": {
    "nodes": 7,
    "links": 9,
    "entity_types": 5,
    "confidence_avg": 0.94,
    "low_confidence_items": [
      {"asset_guid": "LIFT-001", "confidence": 0.85, "reason": "layer_inferred"}
    ]
  }
}
```

---

#### 步骤 4: 输出序列化与生成 Site Model
**输入**: `{assets, ontology_graph, stats}`  
**输出**: `{site_model_id, SiteModel object}`  
**耗时**: ~150ms

```
4.1 Site Model Creation
    SiteModel {
      site_model_id: "SM-001"        # Unique identifier
      cad_source: {
        filename: "wing_fal.dwg",
        sha256: "a3b8..f2e1",
        format: "DWG_R2024",
        coord_system: "WCS",
        import_timestamp: "2026-04-14T09:12:34.567Z"
      },
      assets: [ Asset_1, Asset_2, ..., Asset_4 ],
      ontology_graph: {...},
      geometry_integrity_score: 0.92,
      statistics: {
        total_assets: 4,
        recognized_assets: 4,
        unresolved_count: 0,
        avg_confidence: 0.94
      }
    }

4.2 Persistence
    • Store SiteModel in structured database (PostgreSQL + JSON store, or graph DB)
    • Index by site_model_id, cad_source.sha256
    • Enable quick retrieval for Agent2, Agent3
```

---

### 1.4 Agent1 输入/输出 Schema (完整契约)

#### 输入 Schema (input_schema)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "cad_file": {
      "type": "object",
      "properties": {
        "filename": {"type": "string", "pattern": "\\.(dwg|ifc|step|dxf)$"},
        "file_content": {"type": "string", "format": "binary"},
        "size_bytes": {"type": "integer", "maximum": 536870912}  // 500MB
      },
      "required": ["filename", "file_content"]
    },
    "format": {
      "type": "string",
      "enum": ["DWG", "IFC", "STEP", "DXF", "AUTO"]
    },
    "coord_system": {
      "type": "string",
      "enum": ["WCS", "UCS", "AUTO"],
      "default": "AUTO"
    },
    "options": {
      "type": "object",
      "properties": {
        "preprocess": {"type": "boolean", "default": true},
        "ontology_version": {"type": "string", "default": "AeroOntology-v1.0"},
        "confidence_threshold": {"type": "number", "minimum": 0.5, "maximum": 1.0, "default": 0.90},
        "geometry_precision_mm": {"type": "number", "default": 0.01}
      }
    }
  },
  "required": ["cad_file", "format"]
}
```

#### 输出 Schema (output_schema)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "site_model_id": {"type": "string", "pattern": "^SM-[0-9]{3,}$"},
    "assets": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "asset_guid": {"type": "string"},
          "type": {"type": "string", "enum": ["Equipment", "Conveyor", "LiftingPoint", "Zone", "Other"]},
          "coords": {
            "type": "object",
            "properties": {
              "x": {"type": "number"},
              "y": {"type": "number"},
              "z": {"type": "number"}
            }
          },
          "footprint": {
            "type": "object",
            "properties": {
              "length_mm": {"type": "number"},
              "width_mm": {"type": "number"},
              "height_mm": {"type": "number"}
            }
          },
          "ports": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "port_name": {"type": "string"},
                "coords": {"type": "object"}
              }
            }
          },
          "confidence": {"type": "number", "minimum": 0, "maximum": 1},
          "layer": {"type": "string"}
        }
      }
    },
    "links": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source_guid": {"type": "string"},
          "target_guid": {"type": "string"},
          "link_type": {"type": "string", "enum": ["APPLIES_TO", "GOVERNED_BY", "FEEDS", "PAIR_WITH", "TRAVERSES", "LOCATED_IN"]},
          "metadata": {"type": "object"}
        }
      }
    },
    "unrecognized_count": {"type": "integer"},
    "geometry_integrity_score": {"type": "number", "minimum": 0, "maximum": 1},
    "statistics": {
      "type": "object",
      "properties": {
        "total_entities_parsed": {"type": "integer"},
        "low_confidence_items": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "asset_guid": {"type": "string"},
              "confidence": {"type": "number"},
              "reason": {"type": "string"}
            }
          }
        }
      }
    }
  },
  "required": ["site_model_id", "assets", "links", "geometry_integrity_score"]
}
```

---

### 1.5 编排与依赖管理

#### 触发条件

```yaml
trigger_condition: |
  CAD file uploaded (REST endpoint: /api/v1/import_cad)
  OR Message received on queue: input.cad_import_topic

execution_policy:
  priority: HIGH
  retry_strategy:
    max_attempts: 3
    backoff: exponential (1s, 2s, 4s)
    retry_on: [TIMEOUT, RESOURCE_EXHAUSTED]
```

#### 链路超时与时限

```yaml
step_1_timeout: 1s    # Pre-parsing
step_2_timeout: 3s    # Asset recognition
step_3_timeout: 2s    # Ontology linking
step_4_timeout: 1s    # Serialization
total_timeout: 8s     # Overall SLO
```

#### 故障恢复与降级

```yaml
failure_modes:
  - name: "Format_Not_Supported"
    severity: "ERROR"
    action: "HALT"
    message: "Unsupported CAD format. Supported: DWG, IFC, STEP, DXF"
  
  - name: "Geometry_Corrupt"
    severity: "WARNING"
    action: "CONTINUE_WITH_REPAIR"
    repair_strategy: "AUTO_TOPOLOGY_REPAIR"
    confidence_penalty: 0.15
  
  - name: "Low_Confidence_Assets"
    severity: "INFO"
    action: "QUEUE_FOR_MANUAL_REVIEW"
    review_threshold: 0.90
    ui_hook: "mark_review_button"
```

---

### 1.6 收敛定义与完成准则

#### Agent1 执行完成条件

```yaml
convergence_criteria:
  - name: "All_Entities_Processed"
    definition: "unrecognized_count == 0 OR (unrecognized_count / total_entities) < 0.05"
    threshold: 95%
  
  - name: "Confidence_Threshold"
    definition: "avg_confidence >= 0.90 OR low_confidence_items <= 2"
    threshold: 0.90
  
  - name: "Geometry_Integrity"
    definition: "geometry_integrity_score >= 0.85"
    threshold: 0.85
  
  - name: "Latency_SLO"
    definition: "total_execution_time <= 8s"
    threshold: 8000ms

completion_status:
  - status: "SUCCESS"
    conditions: "All convergence criteria met"
    next_step: "Trigger Agent2"
  
  - status: "SUCCESS_WITH_WARNINGS"
    conditions: "Geometry_Integrity or low_confidence_items slightly below threshold, but processable"
    action: "Generate human review queue + proceed to Agent2 with flags"
  
  - status: "FAILURE"
    conditions: "Format_Not_Supported OR critical geometry corruption"
    action: "Halt & return error to user"
```

#### 示例执行日志

```json
{
  "mcp_context_id": "ctx-7f3a-4e81-b2c9-001",
  "agent": "ParseAgent / AeroSemantic-v2",
  "execution_summary": {
    "status": "SUCCESS",
    "total_latency_ms": 2340,
    "step_breakdown": [
      {"step": "pre_parse", "latency_ms": 400, "status": "SUCCESS"},
      {"step": "asset_recognition", "latency_ms": 1200, "status": "SUCCESS"},
      {"step": "ontology_linking", "latency_ms": 600, "status": "SUCCESS"},
      {"step": "serialization", "latency_ms": 140, "status": "SUCCESS"}
    ],
    "convergence_metrics": {
      "entities_processed": "4/4 (100%)",
      "avg_confidence": 0.94,
      "low_confidence_items": 1,
      "geometry_integrity_score": 0.92
    },
    "output": {
      "site_model_id": "SM-001",
      "assets_count": 4,
      "links_count": 6,
      "unrecognized": 0
    }
  }
}
```

---

## Agent2 — ConstraintAgent（约束风险识别 / 合规检查）

### 2.1 Agent 定义与职责

| 属性 | 值 |
|------|-----|
| **Agent ID** | `agent-constraint-v1.0` |
| **Name** | ConstraintAgent / 约束诊断 Agent |
| **Role** | 约束检查 + 冲突识别 + 改进建议生成 |
| **Trigger** | Agent1 SUCCESS completion |
| **Input** | SiteModel + Constraint Set (CS-001) |
| **Output** | Violations + Soft Scores + Reasoning Chain |
| **Expected Latency** | < 3s (p95) — 示例基线 1.9s |

---

### 2.2 实例化资源模型

#### 计算资源需求

```yaml
resource_profile:
  small_model:  # < 10 assets
    cpu: "1"
    memory: "1Gi"
    timeout: 2s
    z3_solver_memory: "500Mi"
    
  medium_model:  # 10-50 assets
    cpu: "2"
    memory: "4Gi"
    timeout: 5s
    z3_solver_memory: "2Gi"
    
  large_model:  # 50+ assets
    cpu: "4"
    memory: "8Gi"
    timeout: 10s
    z3_solver_memory: "4Gi"

# 示例：wing_fal (4 assets, 15 constraints) → small_model profile
```

#### 依赖组件与库

| 组件 | 用途 | 版本 |
|------|------|------|
| **Z3 Theorem Prover** | SAT/SMT 求解（硬约束） | z3-4.12 |
| **Rule Engine** | 规则执行 + 推理 | Drools / Jess |
| **Constraint Store** | 约束库管理 | PostgreSQL + JSON |
| **Reasoning Logger** | 推理链记录 | Custom tracer |

#### 部署拓扑

```
┌─────────────────────────────────────────────────────────┐
│  ConstraintAgent Service (Docker Container)             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │ SiteModel Input Queue (from Agent1)                │ │
│  └────────────────────────────────────────────────────┘ │
│           ↓                                              │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Constraint Set Loader (CS-001)                     │ │
│  │  • Load PRD-3 规范 (硬约束)                         │ │
│  │  • Load SOP 工艺规程 (软约束)                       │ │
│  │  • Load 标准库 (HB/Z 223-2013, etc.)               │ │
│  └────────────────────────────────────────────────────┘ │
│           ↓                                              │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Hard Constraint Checker (Z3 SAT)                   │ │
│  │  • Symbolic constraint encoding                    │ │
│  │  • Z3 solver invocation                            │ │
│  │  • Conflict analysis & UNSAT core                  │ │
│  └────────────────────────────────────────────────────┘ │
│           ↓                                              │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Soft Constraint Evaluator                          │ │
│  │  • Compute soft constraint scores                  │ │
│  │  • Quantize to [0, 1] range                        │ │
│  │  • Generate improvement suggestions                │ │
│  └────────────────────────────────────────────────────┘ │
│           ↓                                              │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Violation Report Generator                         │ │
│  │  • Aggregate hard + soft results                   │ │
│  │  • Create reasoning chain                          │ │
│  │  • Format recommendations                          │ │
│  └────────────────────────────────────────────────────┘ │
│           ↓                                              │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Output Queue → Agent3                              │ │
│  └────────────────────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

### 2.3 Action Flow — 分步执行流程

#### 步骤 1: 约束集加载 (Constraint Set Loading)
**输入**: `{site_model_id, constraint_set_id: "CS-001"}`  
**输出**: `{hard_constraints[], soft_constraints[], authority_refs[]}`  
**耗时**: ~200ms

```
1.1 Constraint Set Retrieval
    • Query constraint database: WHERE constraint_set_id = "CS-001"
    • Result: {version: "v3.2", last_updated: "2026-04-01", revision: 15}

1.2 Constraint Categorization
    Hard Constraints (MUST satisfy):
      • C-001: 设备间距 (MDI-2024-001 ↔ MDI-2024-002 ≥ 500mm)
        Source: PRD-3 §2.1.4 · Authority: PMI_ENGINE (level=0)
      
      • C-002: 吊运高度 (≤ 8m)
        Source: PRD-3 §2.2.1 · Authority: PMI_ENGINE (level=0)
      
      ... (12 hard constraints total)
    
    Soft Constraints (SHOULD optimize):
      • C-045: 物流路径利用率 (≥ 0.85)
        Source: SOP 蒙皮装配工艺规程 §6.5 · Authority: SOP/LLM (level=3)
        Weight: 0.30 (in scoring function)
      
      • C-046: 扩展性评分 (≥ 0.70)
        Source: 内部工艺指南 · Authority: ENG_TEAM (level=2)
        Weight: 0.10
      
      ... (2 soft constraints)

1.3 Constraint Graph Construction
    • Build constraint graph where nodes = assets, edges = constraints
    • Compute constraint-asset dependency matrix
    → Used for efficient violation analysis

1.4 Authority & Traceability
    • Map constraints to source documents (PRD, SOP, Standard)
    • Attach regulatory references (HB/Z 223-2013, 航空焊接安全标准)
    • Store audit trail: who approved constraint set, when, version
```

**Record in MCP Context**:
```json
{
  "step": "constraint_loading",
  "timestamp": "2026-04-14T09:12:37.000Z",
  "constraint_set": {
    "id": "CS-001",
    "version": "v3.2",
    "hard_constraints_count": 12,
    "soft_constraints_count": 2,
    "total_constraints": 14,
    "authorities": ["PRD-3", "SOP", "HB/Z 223-2013"]
  }
}
```

---

#### 步骤 2: 硬约束检查 (Hard Constraint Verification via Z3)
**输