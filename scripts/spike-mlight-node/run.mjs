// MLightCAD Node spike — single-file probe.
//
// Usage:   node run.mjs <path-to-file.dwg|.dxf>
//
// Goals (record findings in SPIKE_REPORT.md, NOT here):
//   Q1  pure import of @mlightcad/* under Node — any window/document refs?
//   Q2  libredwg WASM load + DWG parse end-to-end
//   Q3  duration_ms / peak_rss_mb / ontology_size_bytes
//   Q4  ontology JSON shape (top-level keys, sample of layers/blocks/entities)
//   Q5  worker_threads substitution — out of scope for v1; flagged TODO
//
// Discipline: this is a SPIKE. Hard-code things, log liberally, don't
// abstract. Findings go to SPIKE_REPORT.md, then this file is deleted or
// rewritten properly in Phase 2.

import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

// ── Web Worker polyfill (Node has no Web Worker API; libredwg-converter
// hard-codes useWorker=true). The `web-worker` package wraps Node's
// `worker_threads` to expose the browser's `Worker` interface globally.
import Worker from "web-worker";
globalThis.Worker = Worker;

const require = createRequire(import.meta.url);
// Resolve the worker file shipped INSIDE the converter package — that's the
// same artefact the browser bundle copies to web/public/mlight/workers/.
// The package's `exports` map doesn't expose dist/ files, so resolve via
// its main entry then walk to the sibling worker file.
const converterMainPath = require.resolve("@mlightcad/libredwg-converter");
const PARSER_WORKER_URL = pathToFileURL(
  path.join(path.dirname(converterMainPath), "libredwg-parser-worker.js"),
).href;

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.join(__dirname, "output");

// ── arg parsing ───────────────────────────────────────────────────────
const inputPath = process.argv[2];
if (!inputPath) {
  console.error("usage: node run.mjs <path-to-file.dwg|.dxf>");
  process.exit(2);
}
const ext = path.extname(inputPath).toLowerCase();
if (ext !== ".dwg" && ext !== ".dxf") {
  console.error(`unsupported extension: ${ext} (expected .dwg or .dxf)`);
  process.exit(2);
}

// ── metrics scaffolding ───────────────────────────────────────────────
const t0 = performance.now();
const peakRss = { value: process.memoryUsage().rss };
const rssTimer = setInterval(() => {
  const r = process.memoryUsage().rss;
  if (r > peakRss.value) peakRss.value = r;
}, 50);

function metric(stage, extra = {}) {
  console.log(
    JSON.stringify({
      stage,
      t_ms: +(performance.now() - t0).toFixed(1),
      rss_mb: +(process.memoryUsage().rss / 1024 / 1024).toFixed(1),
      ...extra,
    }),
  );
}

// ── Q1: pure import probe ─────────────────────────────────────────────
metric("import:start");
let dataModel, converterMod;
try {
  dataModel = await import("@mlightcad/data-model");
  metric("import:data-model:ok", { keys: Object.keys(dataModel).length });
} catch (e) {
  metric("import:data-model:FAIL", { error: String(e), stack: e.stack });
  process.exit(1);
}
try {
  converterMod = await import("@mlightcad/libredwg-converter");
  metric("import:libredwg-converter:ok", {
    keys: Object.keys(converterMod).length,
  });
} catch (e) {
  metric("import:libredwg-converter:FAIL", {
    error: String(e),
    stack: e.stack,
  });
  process.exit(1);
}

const { AcDbLibreDwgConverter } = converterMod;
if (typeof AcDbLibreDwgConverter !== "function") {
  metric("import:no-converter-class", {
    exports: Object.keys(converterMod),
  });
  process.exit(1);
}

// ── Q2: load file + parse ─────────────────────────────────────────────
const fileBuf = await readFile(inputPath);
const sha256 = createHash("sha256").update(fileBuf).digest("hex");
const fileStat = await stat(inputPath);
metric("file:loaded", {
  filename: path.basename(inputPath),
  size_bytes: fileStat.size,
  sha256,
});

let converter;
try {
  converter = new AcDbLibreDwgConverter({
    useWorker: true,
    parserWorkerUrl: PARSER_WORKER_URL,
  });
  metric("converter:constructed", { workerUrl: PARSER_WORKER_URL });
} catch (e) {
  metric("converter:construct:FAIL", { error: String(e), stack: e.stack });
  process.exit(1);
}

// Unwrap to ArrayBuffer (libredwg expects ArrayBuffer, not Node Buffer).
const ab = fileBuf.buffer.slice(
  fileBuf.byteOffset,
  fileBuf.byteOffset + fileBuf.byteLength,
);

let db;
try {
  // AcDbDatabaseConverter exposes `.read(data)` as the public entry.
  // Fall back to whichever method exists on the instance.
  if (typeof converter.read === "function") {
    db = await converter.read(ab);
  } else if (typeof converter.parse === "function") {
    // `.parse` is protected in the .d.ts but JS exposes it.
    db = await converter.parse(ab);
  } else {
    metric("converter:no-entry-method", {
      methods: Object.getOwnPropertyNames(
        Object.getPrototypeOf(converter),
      ),
    });
    process.exit(1);
  }
  metric("converter:parse:ok");
} catch (e) {
  metric("converter:parse:FAIL", { error: String(e), stack: e.stack });
  process.exit(1);
}

// ── Q3 + Q4: shape + size ─────────────────────────────────────────────
function describe(value, depth = 0) {
  if (value === null) return { _t: "null" };
  if (Array.isArray(value)) {
    return {
      _t: "array",
      _len: value.length,
      _sample: value.length && depth < 2 ? describe(value[0], depth + 1) : undefined,
    };
  }
  const t = typeof value;
  if (t !== "object") return { _t: t };
  const out = { _t: "object" };
  for (const k of Object.keys(value).slice(0, 25)) {
    out[k] = depth < 2 ? describe(value[k], depth + 1) : { _t: typeof value[k] };
  }
  return out;
}

const dbShape = describe(db);
let dbJson = null;
let serializeError = null;
try {
  dbJson = JSON.stringify(db);
} catch (e) {
  serializeError = String(e);
}

clearInterval(rssTimer);
const totalMs = +(performance.now() - t0).toFixed(1);
const peakRssMb = +(peakRss.value / 1024 / 1024).toFixed(1);

const report = {
  source: {
    filename: path.basename(inputPath),
    size_bytes: fileStat.size,
    sha256,
    ext,
  },
  parse: {
    ok: true,
    duration_ms: totalMs,
    peak_rss_mb: peakRssMb,
    serialize_error: serializeError,
  },
  ontology_shape: dbShape,
  ontology_size_bytes: dbJson ? Buffer.byteLength(dbJson) : null,
};

await mkdir(OUT_DIR, { recursive: true });
const stem = path.basename(inputPath, ext) + "_" + sha256.slice(0, 8);
await writeFile(
  path.join(OUT_DIR, stem + ".meta.json"),
  JSON.stringify(report, null, 2),
);
if (dbJson) {
  await writeFile(path.join(OUT_DIR, stem + ".ontology.json"), dbJson);
}

metric("done", {
  out_meta: path.join(OUT_DIR, stem + ".meta.json"),
  out_size_bytes: report.ontology_size_bytes,
});
