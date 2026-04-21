# ParseAgent v1.0 GA — 实施执行计划 (S1-S4)

**版本**: 1.0  
**创建日期**: 2026-04-20  
**Owner**: ParseAgent 工程负责人  
**关联文档**:
- [agents/parse_agent/agent.json](../agents/parse_agent/agent.json) — Claude AgentDefinition 契约
- [agents/parse_agent/gold/jijia_gold.yaml](../agents/parse_agent/gold/jijia_gold.yaml) — Gold 锚点
- [ExcPlan/parse_agent_board.html](parse_agent_board.html) — 进度看板

---

## 0. TL;DR

当前 **Phase 4.6** 已完成: gold=0.8267, LLM-judge=0.301, 5 个 Stage Gate 部分通过。
GA 目标: **gold ≥ 0.92**, **LLM-judge ≥ 0.45**, CI 防回退生效, 与 Orchestrator 联调通过。

按 ROI 排 4 个 Sprint, 总工时 **8-9 个工作日**:

| Sprint | 工时 | 退出 Gate | 主战场 |
|---|---|---|---|
| **S1** 词表 + CI | 1d | gold ≥ 0.88 + CI 跑通 | L3.2 / L5.4 / L6.4 / L1.3 |
| **S2** LLM 兜底 | 2-3d | LLM-judge ≥ 0.40, H5 reject<5% | L3.3 / L3.4 / L3.5 / L3.7 |
| **S3** 几何/链路 | 2d | gold ≥ 0.92 + range pass=1.0 | L2.2 / L2.3 / L4.2 / L4.3 / L4.5 |
| **S4** 工程化 | 3d | Orchestrator 端到端跑通 | L7.1 / L7.3 / L7.4 / L7.5 |

---

## 1. 进度基线 (2026-04-20)

| Stage | 进度 | 已完成 | 剩余关键 task |
|---|---|---|---|
| L1 输入与格式 | 90% ✅ | DWG/DXF 探测 + ODA 降级 | R12-R2018 全版本回归 (1.3) |
| L2 几何与坐标 | 50% 🟡 | 坐标归一化 | INSERT 矩阵展开 (2.2) + 几何修补 (2.3) + 单位推断 (2.4) |
| L3 语义识别 ⭐ | 40% 🔴 | 规则分类 strict 0.918 | 词表扩展 + LLM 兜底 + Annotation + Quarantine |
| L4 关系拓扑 | 60% 🟡 | FEEDS + KD-Tree | LOCATED_IN/LABELED_BY 增强 + 对称性检验 |
| L5 输出契约 | 80% 🟢 | SiteModel + mcp_context | provenance 字段 (5.4) |
| L6 评测守门 | 70% 🟢 | Gold + LLM-judge + diagnose | CI Gate (6.4) + 多 Gold (6.5) |
| L7 工程化 | 10% 🔴 | (空) | OTel + Cost Budget + ErrorCode + Service |

**统计**: Done 12 / Doing 7 / Todo 14 / Future 1 = 共 34 项

---

## 2. Sprint 1 · 词表扩展 + CI 接通 (1 天)

**目标**: gold strict_acc 0.918 → 0.95+, CI 防回退上线  
**节点**: L3.2 + L5.4 + L6.4 + L1.3

### S1-T1 · 扩词 (L3.2) — 2h

**修改**: `agents/parse_agent/service.py` 的 `_BLOCK_ASSET_PATTERNS`

新增词条:
- **EQUIPMENT**: `harding`, `extar`, `landis`, `grandmaster`, `deep rolling`, `final washing`, `leak test`, `hardener`, `polish`
- **LIFTING_POINT**: `kbk`
- **ANNOTATION** (S2-T3 后启用): `title`, `平面图`, `drawing`

**验证**:
- 重跑 `scripts/gold_eval.py --run-dir exp/parse_results/run_p0_all/66861c26`
- Equipment recall **0.74 → 0.85+**, KBK F1 **0.75 → 1.0**

### S1-T2 · provenance 字段 (L5.4) — 2h

**修改**: `shared/models.py`

```python
class Asset(BaseModel):
    # ... existing fields ...
    source_entity_id: str | None = None      # DXF handle, e.g. "8F2A"
    classifier_kind: Literal[
        "rule_block", "rule_layer", "rule_geom",
        "llm_fallback", "heuristic"
    ] = "rule_layer"
    llm_evidence: list[str] | None = None
```

**修改**: `service.py` 各分类分支按命中路径写入对应 `classifier_kind`

**测试**: 新建 `tests/test_pt_p1_01_provenance.py`
- 断言 100% asset 含 `source_entity_id` (非空)
- 断言 `classifier_kind` 分布合理 (rule_block + rule_layer ≥ 90%)

### S1-T3 · CI Regression Gate (L6.4) — 2h

**新建**: `.github/workflows/parse_agent_quality.yml`

触发条件: PR 修改 `agents/parse_agent/**` 或 `shared/models.py`

Steps:
1. checkout + setup-python 3.11
2. pip install -e .[all]
3. pytest agents/parse_agent/tests/ --tb=short
4. **gold_eval --baseline gold_eval_phase4.json --regression-threshold 0.02** → 失败 block merge
5. 上传 gold_eval JSON 报告作为 artifact

### S1-T4 · 多版本回归 (L1.3) — 2h

**任务**:
- 用 `ezdxf.r12writer` 生成 R12 minimal DXF
- 从公共 sample 库下载 R13/R14/R2000/R2004/R2010/R2013 各 1 份
- 扩 `tests/test_pt_p0_01_format_detect.py` 参数化

**Gate**: 8 sample 全部成功 `open_doc` (含 ODA 降级路径)

### S1 退出条件
- ✅ `gold_score ≥ 0.88` (重跑验证)
- ✅ CI workflow 在测试 PR 上跑通
- ✅ 所有现有 130+ 测试 + 新增 ~10 测试全绿

---

## 3. Sprint 2 · LLM 兜底分类器 (2-3 天)

**目标**: Equipment recall 0.74 → 0.85, LLM-judge 0.30 → 0.40  
**节点**: L3.3 + L3.4 + L3.5 + L3.7 + L7.2 局部

### S2-T1 · H4 LLMClassifier (L3.3) — 1d

**新建**: `agents/parse_agent/llm_classifier.py`

```python
class LLMClassifier:
    def __init__(self, agent_def: dict, gold_yaml_path: Path):
        self.prompt = agent_def["prompt"]
        self.few_shots = self._load_gold_examples(gold_yaml_path, k=8)
        self.client = anthropic.Anthropic()

    def classify_unknown(
        self, block_name: str, layer: str,
        entity_types: dict[str, int], sample_labels: list[str]
    ) -> ClassificationResponse:
        ...
```

**集成**: `service.py` 加 H4 触发点
- 仅对 `type=Other AND confidence<0.3` 的 asset 调用
- `enable_llm_fallback` 开关从 agent.json options 读 (默认 True)

**单测**:
- mock LLM 返回 Equipment → 验证 type 被覆盖
- 验证 `classifier_kind="llm_fallback"`, `llm_evidence=[...]`

### S2-T2 · H5 Response Validator (L3.4) — 4h

**逻辑**:
1. JSON schema (type ∈ enum, confidence ∈ [0,1], sub_type str|null)
2. **`evidence_keywords ⊆ input_tokens`** (set membership, lower-case)
3. 任一 fail → log warning + 丢弃响应 + 回退 H3 (保持 Other)

**H6 校准**: `if classifier_kind=='llm_fallback': confidence *= 0.8`

**单测**:
- 灌入 hallucinated `evidence` (输入未出现) → 验证 reject
- 灌入 valid → 验证 pass
- type 不在枚举 → reject
- confidence > 1 → reject

### S2-T3 · Annotation 类型 (L3.5) — 4h

**修改**: `shared/models.py` AssetType 加 `ANNOTATION = "Annotation"`

**修改**: `service.py` MTEXT/TEXT/DIMENSION → `AssetType.ANNOTATION` (替代 OTHER)

**修改**: `agents/parse_agent/gold/jijia_gold.yaml` 更新 `expected_type_counts.Annotation` min/max

**验证**: gold range pass rate **0.83 → 1.0** (Other 数量从 342 降回 ≤300)

### S2-T4 · Quarantine 队列 (L3.7) — 4h

**写入**: LLM 每次调用追加 `exp/llm_classifications/<run_id>.jsonl`

字段:
```json
{
  "ts": "2026-04-21T10:23:11Z",
  "file": "20180109_机加.dwg",
  "block_name": "EXTAR-70A",
  "layer": "0",
  "response": {...},
  "validated": true,
  "used": true
}
```

**新建**: `scripts/aggregate_llm_quarantine.py`
- 周聚合, 按 block_name 统计调用次数 + LLM 提议的 type 分布
- 输出 markdown 报告 → 候选词条 PR

### S2-T5 · Cost Budget 局部 (L7.2) — 2h

**逻辑**:
- `service.py` 加 per-file LLM 调用计数器
- 超过 `agent.json.guardrails.cost.per_file.max_llm_calls` (50) → 关闭 H4 (剩余 asset 保持 H3 结果)
- `SiteModel.statistics` 加 `llm_mode: "full" | "degraded" | "disabled"`

### S2 退出条件
- ✅ LLM-judge 3-run avg **≥ 0.40**
- ✅ H5 reject 率 **< 5%** (随机抽 50 样本)
- ✅ Quarantine 周报跑通
- ✅ Cost Budget 在 jijia 上模拟超限验证降级行为

---

## 4. Sprint 3 · 几何/链路收尾 (2 天)

**目标**: gold range pass 0.83 → 1.0, link_symmetry ≥ 0.9  
**节点**: L2.2 + L2.3 + L4.2 + L4.3 + L4.5

### S3-T1 · INSERT 矩阵展开 (L2.2) — 6h

**修改**: `service.py::_compute_entity_centroid` 处理 INSERT 时:
1. 取 block_definition 内 entity 几何
2. 应用 INSERT 的 `insert + scale + rotation` (ezdxf `Matrix44`)
3. 返回 world coords (而非 block-local)

**验证**: Conveyor_2m 261 实例坐标 `max_abs < 1e7` (从 1e9 降下来)

**注意**: 这会改变 FEEDS 链顺序, S3.T1 完成后立即重跑 gold 重置 baseline (`gold_eval_phase4.json` → `gold_eval_phase5_geom.json`)

### S3-T2 · closed-poly 修补 (L2.3) — 4h

**逻辑**:
- LWPOLYLINE 检查 `closed` flag + first/last vertex 距离 < tolerance
- 自动闭合 → AssetType.ZONE 命中

**测试**: 注入 open polyline, 验证修补后归 Zone

### S3-T3 · LOCATED_IN 改进 (L4.2) — 3h

当前: 最近 zone (距离 ≤ 10000mm)

**改**: 基于 Zone bbox 的 point-in-polygon 包含判断, 命中即 LOCATED_IN

**Gate**: jijia LOCATED_IN **18 → ≥ 50**

### S3-T4 · LABELED_BY 增强 (L4.3) — 3h

当前: MTEXT/TEXT 与最近 Equipment 关联, 半径 5000mm

**改**:
- 半径动态 = `max(5000, equipment.bbox.diagonal / 2)`
- 排除 ANNOTATION 类型自身参与匹配

**Gate**: jijia LABELED_BY **18 → ≥ 30**

### S3-T5 · link_symmetry 断言 (L4.5) — 2h

`scripts/quality_diagnose.py` 已有 `compute_link_symmetry`, 集成到 `gold_eval.py` 输出, 加 stage_gate 断言.

### S3 退出条件
- ✅ `gold_score ≥ 0.92`
- ✅ `aggregate_ranges.pass_rate = 1.0`
- ✅ `link_symmetry ≥ 0.9`
- ✅ jijia 坐标 `max_abs_coord < 1e7`

---

## 5. Sprint 4 · 工程化收口 (3 天)

**目标**: GA 必备的可观测/限流/服务化, 与 Orchestrator 联调通过  
**节点**: L7.1 + L7.3 + L7.4 + L7.5

### S4-T1 · OpenTelemetry 埋点 (L7.1) — 1d

**新建**: `agents/parse_agent/observability.py`
- OTel SDK init (TracerProvider + MeterProvider)
- span helpers: `@traced("stage_name")` decorator

**埋点**:
- spans: `parse_file`, `entity_extract`, `classify_unknowns`, `build_links`, `write_output`
- metrics: `parse_time_ms`, `llm.calls`, `llm.tokens`, `llm.quarantined`, `gold_score`

默认 console exporter, 可通过 env 配 OTLP.

### S4-T2 · 错误码完备 (L7.3) — 4h

**新建**: `agents/parse_agent/errors.py`

```python
class ParseAgentError(Exception):
    error_code: str

class InvalidFormatError(ParseAgentError): error_code = "INVALID_FORMAT"
class ParseFailedError(ParseAgentError): error_code = "PARSE_FAIL"
class LLMTimeoutError(ParseAgentError): error_code = "LLM_TIMEOUT"
class BudgetExceededError(ParseAgentError): error_code = "BUDGET_EXCEEDED"
class SchemaInvalidError(ParseAgentError): error_code = "SCHEMA_INVALID"
```

**集成**: 替换 `service.py` 内裸 raise; mcp_context 失败时填 `error_code`.

### S4-T3 · Drift Detector (L7.4) — 4h

**新建**: `scripts/quality_drift_check.py`
- scan 最近 20 个 run 的 `llm_quality_matrix.json`
- 计算 7 日趋势线
- 阈值: 跌幅 > 5% → exit 1 (可接 cron, 后续接告警)

### S4-T4 · FastAPI Service 完善 (L7.5) — 1d

**修改**: `agents/parse_agent/app.py`
- POST /parse 接 multipart file → 同步返回 SiteModel JSON
- GET /healthz, GET /version (含 gold_score baseline)

**新建**: `Dockerfile` + `docker-compose.yml`

**联调**: Orchestrator MCP server 配 ParseAgent 端点 → 跑通 ConstraintAgent 消费

### S4-T5 · agent.json loader (启动校验) — 2h

**新建**: `agents/parse_agent/agent_loader.py`
- 启动时读 `agent.json` 并校验 SDK 兼容
- 失败启动即崩, 不静默降级

### S4 退出条件
- ✅ OTel trace 在 jijia 跑可见 (导出到 console)
- ✅ 错误码全覆盖 (旧 raise 全部替换)
- ✅ Orchestrator 端到端跑通 1 次 jijia 全链路
- ✅ gold ≥ 0.92, LLM-judge ≥ 0.45 (GA 双指标)

---

## 6. 跨 Sprint 依赖

```
S1 (独立, 最先做)
  ├─ S1-T2 provenance 字段 ─────┐
  ├─ S1-T3 CI Gate ────────────┐│
  └─ S1-T4 多版本回归 (并行)    ││
                               ││
S2 (依赖 S1.T2 + S1.T3)         ││
  ├─ S2-T1 LLMClassifier ←─────┘│
  ├─ S2-T3 Annotation (并行) ────┘
  └─ S2-T4/T5
                     ↓
S3 (弱依赖 S2.T3, 强依赖 S1.T2)
  └─ S3-T1 INSERT 矩阵 (改坐标, 需重置 gold baseline)
                     ↓
S4 (依赖 S2/S3 接口稳定)
```

**可并行 task**:
- S1-T4 ⫽ S1-T1/T2/T3 (不同人)
- S2-T3 ⫽ S2-T1/T2 (Annotation 与 LLM 完全独立)

---

## 7. 量化里程碑

| 里程碑 | gold | LLM-judge | CI | 联调 |
|---|---|---|---|---|
| 起点 (Phase 4.6) | 0.83 | 0.30 | ✗ | ✗ |
| **S1 末** | ≥ 0.88 | (持平) | ✓ | ✗ |
| **S2 末** | ≥ 0.90 | ≥ 0.40 | ✓ | ✗ |
| **S3 末** | ≥ 0.92 | ≥ 0.43 | ✓ | ✗ |
| **S4 末 (GA)** | **≥ 0.92** | **≥ 0.45** | **✓** | **✓** |

每个 Sprint 末必跑: gold_eval + 3-run llm-judge + 全部 pytest, **三连测稳定才算 done**.

---

## 7.5. GA 验收准则 (Roles × Dimensions)

> ParseAgent 输出"satisfy" 的硬定义: 6 个 Role 全绿才算可发布 GA。任意一个 fail 必须修复后重审, **不允许例外通过**。

### 7.5.1 输出物清单 (审核对象)

| 类别 | 内容 | Schema 来源 |
|---|---|---|
| **A. 主产物** | `SiteModel` (assets[] / links[] / geometry_integrity_score / statistics) | [shared/models.py](../shared/models.py) `class SiteModel` |
| **B. 元数据** | `mcp_context_id` / `mode` (normal\|fallback) / `provenance[]` / `agent_version` | MCP envelope |
| **C. 可观测信号** | `parse_time_ms` / `llm.calls` / `llm.tokens` / `llm.quarantined` / `gold_score` | OpenTelemetry, [agent.json](../agents/parse_agent/agent.json) `guardrails.observability.telemetry` |

### 7.5.2 Role × Dimension 审核矩阵

| Role | 触发时机 | 维度 | 工具 | Block? | RACI |
|---|---|---|---|:---:|---|
| **R1 Schema Guardian** | 每次解析后 (ms) | pydantic strict / 枚举 / 数值边界 / GUID 唯一 | `SiteModel.model_validate()` + Hook H5 | ✅ | R: ParseAgent dev |
| **R2 Gold Auditor** | 每个 PR (CI) | strict_acc ≥ 0.92 / Equipment recall ≥ 0.85 / 关系召回 / ECE | [scripts/gold_eval.py](../scripts/gold_eval.py) + Hook H7 | ✅ | A: ParseAgent dev |
| **R3 Silver Statistician** | 每次大批量跑 (s) | Unknown<15% / 平均 conf>0.75 / 类型 KL<0.5 / Layer 命中>90% / LLM 配额<80% | [scripts/quality_diagnose.py](../scripts/quality_diagnose.py) | ⚠ Warn | C: Domain Lead |
| **R4 LLM Judge** | 周 cron (min) | 语义合理性 ≥ 0.45 / 失败标签分布 / 长尾覆盖趋势 | [agents/parse_agent/llm_quality.py](../agents/parse_agent/llm_quality.py) | ⚠ Warn | C: Domain Lead |
| **R5 Domain Expert** | 词表变更 / 季度审计 | 业务合理性 / 误判修订 / `propose_taxonomy_term` 审批 | 人工 → 写回 [jijia_gold.yaml](../agents/parse_agent/gold/jijia_gold.yaml) | ✅ (词表变更) | A: Domain Lead |
| **R6 Consumer Contract** | 下游 Agent 启动期 | footprint 非空 / ports 闭合 / `geometry_integrity_score>0.8` | ConstraintAgent / LayoutAgent E2E | ✅ | A: Orchestrator dev |

### 7.5.3 GA 准入硬条件 (AND 关系)

```
GA_satisfy = (
      R1.schema           == ALL_GREEN      # pydantic 0 ValidationError
  AND R2.gold.strict_acc  >= 0.92           # Phase4.6 → GA 提升
  AND R2.gold.regression  >  -0.02          # 不允许相对基线掉 >2%
  AND R3.silver           == NO_RED_CELL    # 5 项指标全绿
  AND R4.llm_judge        >= 0.45           # 语义层目标
  AND R5.expert_signoff   == TRUE           # 季度审计签字
  AND R6.consumer_e2e     >= 1_PASSING      # 至少 1 个下游 E2E 跑通
)
```

### 7.5.4 自动化覆盖率

| Role | 自动化程度 | CI 集成 | 失败处置 |
|---|:---:|:---:|---|
| R1 Schema | 100% 自动 | ✅ `parse_agent_quality.yml` contract job | Block PR |
| R2 Gold | 100% 自动 | ✅ `parse_agent_quality.yml` gold-regression job | Block PR |
| R3 Silver | 100% 自动 | ⏸ Dashboard, 不 block | 触发人审 issue |
| R4 LLM-Judge | 半自动 (LLM) | ⏸ Weekly cron | 趋势告警 |
| R5 Expert | 人工 | ❌ 季度 ritual | 阻断 GA, 不阻断 PR |
| R6 Consumer | 自动 (E2E) | ⏸ Phase 5 集成 | Block GA |

### 7.5.5 验收 checklist (GA 发布前必跑)

```bash
# R1 Schema
python -m pytest agents/parse_agent/tests/ -v

# R2 Gold (必须 ≥ 0.92, 相对基线不掉 >2%)
python scripts/gold_eval.py \
  --run-dir exp/parse_results/run_p0_all/<latest> \
  --baseline exp/parse_results/run_p0_all/gold_eval_phase4.json \
  --regression-threshold 0.02

# R3 Silver (5 项指标必须全绿)
python scripts/quality_diagnose.py --run-dir <...> --strict

# R4 LLM-Judge (3 次取均值, 必须 ≥ 0.45)
python -m agents.parse_agent.llm_quality --run-dir <...> --runs 3

# R5 Expert: Domain Lead 在 GitHub PR 上签字 'GA-APPROVED'
# R6 Consumer: 跑 spikes/e2e/test_constraint_consumes_site_model.py
python -m pytest spikes/e2e/ -v
```

全部通过 → 打 tag `parse_agent/v1.0.0` → 升 GA。

---

## 8. 风险与对策

| ID | 风险 | 等级 | 对策 |
|---|---|---|---|
| R1 | LLM 兜底引入 hallucination | 高 | H5 校验 + classifier_kind + 0.8 折扣三重防护 |
| R2 | INSERT 矩阵展开改坐标 → FEEDS 链重排 | 中 | S3.T1 完成后立即刷新 gold baseline |
| R3 | CI 跑 LLM 太贵 | 中 | 强制 gate 用 gold_eval (零 LLM), llm-judge 仅 nightly |
| R4 | R12/R13 样本难找 | 低 | fallback 用 ezdxf 自带 r12writer 生成 |

---

## 9. Out of Scope (Phase 5+)

- L3.6 sub_type 细分 (WashingMachine/HoningMachine 等子类)
- 多 Gold 仅做 wood_factory_1 一份, cold_rolled 推后
- Drift Detector 仅做 exit code, 告警通道留 P5
- Web 可视化 (Three.js renderer 已有原型, 不在 ParseAgent GA 范围)

---

## 10. 决策记录

- LLM 调用预算 50/file, 超限自动降级为纯规则 (degraded mode)
- Annotation 作为新枚举 (不复用 OTHER), 保留语义清晰度
- `agent.json` 是单一事实源, 运行时 prompt/tools 都从此加载
- provenance 改 `shared/models.py` 是 breaking change, 但 ConstraintAgent 尚未消费, 现在做无成本
- S3 INSERT 矩阵展开后, jijia gold 的 `coord_scale_outlier` 标记会失效, 同步更新 known_issues
