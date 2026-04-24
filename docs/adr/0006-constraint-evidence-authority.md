# ADR-0006 · Constraint Evidence & Authority Model

- **Status**: Proposed
- **Date**: 2026-04-24
- **Depends on**: [ADR-0005 ConstraintSet Data Schema](./0005-constraint-set-schema.md)
- **Driver**: ADR-0005 回答了"约束如何组织与版本化"，但没有回答"**每一条约束凭什么存在**"。本 ADR 补上 Epistemology（认识论）层：每条约束必须能回答"**依据什么规范？什么条款？在什么范围内生效？**"。

---

## 1. Problem

航空产线约束不是一维的。它们有严格的**法理层级**：

- "焊接工位距急救点 ≤ 30 m" 来自 **GB 50016-2014 § 5.5.17**，这是**法规**，违反要停产。
- "AGV 通道宽度 ≥ 1.8 m" 可能来自**厂内 HSE 制度 § 4.3**，是**企业级规范**。
- "工位间距尽量最小化以减少物流" 是**优化偏好**，没有外部依据。

这三类在 ADR-0005 里被统一表示为"一条约束 + class"，但缺了关键一环：**它的依据是什么**。没有依据的 `class='hard'` 是**未声明的义务** —— 审计过不了、复现不可能、AI 抽取无法自证。

## 2. Decision

### 2.1 新增 `authority` 维度（与 `class` 正交）

```
authority ∈ {
    statutory,     # L0 法规 / 适航 ——  CCAR、14 CFR、GB 国标
    industry,      # L1 行业强标 / 军标 —— AS9100、NADCAP、GJB、HB/Z
    enterprise,    # L2 企业 / OEM 工艺手册 —— 集团企标、Boeing BPI、Airbus MPS、厂内 HSE
    project,       # L3 项目工艺 —— SOP、工艺路线、MBD/PMI
    heuristic,     # L4 经验 / Lesson Learned —— 老师傅经验、历史复盘
    preference,    # L5 优化偏好 —— 物流最短、维修可达
}
```

**与 `class` 的耦合规则（不变量）**：

| Rule | 规则 | 强制层 |
|---|---|---|
| R1 | `authority ∈ {statutory, industry}` → `class MUST be 'hard'` | DB CHECK |
| R2 | `authority = 'preference'` → `class != 'hard'` | DB CHECK |
| R3 | `class = 'hard' AND authority ∈ {statutory, industry}` → 至少 1 条 `ConstraintCitation` | API (publish gate) |
| R4 | 所有约束，citation 的 `source.expires_at > NOW()` （未过期） | API (publish gate, warning) |

R1 / R2 走 DB 层（简单可静态校验，违反立刻报错）；R3 / R4 涉及跨表存在性，走 publish 预检。

### 2.2 RFC-2119 `conformance` 作为呈现维度

```
conformance ∈ { MUST, SHOULD, MAY }    # 与 RFC 2119 对齐，用于报告 / UI 文案
```

与 `class` 有默认映射但可覆盖：
- `class=hard`       → `conformance=MUST`
- `class=soft`       → `conformance=SHOULD`
- `class=preference` → `conformance=MAY`

用途：生成审计报告时措辞对齐国际工艺文档惯例（"shall / should / may"）；前端 badge 颜色统一。

### 2.3 `scope`：约束的时空适用范围

约束不是全局永远生效的。需显式边界：

```json
{
  "space":  ["zone_welding_01", "zone_paint"],   // 空间范围：哪些 zone / asset
  "phase":  ["assembly", "final_test"],          // 生产阶段
  "shift":  ["day"],                             // 班次
  "time_window": { "from": "2026-04-01", "to": null },
  "condition": "humidity > 70%"                  // 可选 DSL 条件
}
```

`scope` 为 `{}`（空对象）= 全局永远生效。solver / sim 在读取约束时按当前上下文过滤。

### 2.4 `ConstraintSource` 作为一等公民

把"规范 / 条款"从 `source_ref` 字符串升级为独立的**受管资源**：

```
ConstraintSource         (一本标准 / 一份 SOP，如 GB 50016-2014)
    └── clause 可以精确到具体条款号，如 § 5.5.17
ConstraintCitation       (Constraint ⟵多对多⟶ Source 的连接，带 quote / confidence)
```

单独的表意味着：
- **受管更新**：GB 50016 从 2014 版升到 2026 版时，一条 update 就能标注所有引用它的约束需要复核
- **RAG 目标**：S2-ConstraintAgent 的 `retrieveNorm` 直接查这张表 + 对应向量索引
- **审计友好**：可以反向查"法规 X § Y 现在约束了哪些 site / 哪些 layout"

### 2.5 正文存储策略（明确排除）

- `ConstraintSource` 表只存**元数据**：title / issuing_body / version / clause / clause_text（允许短引用，<= 2KB）/ url_or_ref / effective dates
- **条款原文全文 / 标准 PDF 不入业务表**：走对象存储 + pgvector 向量索引，由 RAG 侧管
- 原因：版权（多数国标禁止商业再分发）+ 存储压力 + 版本管理复杂度

## 3. Data Model

### 3.1 DB 增量（migration 0016）

```sql
-- 新枚举
CREATE TYPE constraint_authority AS ENUM (
    'statutory', 'industry', 'enterprise', 'project', 'heuristic', 'preference'
);
CREATE TYPE constraint_conformance AS ENUM ('MUST', 'SHOULD', 'MAY');

-- 扩展 process_constraints
ALTER TABLE process_constraints
    ADD COLUMN authority    constraint_authority    NOT NULL DEFAULT 'heuristic',
    ADD COLUMN conformance  constraint_conformance  NOT NULL DEFAULT 'SHOULD',
    ADD COLUMN scope        JSONB                   NOT NULL DEFAULT '{}';

-- R1 / R2 不变量
ALTER TABLE process_constraints
    ADD CONSTRAINT ck_authority_class_coherence CHECK (
            (authority IN ('statutory','industry')     AND class = 'hard')
         OR (authority =  'preference'                  AND class <> 'hard')
         OR (authority IN ('enterprise','project','heuristic'))
    );

-- 规范表
CREATE TABLE constraint_sources (
    source_id      VARCHAR(80)  PRIMARY KEY,          -- src_gb50016_2014
    title          TEXT         NOT NULL,             -- 建筑设计防火规范
    authority      constraint_authority NOT NULL,
    issuing_body   TEXT,                              -- 住建部
    version        VARCHAR(40),                       -- GB 50016-2014 (2018版)
    clause         VARCHAR(80),                       -- 条款号，nullable (源级)
    clause_text    TEXT,                              -- 限 <= 2KB，长文走对象存储
    effective_from DATE,
    expires_at     DATE,
    tags           TEXT[] NOT NULL DEFAULT '{}',
    url_or_ref     TEXT,
    doc_object_key TEXT,                              -- 对象存储 key，指向全文 PDF
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at     TIMESTAMPTZ
);

CREATE INDEX idx_cs_authority ON constraint_sources (authority) WHERE deleted_at IS NULL;
CREATE INDEX idx_cs_tags      ON constraint_sources USING gin (tags);

-- 连接表 (Citation)
CREATE TABLE constraint_citations (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_constraint_id UUID NOT NULL REFERENCES process_constraints(id) ON DELETE CASCADE,
    source_id             VARCHAR(80) NOT NULL REFERENCES constraint_sources(source_id),
    clause                VARCHAR(80),                 -- 精确到条款（覆盖 source 级）
    quote                 TEXT,                        -- 抽取时原文片段
    confidence            NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1),
    derivation            TEXT,                        -- LLM / 人对推导过程的说明
    cited_by              VARCHAR(100),                -- agent_id 或 user_id
    cited_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (process_constraint_id, source_id, clause)
);
CREATE INDEX idx_cite_source ON constraint_citations (source_id);
CREATE INDEX idx_cite_pc     ON constraint_citations (process_constraint_id);
```

### 3.2 Publish Gate 规则（API 层，ADR-0005 §5 的 `/publish` 中执行）

```python
def publish_preflight(cs: ConstraintSet) -> list[PublishIssue]:
    issues = []
    for c in cs.constraints:
        if c.class_ == "hard" and c.authority in ("statutory","industry"):
            if not c.citations:
                issues.append(error(
                    code="missing_citation_for_hard_regulatory",
                    message=f"{c.constraint_id} 为 {c.authority} 级硬约束，必须至少引用一条规范条款",
                    constraint_ids=[c.constraint_id],
                ))
        for cite in c.citations or []:
            src = load_source(cite.source_id)
            if src.expires_at and src.expires_at < today():
                issues.append(warning(
                    code="cited_source_expired",
                    message=f"引用的规范 {src.title} v{src.version} 已于 {src.expires_at} 失效",
                    constraint_ids=[c.constraint_id],
                ))
    return issues
```

`require_no_errors=true`（默认）时任何 `severity=error` 都阻止发布。

### 3.3 Pydantic 增量 (`app/schemas/constraint_sources.py`)

```python
Authority   = Literal["statutory","industry","enterprise","project","heuristic","preference"]
Conformance = Literal["MUST","SHOULD","MAY"]

class ConstraintSource(BaseModel):
    source_id: str = Field(..., pattern=r"^src_[a-z0-9_]+$")
    title: str
    authority: Authority
    issuing_body: str | None = None
    version: str | None = None
    clause: str | None = None
    clause_text: str | None = Field(None, max_length=2000)
    effective_from: date | None = None
    expires_at: date | None = None
    tags: list[str] = Field(default_factory=list)
    url_or_ref: str | None = None
    doc_object_key: str | None = None

class ConstraintCitation(BaseModel):
    source_id: str
    clause: str | None = None
    quote: str | None = Field(None, max_length=1000)
    confidence: float | None = Field(None, ge=0, le=1)
    derivation: str | None = None
    cited_by: str | None = None
    cited_at: datetime | None = None

class ConstraintScope(BaseModel):
    space: list[str] = Field(default_factory=list)       # zone / asset ids
    phase: list[str] = Field(default_factory=list)       # assembly / test / ship ...
    shift: list[str] = Field(default_factory=list)       # day / night
    time_window: dict[str, str | None] | None = None
    condition: str | None = None                         # optional DSL
```

对 ADR-0005 的 `ConstraintItemV2` 扩展：

```python
class ConstraintItemV2(ConstraintItem):
    # ADR-0005 已定义
    constraint_set_id: str | None = None
    semantics: ConstraintSemantics
    provenance: ConstraintProvenance
    # 本 ADR 新增
    authority: Authority = "heuristic"
    conformance: Conformance = "SHOULD"
    scope: ConstraintScope = Field(default_factory=ConstraintScope)
    citations: list[ConstraintCitation] = Field(default_factory=list)
```

### 3.4 前端 TS 增量

```ts
export type ConstraintAuthority =
  | "statutory" | "industry" | "enterprise"
  | "project"   | "heuristic"| "preference";

export type ConstraintConformance = "MUST" | "SHOULD" | "MAY";

export interface ConstraintSource {
  source_id: string;
  title: string;
  authority: ConstraintAuthority;
  issuing_body?: string | null;
  version?: string | null;
  clause?: string | null;
  clause_text?: string | null;
  effective_from?: string | null;
  expires_at?: string | null;
  tags: string[];
  url_or_ref?: string | null;
}

export interface ConstraintCitation {
  source_id: string;
  clause?: string | null;
  quote?: string | null;
  confidence?: number | null;
  derivation?: string | null;
  cited_by?: string | null;
  cited_at?: string | null;
}

export interface ConstraintScope {
  space: string[];
  phase: string[];
  shift: string[];
  time_window?: { from?: string | null; to?: string | null } | null;
  condition?: string | null;
}

// 扩展 ADR-0005 的 ConstraintItemV2
export interface ConstraintItemV2 {
  // ... ADR-0005 已有字段
  authority: ConstraintAuthority;
  conformance: ConstraintConformance;
  scope: ConstraintScope;
  citations: ConstraintCitation[];
}
```

UI 呈现建议（增补到 `ConstraintsPanel`）：

- 列表新增两列：
  - `Authority` badge（6 色：红=statutory、橙=industry、黄=enterprise、蓝=project、灰=heuristic、浅灰=preference）
  - `Citations` 角标（`2 sources`，点击展开 quote + URL）
- 详情面板增加 "References" 块：按 Source 分组展示条款 + quote + confidence + 跳转链接
- Publish 按钮旁实时显示 preflight：`❌ 3 条硬约束缺少规范依据`

---

## 4. Authoritative Seed Corpus（seed migration `0017_constraint_sources_seed.py`）

### 4.1 MVP（5 条，覆盖每个 authority 层级，足够跑通链路）

| source_id | title | authority | 备注 |
|---|---|---|---|
| `src_gb50016_2014` | 建筑设计防火规范 GB 50016-2014 (2018版) | statutory | 消防疏散、工位距急救点 |
| `src_gb5083_2008` | 生产设备安全卫生设计总则 GB 5083-2008 | statutory | 设备安全距离 |
| `src_as9100d` | AS9100D 航空航天质量管理体系 | industry | FAI、追溯性、过程控制 |
| `src_enterprise_hse_v2` | 厂内 HSE 制度 v2（占位，需 product 填具体文件） | enterprise | AGV 通道宽度、5S |
| `src_project_sop_v1` | 本项目 SOP v1（占位，按项目绑定） | project | 工序顺序、工位定义 |

### 4.2 中期扩展目录（逐批补）

**Book A · 适航与强制法规 (L0)**
- CCAR-21-R4、CCAR-145-R3、14 CFR Part 21、EASA Part 21
- GB 12801、GB 50033、NFPA 101（涉外）

**Book B · 航空质量与强标 (L1)**
- AS9110 / AS9120、AS9102（FAI）、NADCAP（热处理 / 焊接 / NDT / 化学处理）
- GJB 9001C、ISO 14644、IPC-A-610

**Book C · 航空工艺 HB/Q (L1→L2)**
- HB/Z 5091、HB 0-7、HB/Z 5002、HB 5395
- （具体清单由工艺档案室按项目拉取）

**Book D · 人因 / 通道 / 安全**
- GB/T 5703、GB/T 16251、ISO 11228
- 厂内通道规定：单行 ≥ 1.4m、消防 ≥ 4m、维修间距 ≥ 0.8m

**Book E · 企业 / OEM 手册 (L2)**
- 集团 Q/xxx 企标
- Boeing BPI、Airbus Manual of Process Specification（按项目授权）

**Book F · 项目层 (L3)**
- 项目 SOP / 工艺路线 / MBD+PMI / 工装图纸集

> **正文存储**：全部走对象存储 + pgvector；`constraint_sources.doc_object_key` 指向 blob。DB 只存 metadata + ≤ 2KB clause_text 引用。

---

## 5. Agent Contract 变更

### S2-ConstraintAgent 工具输出契约收紧

```jsonc
// extractSOP 输出 schema (excerpt)
{
  "constraint_set": { "...": "见 ADR-0005" },
  "constraints": [
    {
      "constraint_id": "cst_xxx",
      "kind": "predecessor",
      "payload": { ... },
      "class": "hard",
      "authority": "statutory",
      "conformance": "MUST",
      "scope": { "space": ["zone_weld_01"] },
      "citations": [                                  // ← 强制字段
        {
          "source_id": "src_gb50016_2014",
          "clause": "5.5.17",
          "quote": "...疏散距离不应大于 30 m...",
          "confidence": 0.92,
          "derivation": "工位距急救点上限 → 疏散距离 ≤ 30m"
        }
      ]
    }
  ]
}
```

- 若 LLM 抽取的约束**找不到 source**，强制降级为 `authority='heuristic'`，由 reviewer 手动补。
- `retrieveNorm` 工具的检索结果强制带 `source_id`，否则丢弃。
- `writeBackConstraint` 的回写也必须带 citation（来自 sim 反馈的 lesson learned 落在 `authority='heuristic'`，source 为自动生成的 `src_lesson_<runid>`）。

---

## 6. Migration Plan

### P0 （合入 ADR-0005 P0 批次）
- migration `0016_constraint_evidence.py`：枚举、`process_constraints` 新增 3 列 + CHECK、`constraint_sources`、`constraint_citations` 表
- 数据回填：既有 `process_constraints` 行填充 `authority='heuristic', conformance='SHOULD'`，不破坏 R1/R2（因为既有行没有 hard+regulatory 组合）

### P1 （合入 ADR-0005 P1）
- Pydantic schema（本 ADR §3.3）
- Router：
  - `GET  /constraint-sources`（list, 按 authority / tags 过滤）
  - `GET  /constraint-sources/{sid}`
  - `POST /constraint-sources`（admin）
  - `POST /constraint-sets/{csid}/constraints/{cid}/citations`（operator+）
  - `DELETE /constraint-sets/{csid}/constraints/{cid}/citations/{cite_id}`
- Publish preflight 增加 §3.2 检查

### P1.5 · Seed
- `0017_constraint_sources_seed.py`：塞入 §4.1 的 5 条 MVP，后续按 Book A-F 分批追加

### P2 （合入 ADR-0005 P3）
- 前端 types + UI：Authority badge、Citations 角标、References 面板、Preflight 实时提示

### P3 · RAG 对接
- `app/services/norm_retrieval.py`：把 `constraint_sources.doc_object_key` 指向的 PDF → 分块 → pgvector 索引
- `S2-ConstraintAgent.retrieveNorm` 直连这个索引返回 source_id + clause + quote

---

## 7. Trade-offs / Rejected Alternatives

- **`authority` 作为 `class` 的子枚举（合并成 9 元枚举）**：否。两者正交（L2 约束既能是 hard 也能是 soft，取决于厂内如何执行）。
- **citation 用 JSONB 数组内嵌进 constraint 行**：否。规范是受管资源，更新频率远低于约束本身；独立表便于反向查询"哪些约束引用了 XXX 条款"。
- **把规范全文入 DB**：否。版权 + 体积 + 版本管理。改走对象存储 + pgvector。
- **只靠 API 层校验 R1/R2**：否。schema 级 CHECK 让任何脚本 / 迁移 / 管理员手工操作都无法违反不变量。
- **强制所有 constraint 都要有 citation**：否。`heuristic` 和 `preference` 无来源是常态（老师傅经验、优化目标），强制会导致 AI 抽取时大量降级失败。

---

## 8. Open Questions

1. `doc_object_key` 对接哪个对象存储？（MinIO / S3 / 厂内 OSS）项目里是否已有规范？
2. Seed 清单（§4.1 的 5 条）是否 OK？尤其 `src_enterprise_hse_v2` 和 `src_project_sop_v1` 是占位，需 product / 工艺档案室给出真实文件。
3. 条款级更新通知机制：当 `constraint_sources.version` 升版时，是否自动标记所有引用它的 constraint 为 `review_required = true`？当前 ADR 暂不包含该字段，可下一轮补。
4. `scope.condition` 的 DSL 先不定义（占位 string 字段），等有真实用例后再设计。

### 8.1 Recommended Resolutions（作者建议，待 product 终审）

#### Q1 · 对象存储 → **MinIO（已就绪，直接复用）**

理由：`docker-compose.yml` 里已存在 `proline-minio` 服务（端口 9000/9001，注释原文"对象存储 — proof artifacts、PDF、CAD 文件"），生态完整，无需再引入 S3 依赖。落地规则：

- 独立 bucket：`constraint-corpus`
- 目录约定：`s3://constraint-corpus/{authority}/{source_id}/v{version}/{filename}`
  - 例：`s3://constraint-corpus/statutory/src_gb50016_2014/v2018/GB50016-2014.pdf`
- DB 字段 `doc_object_key` 存**完整 URI**（`s3://...`），而非裸 key，未来切换 S3 / 阿里云 OSS / 厂内 OSS 时只改前缀
- 访问走 presigned URL，有效期 1h；长期链接走专用 `/constraint-sources/{sid}/download` 路由带 RBAC
- 不入库的 clause_text（>2KB）落在同级 `.clauses/{clause_id}.txt` 以便 RAG 增量索引

#### Q2 · Seed 清单 → **缩减到 3 条真 MVP，占位不进 seed**

原 §4.1 的 5 条中，`src_enterprise_hse_v2` 和 `src_project_sop_v1` 是无主占位，放进 seed migration 反而造就"永远的 TODO"和误导性 citation。建议：

| source_id | 理由 |
|---|---|
| `src_gb50016_2014` ✅ | GB 国标公开、条款正文允许合理引用；消防疏散是航空产线的硬门槛 |
| `src_gb5083_2008` ✅ | GB 国标公开；设备安全距离几乎每个 layout 都会触发 |
| `src_as9100d`    ✅ | 航空强标的身份标识；正文因版权**不入 MinIO**，只存 metadata + 官方链接 |
| ~~`src_enterprise_hse_v2`~~ | **移出 seed**。由 product 从工艺档案室拿到第一份 PDF 后，走 `POST /constraint-sources` 录入 |
| ~~`src_project_sop_v1`~~ | **移出 seed**。跟着具体项目走，由 S2-ConstraintAgent 在 `extractSOP` 时自动建档 |

版权红线：
- **GB 国标**：短条款引用（<=2KB）入 `clause_text`，PDF 全文不分发；`doc_object_key` 留空
- **AS / NADCAP / ISO / IPC / Boeing BPI / Airbus MPS**：**元数据 + 官方购买链接**，正文一律不入库，由 RAG 侧对接厂内已授权的访问渠道
- **HB/GJB**：企业内网可访问的放 MinIO 内网 bucket，加 RBAC 白名单
- **项目 SOP / MBD**：项目私有资产，可以全文入库

#### Q3 · 条款升版通知 → **做，但只标记、不自动降级**

引入轻量级升版追踪，避免"沉默的过期依据"：

```sql
-- 增到 constraint_citations：上次审核时引用的 source 版本
ALTER TABLE constraint_citations
    ADD COLUMN reviewed_at_version VARCHAR(40);

-- 升版事件审计表
CREATE TABLE constraint_source_version_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id     VARCHAR(80) NOT NULL REFERENCES constraint_sources(source_id),
    old_version   VARCHAR(40),
    new_version   VARCHAR(40) NOT NULL,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by    VARCHAR(100),
    release_notes TEXT
);
```

行为：
- `PATCH /constraint-sources/{sid}` 改了 `version` 字段时，**自动**插一条 `version_event`，但**不**改任何 citation
- UI 用 SQL 反查 `reviewed_at_version != sources.version` 的 citation，对应约束展示 ⚠ "依据已升版，待复核"
- **不**自动把 constraint 置为 inactive、不触发 unpublish；因为"新版规范更严"和"新版规范更松"都存在，必须人评
- reviewer 人工点击 "Acknowledge" 后 `reviewed_at_version := sources.version`，badge 消失
- 对于**已 published 的 constraint_set**：升版事件只记录到 `version_event`，不影响历史决策的不可变性；需要响应时用 ADR-0005 的 `/clone` 起新 draft

这个字段建议合入 migration 0016，别等下一轮。

#### Q4 · `scope.condition` DSL → **不做，只当人类可读文本**

YAGNI。理由：
- 目前没有单条约束真正需要"条件化生效"的业务用例（scope.space/phase/shift 已足够覆盖 90%）
- 过早引入 CEL / JsonLogic / mini-DSL 会让 solver / sim / 前端三边都要实现解析器
- 维持 `condition: string \| null` 作为**人读说明**（例："只在湿度 > 70% 时激活"），solver 忽略
- 真出现刚需时（估计 >= 3 条独立用例），单起 ADR-00XX 设计 mini-DSL，那时再纳入 solver；现在留好 `null-safe` 字段即可

---

## 9. Next Actions


- 切 Act Mode 后：
  1. 写 `0016_constraint_evidence.py` migration 骨架
  2. 写 `0017_constraint_sources_seed.py`（只落 §4.1 的 5 条 MVP）
  3. 写 `app/schemas/constraint_sources.py` Pydantic
  4. 前端 `types.ts` 追加对应类型（纯增量，不 break 现有 UI）
- product 需反馈 §8 的 4 个问题，才能解锁 P3 RAG 对接。
