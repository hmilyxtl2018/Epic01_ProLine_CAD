# Stage B — 候选 span 结构化（高精度，零幻觉）

> Prompt 版本：`stage_b_v1`（任何字符级修改必须 bump 到 v2）
> 调用方：`app/services/constraint_extractor/extractor.py`
> 出参契约：`app/schemas/constraint_extraction.py::ExtractedConstraint`

## 1. 任务

给你一个**已被 Stage A 圈定的候选 span** 和它所在的 chunk 上下文。
你需要把这个 span 抽成**一条结构化工艺约束**，严格遵守下面的输出 JSON Schema。
若该 span **不构成有效约束**（属于章节标题、签字、错圈），返回 `{"skip": true, "reason": "..."}`。

## 2. 输入

```json
{
  "site_model_id": "site_seed_001",
  "document_id": "AO-DEMO-001",
  "chunk": {
    "chunk_id": "chunk_1",
    "page": 4,
    "char_start": 1280,
    "char_end": 1402,
    "text": "...完整 chunk 上下文..."
  },
  "candidate": {
    "span_start": 12,
    "span_end": 48,
    "span_text": "前序工序 S10 完成后方可开始铆接。",
    "reason": "顺序触发词「方可」"
  }
}
```

## 3. 输出（**仅返回 JSON 顶层对象**）

形式 A — 抽到一条约束：

```json
{
  "kind": "predecessor",
  "category": "SEQUENCE",
  "class": "soft",
  "severity": "major",
  "authority": "project",
  "conformance": "SHOULD",
  "rule_expression": "precedes(S10, S20)",
  "rationale": "AO 第 4.1 节明示 S10 完成后才能开始铆接（S20）。",
  "applicable_phases": ["OPERATION"],
  "valid_from": null,
  "valid_to": null,
  "scope": {
    "node_rds_candidates": ["=PROC.S10", "=PROC.S20"],
    "asset_guid_candidates": [],
    "product_id": null
  },
  "source_document_id": "AO-DEMO-001",
  "source_span": {"page": 4, "char_start": 1292, "char_end": 1328},
  "span_text": "前序工序 S10 完成后方可开始铆接。",
  "confidence": 0.82
}
```

形式 B — span 错圈或不构成约束：

```json
{"skip": true, "reason": "该 span 是章节标题，不含工艺约束。"}
```

## 4. 字段语义与封闭枚举

> 所有枚举为闭集，**值必须从下表选**，否则会被 422 丢弃。

### `kind` — 求解器形状（4 选 1）

| 值 | 中文 | 适用场景 |
|---|---|---|
| `predecessor` | 前驱 | "A 完成后 B 才能开始" 类工序顺序 |
| `resource` | 资源 | "A、B、C 共用同一工人 / 同一行车" 类并发上限 |
| `takt` | 节拍 | "S20 循环时间在 [min, max] 区间" 类时间窗 |
| `exclusion` | 互斥 | "A 与 B 不能同时进行" 类禁止并发 |

### `category` — 业务类别（10 选 1）

`SPATIAL` 空间 · `SEQUENCE` 顺序 · `TORQUE` 扭矩 · `SAFETY` 安全 ·
`ENVIRONMENTAL` 环境 · `REGULATORY` 法规 · `QUALITY` 质量 ·
`RESOURCE` 资源 · `LOGISTICS` 物流 · `OTHER` 其他

### `class` — 强度（3 选 1）

`hard` 必须满足（违反 = 不可发布）· `soft` 参与目标函数（违反扣分）·
`preference` 仅参与排序（不阻塞）

### `severity` — 严重度（3 选 1）

`critical` · `major` · `minor`

### `authority` — 权威等级（6 选 1，L0..L5 由强到弱）

`statutory` 法规适航 · `industry` 行业军标 · `enterprise` 企业 OEM ·
`project` 项目工艺 · `heuristic` 经验 · `preference` 个人偏好

### `conformance` — RFC 2119 词汇（3 选 1）

`MUST` · `SHOULD` · `MAY`

### `applicable_phases` — 生命周期阶段子集（至少 1 个）

`CONCEPT` · `DESIGN` · `CONSTRUCTION` · `COMMISSIONING` ·
`OPERATION` · `MODIFICATION` · `MAINTENANCE` · `DECOMMISSION`

## 5. 联动规则（**违反一条 = 立即返回 `{"skip": true}`**）

- **R1**：`authority ∈ {statutory, industry}` ⇒ `class` 必须是 `hard`。
- **R2**：`authority == "preference"` ⇒ `class` **不能**是 `hard`。
- **R3**：`kind == "predecessor"` ⇒ `scope.node_rds_candidates` **至少 2 个**
  （前驱与后继两端都要给出候选；只给一端属于幻觉）。
- **R4**：`span_text` **必须**逐字等于 `chunk.text[span_start_local:span_end_local]`，
  且写入 `source_span.char_start = chunk.char_start + span_start_local`。
- **R5**：`valid_to` 若给出，必须严格晚于 `valid_from`；多数情况两者均为 `null`。
- **R6**：`confidence ∈ [0.0, 1.0]`；不确定就给 `0.5`，**不要**编造 `0.99`。

## 6. RDS 编码格式（IEC 81346）

`scope.node_rds_candidates` 中的 RDS 码遵循三视角前缀：

- `=` FUNCTION 视角，例：`=PROC.S20`、`=PROC.AC.SH01.A2.L1.S20`
- `-` PRODUCT 视角，例：`-EQ.PRESS01`、`-FIX.J3.ASSY`
- `+` LOCATION 视角，例：`+SH01.A2.L1.S20`、`+SH01.HALL_B`

抽不到 RDS 编码时给 `[]`，不要编造。`asset_guid_candidates` 同理：原文未出现 `MDI-XXXXXXXX` 格式不要造。

### `asset_guid_candidates` 关联的 AssetType 词典（仅供文本里出现"工装/设备/机器人"等字样时辅助识别）

> 只用于在 `rationale` 中正确表述资产类别名词，不写入 JSON 输出字段。
> 闭集；下表不在表内的资产名称不要被错误识别。

`Equipment` 通用设备 · `Conveyor` 输送带 · `LiftingPoint` 吊装点 ·
`Zone` 区域 · `Wall` 墙体 · `Door` 门 · `Pipe` 管道 · `Column` 柱子 ·
`Window` 窗 · `CncMachine` 数控机床 · `ElectricalPanel` 配电柜 ·
`StorageRack` 货架 · `Annotation` 标注 · `Other` 其他 ·
`StampingPress` 冲压机 · `WeldingRobot` 焊接机器人 ·
`HandlingRobot` 搬运机器人 · `Agv` AGV ·
`Buffer` 缓存区 · `OperatorStation` 人工工位 ·
`InspectionStation` 检测工位 · `RobotCell` 机器人工作单元

## 7. 反例（5 条最常见的幻觉）

1. **不要**把"建议 / 宜 / recommend"当 `MUST`；这些是 `MAY` 或 `SHOULD` + `class=preference`。
2. **不要**给单端的 `predecessor`；只看到 "S20 之前要 ..." 但找不到对方时返回 `{"skip": true}`。
3. **不要**给原文里完全不存在的 RDS 编码；候选为空就给 `[]`。
4. **不要**把章节标题（"4.1 装配工艺要求"）抽成约束；返回 `{"skip": true}`。
5. **不要**编造 `confidence ≥ 0.95`；只有原文 + 强触发词同时满足才允许 ≥ 0.85。

## 8. 自检清单

1. 我返回的是单个顶层 JSON 对象吗？
2. 我抽出的 `span_text` 与候选 `span_text` **完全一致**吗？
3. 我有没有违反 R1–R6 任意一条？
4. 我的 `rule_expression` 是机器可解析的，不是中文长句？

只输出 JSON。**不要**输出 Markdown 代码块、解释、开场白。
