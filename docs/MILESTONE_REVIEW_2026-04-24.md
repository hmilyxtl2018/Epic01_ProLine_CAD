# Milestone Review — 2026-04-24 (revised)

Generated after the 4-commit cleanup of `main` that closed out Phase 2.2/2.3
constraint work and the corpus/infra upgrade.

> **Revision note (same day):** the first version of this document
> proposed creating a new milestone `M-Phase-2.3b`. That was wrong —
> milestones are **business goals**, not tech stacks. The 7 existing
> milestones (M0–M6) stay untouched; only the **implementation stack**
> changed, which is what ADR-0008 records.

---

## 1 · Local vs remote

```
pushed.  origin/main = HEAD = 83979a3 (after this doc's revision, a new commit will follow).

This cleanup covers these 4 locally-made commits (plus the earlier 3 already waiting):
  2038383  feat(parse+devx):  enrichment/llm/parse service layer + dashboard + misc
  eb7765d  fix(constraints-web): ConstraintForm type bug + A-2 enable/delete
  8c705b9  feat(infra):        MinIO corpus + Postgres HA (TS/PostGIS/pgvector)
  553b9e3  feat(constraints):  CRUD + validator + evidence schema + Phase 1.1 taxonomy
```

---

## 2 · Per-issue status (authoritative mapping)

Legend: ✅ done · 🟡 partial · 🔴 not started · 🔁 stack pivoted (see ADR-0008)

### M0 · 项目准备与发现
| # | Title | Status | Notes |
|---|---|---|---|
| 1  | 收集 5-10 个代表性 CAD 样本 + 回归集 | 🟡 | `tests/fixtures/cad/sample_factory.dxf` + `exp/parse_results/run_p0_all/*`; CS-001 正式回归集仍缺 |
| 2  | 约束库 CS-001（15+ 约束）         | 🟡 | 6 本标准 seeds + schema ready (commit 8c705b9)；15 条具体约束待录入 |
| 3  | 技术评估（Z3 / CAD / GraphDB）    | ✅ | 由 ADR-0005 / 0006 / 0007 / **0008** 共同交付 |
| 4  | 需求确认（格式 / 角色 / 审批）    | ✅ | DXF + 4 角色 RBAC + quarantine-decide 已上线 |
| 5  | K8s/Docker 环境                   | 🟡 | Docker ✅；K8s → ADR-0008 §2.5 推迟到 M6 |
| 6  | CI/CD 基础管道                    | 🟡 | Vitest + Playwright + pytest 架子 ✅；GH Actions 配置待完善 |

### M1 · 基础设施 & MCP Toolbelt
| # | Title | Status | Notes |
|---|---|---|---|
| 7  | PostgreSQL DDL + mcp_context    | ✅ | 0001–0016 共 15 迁移；0014 process_constraints / 0015-16 evidence |
| 8  | GraphDB + AeroOntology         | 🔁→✅ | ADR-0008 §2.3：由 `asset_catalog` + `process_constraints` discriminated JSON 等价交付 |
| 9  | AuditStore S3+DB 双冗余         | 🟡 | `audit_log_actions` DB 侧 ✅；S3/MinIO 冗余写入路径待补 |
| 10 | Milvus + SOP 向量化             | 🔁 | ADR-0008 §2.2：改用 pgvector（镜像已内置）；ingest/search endpoint 拆给新 Issue **C-2 / C-3** |
| 11 | Kafka 主题 + DLQ               | 🔁 | ADR-0008 §2.4：改用 `app/queue.py` + quarantine 表；CDC slots 已预配给 Phase B |
| 12 | mcp_context JSON Schema 文档   | 🟡 | 代码有，schema.md 需补 |
| 13 | `/mcp/tool/retrieve_sop`       | 🔴 | 即将由 **C-3** 实现（接口名保留 `/mcp/tool/retrieve_sop` 以维持 PRD 路径兼容） |
| 14 | `/mcp/tool/publish_audit_record` | 🟡 | audit 写入 DB 已有；独立 endpoint 待查 |

### M2 · ParseAgent
| # | Title | Status | Notes |
|---|---|---|---|
| 15 | format_detect + entity_extract | ✅ | `app/services/parse/` + `agents/parse_agent/`（commit 2038383 + 之前） |
| 16 | topology_repair + coord_normalize | 🟡 | 框架到位，`geometry_integrity_score >= 0.85` 未验证 |
| 17 | classify_entity + confidence_scoring | 🟡 | `app/services/enrichment/` 有分类，但 `avg_confidence >= 0.90` 基准测试待跑 |
| 18 | Ontology 图谱 JSON-LD + GraphDB | 🔁 | ADR-0008 §2.3，由 Postgres JSON 等价代替 |
| 19 | SiteModel 持久化 + 检索 | 🟡 | Run 表有，SiteModel 专用表/接口待确认 |
| 20 | ParseAgent REST `/mcp/agent/parse` | 🟡 | `/dashboard/runs` POST 功能等价；PRD 路径别名待补（与 #13 同策略） |
| 21 | ParseAgent 单元+集成测试 | 🟡 | `test_parse_agent_worker.py` + `test_cad_parser.py` ✅；回归集覆盖率待测 |

### M3 · ConstraintAgent
| # | Title | Status | Notes |
|---|---|---|---|
| 22 | ConstraintLoader | ✅ | commit `553b9e3`：`app/routers/constraints.py` + `app/services/constraints_validator.py` |
| 23 | Z3 SolverInvoker | 🔁 | ADR-0008 §2.1：已由 `constraints_validator.py` 覆盖当前所有约束类型；Z3 本身**推迟**到非线性几何 clearance 约束出现时再引入 |
| 24 | SoftScorer | 🟡 | `priority` + `conformance` 字段 ✅；独立 scorer service + `score = 0.4*间距合规 + …` 公式待实现 |
| 25 | 硬约束冲突报告 + Reasoning Chain | ✅ | `ValidationReport` + `ValidationIssue(type, affected_assets, description)` + source 引用 |
| 26 | LLM-assisted ConstraintTranslator | 🟡 | enrichment 通用 LLM 框架 ✅；`/mcp/tool/constraint_translate` 专项 endpoint 待做（属于 **A-3** 之后的 C 系列延伸） |
| 27 | ConstraintAgent REST + 测试 | 🟡 | REST ✅；`纯硬约束检出率 = 100%` / `假阳 < 0.2%` 基准测试待跑 |

### M4 · LayoutAgent（未启动）· M5 · 编排+LLM+UI（部分）· M6 · 测试+部署（部分）
这些留到下次 review（本轮 commit 不直接触及）。

---

## 3 · Actions to take on GitHub (this review cycle)

### 3.1 Close (4 issues)

| # | Milestone | Closing comment will reference |
|---|---|---|
| 3  | M0 | ADR-0005 / 0006 / 0007 / 0008（技术评估 = 4 篇 ADR） |
| 8  | M1 | ADR-0008 §2.3 + commit 553b9e3（Ontology 由 Postgres JSON 落地） |
| 22 | M3 | commit 553b9e3（ConstraintLoader = `constraints_validator.py`） |
| 25 | M3 | commit 553b9e3（`ValidationReport` 已按 AC 输出结构化冲突 + reasoning） |

### 3.2 Comment-only (progress update, keep open)

`#1 #2 #5 #6` (M0) · `#7 #9 #10 #11 #12 #14` (M1) · `#15–21` (M2) · `#23 #24 #26 #27` (M3)

Each comment will (a) give the ✅/🟡/🔁 status from §2; (b) link the most relevant commit(s); (c) for 🔁 items, link ADR-0008.

### 3.3 Open 7 new issues

| New | Milestone | Title | Blocks |
|---|---|---|---|
| A-3 | M3 | ConstraintForm evidence 选择器（UI） | — |
| B-1 | M3 | `GET /constraint-sources` endpoint                    | A-3 |
| B-2 | M3 | `POST /constraints/{cid}/citations` + DELETE           | A-3 |
| B-3 | M3 | Pydantic 镜像 `ck_authority_class_coherence`           | A-3 |
| C-1 | M1 | corpus: 样本 `clauses/*.md`（AS9100D §8.1.4 / §8.4.2） | C-2 |
| C-2 | M1 | `scripts/index_corpus.py` → pgvector（对应 #10 落地）  | C-3 |
| C-3 | M1 | `POST /constraint-sources/search` (+ `/mcp/tool/retrieve_sop` alias，对应 #13) | — |

> A-3 / B-* 做完自然推进 #26 #27；C-* 做完自然可 close #10 #13。

---

## 4 · Execution

A one-shot PowerShell block will perform §3.1 / §3.2 / §3.3 via `gh` CLI, logging every command. The driver lives inline (没有新加 `scripts/milestone_sync.py`，因为这是一次性操作).
