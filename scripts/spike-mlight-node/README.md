# MLightCAD Node spike

**Status**: in-progress (Phase 1)

**Goal** — answer 5 yes/no questions in ≤ 2 days:

| # | Question |
|---|---|
| Q1 | Can `@mlightcad/*` be `import`ed under Node 18+ without `window`/`document` errors? |
| Q2 | Does the libredwg WASM load in Node and parse a real DWG? |
| Q3 | What are duration / RSS / output size on small / medium / large samples? |
| Q4 | What is the MLightCAD ontology JSON shape? Which fields are NEW vs the existing DXF baseline ontology? |
| Q5 | Can `worker_threads` substitute for the browser Web Workers (to keep parsing off the FastAPI event loop)? |

**Decision gate** at end of `SPIKE_REPORT.md`: GREEN → Phase 2; YELLOW → constrained Phase 2; RED → evaluate alternatives.

## Layout

```
scripts/spike-mlight-node/
  README.md          (this file)
  package.json       (own npm install — does NOT touch web/)
  run.mjs            (entry: node run.mjs <file.dwg|.dxf>)
  fixtures/          (drop sample files here, gitignored)
  output/            (run.mjs writes JSON + metrics here, gitignored)
  SPIKE_REPORT.md    (Q1–Q5 answers + decision; produced at the end)
```

## Quick start

```powershell
cd Epic01_ProLine_CAD/scripts/spike-mlight-node
npm install
# drop a real file into fixtures/, then:
node run.mjs fixtures/sample.dwg
```

## Non-goals

- Do **NOT** touch `app/`, `db/migrations/`, schemas, or models in this spike.
- Do **NOT** import this spike's code from the FastAPI app.
- Do **NOT** publish or commit `output/` artefacts (gitignored).
