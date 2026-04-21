# ADR-004: Reserve pgvector infrastructure ahead of demand

**Status:** Accepted (2026-04-20)
**Context:** ExcPlan plan r2 §3.4.2 (T3 / B3)

## Decision

Install the `pgvector` extension and add a NULL `vector(384)` column to
`asset_geometries` in revision `0006`, **without** creating an ivfflat or hnsw
index. The column is a reservation, not a production feature.

## Forces

- ParseAgent's `propose_taxonomy_term` produces text candidates that semantic
  retrieval would benefit from (find near-duplicates in `taxonomy_terms`).
- pgvector's index types penalize empty / sparse columns at write time; an
  index built on an empty column also has to be rebuilt once data lands.
- Adding a column later via `ALTER TABLE` is cheap, but installing the
  extension on a busy production cluster requires an explicit maintenance
  window — pre-installing it on every fresh dev / CI database now removes
  that future friction.

## Consequences

**Positive**
- Future "search similar terms" feature can ship as an additive change with
  no migration ceremony.
- The 384-dim choice aligns with `sentence-transformers/all-MiniLM-L6-v2`
  which is already vendored in the dependency surface for local-only embed.

**Negative / open**
- Drift CI must learn to ignore the `embedding` column when comparing against
  the `AssetGeometry` Pydantic model (it is intentionally absent there).
- A future revision will need to backfill embeddings + create the chosen
  index in two phases (`CONCURRENTLY` is mandatory on populated tables).

## Alternatives considered

1. **Defer entire pgvector adoption** — rejected: extension install on prod
   needs DBA approval and a window; doing it now is free.
2. **Adopt now with hnsw index** — rejected: empty-index cost without
   benefit.
3. **Separate `asset_embeddings` side table** — rejected for now: 1:1 with
   `asset_geometries`, no payload separation worth the join cost.

## Follow-ups

- B4 (drift CI) explicit allowlist for `asset_geometries.embedding`.
- Future ADR-005 will document the index choice (ivfflat vs hnsw) when the
  embedding pipeline is actually wired.
