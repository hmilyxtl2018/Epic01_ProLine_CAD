# Milestone Review — 2026-04-24

Generated after the 4-commit cleanup of `main` that closed out Phase 2.2/2.3
constraint work and the corpus/infra upgrade.

---

## 1 · Local vs remote

```
local main  ahead of origin/main by 7 commits, 0 dirty files.

  2038383  feat(parse+devx):  enrichment/llm/parse service layer + dashboard refactor + misc
  eb7765d  fix(constraints-web): ConstraintForm union + A-2 enable/delete controls
  8c705b9  feat(infra):        MinIO corpus + Postgres HA (TimescaleDB/PostGIS/pgvector)
  553b9e3  feat(constraints):  CRUD + validator + evidence schema + Phase 1.1 taxonomy
  d143eb7  feat(S2):           工艺约束支持新建 (earlier session)
  46c911e  feat(S2):           CRUD + reactflow/dagre DAG (earlier session)
  49b985d  feat(web):          MLightCAD A/B alternative                     (earlier session)

origin/main  0a052e1  test(web): bootstrap Vitest (jsdom) + Playwright smoke harness
```

**Action:** `git push origin main` once the review below is accepted.

---

## 2 · Mapping commits → likely existing milestones / epics

Adjust column 3 as needed based on what actually exists on GitHub.

| Commit | Scope | Milestone it should close / advance |
|---|---|---|
| 553b9e3 | Phase 2.2 CRUD + 2.3 evidence schema + 0012–0016 + ADR-0005/0006 | **M-Phase-2.2 process_constraints** (likely close) + **M-Phase-2.3 constraint-evidence** (advance but not close — still need backend endpoints) |
| 8c705b9 | MinIO corpus, Postgres HA upgrade (TS/PostGIS/pgvector), ADR-0007 | **M-Constraint-Corpus-Bootstrap** (close — seeds loaded) · **M-Infra-pgvector-ready** (close — image in place) |
| eb7765d | Frontend bug fix + A-2 enable/delete | **M-Phase-2.3a-UI** (advance — form, create, list, enable/delete done; still missing evidence picker) |
| 2038383 | parse/llm/enrichment service layer + dashboard wiring | **M-Phase-1-Parse-Agent-refactor** (likely close — moves parse into a clean service module) |

---

## 3 · Issues that should change status

### → Close / mark done
- Any issue titled *"ConstraintsPanel 新建表单 TS 错误 / bug"* (or similar) — **fixed in eb7765d**
- Any issue titled *"Phase 2.2 — /constraints CRUD endpoints"* — **delivered in 553b9e3**
- Any issue titled *"Constraint evidence schema (authority / conformance / scope / citations)"* — DB side is **delivered in 553b9e3**; note the sub-task for API endpoints is still open (see §4)
- Any issue titled *"bootstrap MinIO corpus + 6 reference standards"* — **delivered in 8c705b9**
- Any issue titled *"upgrade Postgres image to include PostGIS + TimescaleDB + pgvector"* — **delivered in 8c705b9**
- Any issue titled *"ConstraintsPanel: enable/disable + soft-delete buttons"* (or "A-2") — **delivered in eb7765d**

### → Update comment but keep open
- *"Phase 2.3 evidence layer"* epic — DB + corpus done, backend endpoints + UI picker still pending; add progress comment linking the 4 commits
- *"LLM enrichment pipeline (A..M sections)"* epic — core service extracted in 2038383; content-level tuning likely ongoing

---

## 4 · New issues to open (because the code now requires them)

These correspond to the "A-3 / B / C" plan the user chose to continue after this milestone review:

1. **`B-1 · GET /constraint-sources` endpoint**
   - file: `app/routers/constraint_sources.py` (new)
   - schema: paginated list of `constraint_sources` rows, filterable by `authority` / `tags`
   - blocker for A-3

2. **`B-2 · POST /constraints/{cid}/citations` (+ DELETE)**
   - file: `app/routers/constraints.py` sub-router or new `app/routers/constraint_citations.py`
   - binds an existing constraint to ≥1 source clause with `quote / confidence / derivation / reviewed_at_version`
   - note real table name is **`constraint_citations`** (not `constraint_evidence`, even though that was the ADR working title)

3. **`B-3 · Mirror `ck_authority_class_coherence` in Pydantic**
   - Today the DB CHECK returns opaque 500s on violation.
   - Add a Pydantic root validator that enforces R1/R2 from ADR-0006 §2.1 so the user sees a 422 with a clear message.
   - Also extend `ConstraintItem` schema to return `authority / conformance / scope` to the frontend.

4. **`A-3 · ConstraintForm evidence picker`**
   - After B-1, add a multi-select searchable dropdown at the bottom of the form.
   - On submit: create constraint, then (in the same mutation) create N `constraint_citations` rows.

5. **`C-1 · Sample clauses/*.md` under MinIO corpus**
   - Author `industry/src_as9100d_2016/vAS9100D-2016/clauses/8.1.4.md` and `8.4.2.md` as the first concrete RAG samples.

6. **`C-2 · scripts/index_corpus.py` → pgvector**
   - pgvector is already available in the new image (`8c705b9`). Add an embedding table + ingest script that walks every `clauses/*.md` in MinIO.

7. **`C-3 · Semantic search in A-3 picker`**
   - Replace the plain-text filter in the B-1 dropdown with a `POST /constraint-sources/search` endpoint that queries pgvector.

---

## 5 · Recommended next move

1. `git push origin main` (nothing in the 7 commits is experimental; all four new ones have clean tsc / no dirty tree).
2. Install `gh` CLI (`winget install GitHub.cli`) so this list can be turned into real Issue/Milestone state changes instead of a markdown checklist.
3. Open the 7 issues above, slot them under the existing epic **M-Phase-2.3 evidence** (or create a new **M-Phase-2.3b evidence API** milestone to keep the epic tidy).
4. Resume the `A-3 → B → C` execution plan from that new milestone.
