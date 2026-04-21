# 数据资产台账 (Data Inventory)

> 用途: 合规 / DR / 安全审计的字段级登记表。每张表的每一列都标注:
> 类别 (PII / business / audit / metadata) · 加密方式 · 保留周期 · owner。
> 当 Pydantic 或 DDL 新增字段时,**同一 PR 必须更新本台账**,否则 PR review 拒绝。

约定:
- **类别**: `PII` (个人身份信息) | `BIZ` (业务数据) | `AUD` (审计) | `META` (技术元数据)
- **加密**: `at-rest` (PG TDE / MinIO SSE-S3) | `app` (应用层 AES-256-GCM) | `none`
- **保留**: hot tier (TimescaleDB retention) / warm tier (MinIO lifecycle) / 永久 (软删除)
- **owner**: Agent 或团队角色,变更时通知该 owner

---

## 1. mcp_contexts (Timescale hypertable, 30d retention)

| 字段 | 类型 | 类别 | 加密 | 保留 | owner | 备注 |
|---|---|---|---|---|---|---|
| id | UUID | META | at-rest | 30d | Orchestrator | PK |
| mcp_context_id | VARCHAR(100) | META | at-rest | 30d | Orchestrator | 全局可见的脊椎 ID |
| agent | VARCHAR(50) | META | at-rest | 30d | Orchestrator | parse / constraint / layout / ... |
| agent_version | VARCHAR(20) | META | at-rest | 30d | Orchestrator | |
| parent_context_id | VARCHAR(100) | META | at-rest | 30d | Orchestrator | 自引用 FK |
| input_payload | JSONB | BIZ | at-rest | 30d | Agent | **不得放原始 PII**,DWG 用 sha256 引用 |
| output_payload | JSONB | BIZ | at-rest | 30d | Agent | |
| timestamp | TIMESTAMPTZ | META | at-rest | 30d | Agent | hypertable 时间列 |
| latency_ms | INT | META | at-rest | 30d | Agent | |
| provenance | JSONB | AUD | at-rest | 30d | Agent | 含 user_id / ip / agent_build |
| status | VARCHAR(30) | META | at-rest | 30d | Agent | |
| error_message | TEXT | META | at-rest | 30d | Agent | 不得 dump secrets |
| step_breakdown | JSONB | META | at-rest | 30d | Agent | |
| created_at | TIMESTAMPTZ | META | at-rest | 30d | DB | |
| schema_version | SMALLINT | META | at-rest | 30d | DB | |
| deleted_at | TIMESTAMPTZ | META | at-rest | 30d | DB | 软删除 |

冷归档: >30d 通过 `scripts/export_cold_mcp_to_parquet.py` 导出 Parquet 到 MinIO cold bucket,7 年保留。

---

## 2. site_models (永久 + 软删除)

| 字段 | 类型 | 类别 | 加密 | 保留 | owner |
|---|---|---|---|---|---|
| id | UUID | META | at-rest | 永久 | ParseAgent |
| site_model_id | VARCHAR(50) | META | at-rest | 永久 | ParseAgent |
| cad_source | JSONB | BIZ | at-rest | 永久 | ParseAgent | dwg_hash + uri 引用 MinIO,不存原文件 |
| assets | JSONB | BIZ | at-rest | 永久 | ParseAgent |
| links | JSONB | BIZ | at-rest | 永久 | ParseAgent |
| geometry_integrity_score | NUMERIC(5,4) | BIZ | at-rest | 永久 | ParseAgent |
| statistics | JSONB | META | at-rest | 永久 | ParseAgent |
| mcp_context_id | VARCHAR(100) | META | at-rest | 永久 | ParseAgent | FK lineage |
| bbox | geometry(Polygon,0) | BIZ | at-rest | 永久 | ParseAgent | GIST |
| schema_version / deleted_at / created_at / updated_at | -- | META | at-rest | 永久 | DB |

---

## 3. asset_geometries (永久 + 软删除)

| 字段 | 类型 | 类别 | 加密 | 保留 | owner | 约束 |
|---|---|---|---|---|---|---|
| id | UUID | META | at-rest | 永久 | ParseAgent | |
| site_model_id | VARCHAR(50) | META | at-rest | 永久 | ParseAgent | FK |
| asset_guid | VARCHAR(50) | BIZ | at-rest | 永久 | ParseAgent | UNIQUE(site_model_id, asset_guid) |
| asset_type | VARCHAR(30) | BIZ | at-rest | 永久 | ParseAgent | CHECK enum (14 值) |
| footprint | geometry(Polygon,0) | BIZ | at-rest | 永久 | ParseAgent | GIST |
| centroid | geometry(Point,0) | BIZ | at-rest | 永久 | ParseAgent | |
| confidence | NUMERIC(4,3) | BIZ | at-rest | 永久 | ParseAgent | CHECK [0,1] |
| classifier_kind | VARCHAR(40) | META | at-rest | 永久 | ParseAgent | gold / llm / heuristic |
| mcp_context_id | VARCHAR(100) | META | at-rest | 永久 | ParseAgent | FK lineage |
| schema_version / deleted_at | -- | META | at-rest | 永久 | DB |

Phase B (rev 0006) 将新增 `embedding vector(384)`,类别 BIZ,owner ParseAgent。

---

## 4. constraint_sets / layout_candidates / workflows

| 表 | 关键字段 | 类别 | 加密 | 保留 | owner |
|---|---|---|---|---|---|
| constraint_sets | hard_constraints / soft_constraints (JSONB) | BIZ | at-rest | 永久 | ConstraintAgent |
| layout_candidates | reasoning_chain (JSONB) | BIZ + AUD | at-rest | 永久 | LayoutAgent |
| workflows | context_chain (JSONB), state | META | at-rest | 永久 | Orchestrator |

三表均含三列模板 (schema_version / deleted_at / mcp_context_id),保留与加密同上。

---

## 5. audit_logs (决策签发,永久)

| 字段 | 类型 | 类别 | 加密 | 保留 | owner | 备注 |
|---|---|---|---|---|---|---|
| audit_id | VARCHAR(100) | AUD | at-rest | 永久 | ReviewerService | UNIQUE |
| decision | VARCHAR(30) | AUD | at-rest | 永久 | ReviewerService | approve/reject |
| mcp_context_ids | JSONB (list) | AUD | at-rest | 永久 | ReviewerService | 可挂多个上下文 |
| approver | VARCHAR(200) | **PII** | at-rest + app (AES-256) | 永久 | ReviewerService | 用户名 / 邮箱前缀 |
| signature | TEXT | AUD | at-rest | 永久 | ReviewerService | 数字签名 |
| pdf_sha256 | VARCHAR(64) | AUD | at-rest | 永久 | ReviewerService | |
| artifact_urls | JSONB | META | at-rest | 永久 | ReviewerService | MinIO 引用 |
| timestamp / created_at / schema_version / deleted_at | -- | META | at-rest | 永久 | DB | |

---

## 6. Phase B 待登记 (W2 写入)

| 表 | 计划 owner | PII 字段 | 备注 |
|---|---|---|---|
| taxonomy_terms | TaxonomyService | approved_by (PII, AES-256) | gold/llm/manual 来源标记 |
| quarantine_terms | TaxonomyService | decided_by (PII, AES-256) | evidence 中可能含 DWG block 名 (BIZ) |
| audit_log_actions | All agents (write-only) | actor (PII, AES-256) | action-level,与 audit_logs 决策表互补 |

---

## 7. PG 角色 + RLS (W2 实施)

| 角色 | 权限 | 适用表 |
|---|---|---|
| `parse_agent_rw` | SELECT/INSERT/UPDATE | mcp_contexts / site_models / asset_geometries / quarantine_terms |
| `dashboard_ro` | SELECT (deleted_at IS NULL) | 所有业务表 |
| `dashboard_rw` | + INSERT into audit_log_actions | 同上 |
| `reviewer` | + UPDATE quarantine_terms.decision / INSERT taxonomy_terms | taxonomy / quarantine / audit_logs |
| `admin` | ALL | 所有表 |

RLS 启用方法见 ExcPlan plan r2 §3.8;启用后 dashboard_ro 自动只读 `WHERE deleted_at IS NULL` 的行。

---

## 8. 维护流程

1. **新增字段**: PR 必须同时改 `shared/models.py` (Pydantic) +
   `shared/db_schemas.py` (SQLAlchemy) + `db/alembic/versions/` (revision) +
   本台账。CI 漂移检查 (B4) 是 last-line-of-defense。
2. **变更字段类型/语义**: 触发 `schema_version++`,在本台账"备注"列写明 breaking 性质。
3. **删除字段**: expand-migrate-contract,本台账标 `[deprecated YYYY-MM-DD, dropped at vN]`。
4. **季度审计**: 每季度 owner 复核 PII 字段加密 + 保留期是否符合最新合规要求。
