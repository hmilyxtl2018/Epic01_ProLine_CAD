# ADR-0008 · Implementation stack choices (pivots from initial PRD blueprint)

| | |
|---|---|
| **Status**     | Accepted · 2026-04-24 |
| **Scope**      | Clarifies the technology choices used to **deliver** the existing M0–M6 milestones. Milestone business goals are **unchanged** — only their implementation stack is recorded here. |
| **Supersedes** | Stack hints in original PRD / M0–M6 issue bodies (Z3, Milvus, GraphDB, Kafka, K8s) |
| **Related**    | ADR-0005 (constraint set schema) · ADR-0006 (evidence authority) · ADR-0007 (MinIO corpus layout) |

## 1 · Why this ADR exists

During Phase 1–2.3 delivery we deviated from the stack named in the original PRD. The *business goals* behind each deviation are still valid (see the milestone issues), but tooling changed. Rather than re-write the old issues, we record the rewrites here and link affected issues back to this ADR.

## 2 · Decisions

### 2.1 Rule engine — **Z3 SMT → hand-written DAG validator**

- **Original plan (M3 #23):** Z3 LIA solver + `proof.smt2` in S3.
- **Delivered (commit `553b9e3`, `app/services/constraints_validator.py`):** pure-Python validator producing a `ValidationReport` with issues of type `CYCLE / RESOURCE / TAKT / MISSING_ASSET`.
- **Why:** constraints captured so far (precedence / resource / temporal / takt) are all expressible as graph-reachability and linear inequalities; Z3 adds 400 MB of native deps + solver latency for cases we don't have. We still reserve Z3 for a future hard-constraint layer when we introduce non-linear geometry clearance constraints.
- **Impact on M3 #23:** will be **commented & left open** (deferred, re-scoped to "non-linear geometry clearance only").

### 2.2 Vector store — **Milvus → pgvector (bundled in TimescaleDB-HA image)**

- **Original plan (M1 #10):** standalone Milvus cluster, SOP 向量化导入.
- **Delivered (commit `8c705b9`):** `docker-compose.yml` now runs `timescale/timescaledb-ha:pg16-all` which bundles **pgvector + PostGIS + TimescaleDB**. The constraint corpus (6 standards) is seeded to MinIO via `scripts/sync_corpus_to_minio.py` (ADR-0007). The embedding ingest / search path is still TODO (tracked by new issues **C-2 / C-3**).
- **Why:** one fewer dependency, row-level security works natively, joins between `constraint_sources` and embeddings keep transactional integrity.

### 2.3 Ontology store — **Dedicated GraphDB (RDF) → Postgres with discriminated JSON**

- **Original plan (M1 #8, M2 #18):** GraphDB + AeroOntology-v1.0 + JSON-LD.
- **Delivered (commit `553b9e3` + prior `d143eb7`):** `asset_catalog` (0013) + Phase 1.1 AssetType union (0012) + `process_constraints` with a discriminated JSON `payload` (precedence / resource / temporal / takt). Relationships expressed as foreign keys + JSON arrays; traversal via recursive CTE.
- **Why:** single Postgres instance, no SPARQL learning curve for contributors, the production-line domain is finite (< 30 node types) so RDF's open-world model is overkill.
- **Impact on M1 #8, M2 #18:** **comment & close** with a pointer to the schema.

### 2.4 Queue — **Kafka + DLQ → `app/queue.py` + `parse_agent_worker.py`**

- **Original plan (M1 #11):** Kafka topics + DLQ + consumer groups.
- **Delivered:** in-process queue + Redis-backed job registry, with quarantine table as the DLQ equivalent (see `tests/app/test_quarantine.py`). CDC slots were pre-configured in `8c705b9` so Kafka can be added later without re-doing Postgres setup (`wal_level=logical`, `max_replication_slots=4`).
- **Why:** single-worker POC; Kafka will reappear in Phase B (multi-agent scaling) without needing to change call sites.
- **Impact on M1 #11:** **left open**, re-scoped to Phase B.

### 2.5 Orchestration — **K8s → Docker Compose for dev, TBD for prod**

- **Original plan (M0 #5):** K8s-ready.
- **Delivered:** `docker-compose.yml` (dev) + `db/docker-compose.db.yml` (CI). Prod topology not chosen yet.
- **Impact:** **left open**, tracked as M6 work.

## 3 · Net effect on milestones

Milestone goals are unchanged. The "落地选型" column in `docs/MILESTONE_REVIEW_2026-04-24.md` is the authoritative per-issue mapping.

## 4 · Reversal criteria

Any of §2.1–§2.4 can be reverted; the gate for re-introducing Z3 is "we hit a constraint the DAG validator cannot express"; for Milvus it is "pgvector recall@10 < 0.9 at 1 M vectors"; for GraphDB it is "we need transitive reasoning across > 3 hops at query time"; for Kafka it is "> 1 agent consumer group needed in prod".
