// One-off bundler that takes our tiny entry (mlight-entry.mjs) plus its
// dependency tree (vue, element-plus, @mlightcad/*, etc.) and emits a single
// self-contained ESM file at web/public/mlight/bundle.js, with all CSS
// concatenated into web/public/mlight/bundle.css.
//
// We do this so the iframe at /mlight-viewer.html can load MLightCAD without
// touching any external CDN — esm.sh / esm.run kept choking on element-plus's
// `@popperjs/core: npm:@sxzz/popperjs-es` alias and on CSS-as-module imports.
//
// Usage:  node scripts/build-mlight.mjs

import { build } from "esbuild";
import vuePlugin from "esbuild-plugin-vue3";
import { mkdirSync, existsSync, copyFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");
const outdir = resolve(root, "public/mlight");
const workersDir = resolve(outdir, "workers");

if (!existsSync(outdir)) mkdirSync(outdir, { recursive: true });
if (!existsSync(workersDir)) mkdirSync(workersDir, { recursive: true });

// Copy the three worker bundles MLightCAD spawns at runtime. The library
// defaults to "./assets/<name>.js" relative to the page; we override the URLs
// in mlight-entry.mjs so they resolve to /mlight/workers/<name>.js instead.
const workerCopies = [
  ["node_modules/@mlightcad/data-model/dist/dxf-parser-worker.js", "dxf-parser-worker.js"],
  ["node_modules/@mlightcad/libredwg-converter/dist/libredwg-parser-worker.js", "libredwg-parser-worker.js"],
  ["node_modules/@mlightcad/cad-simple-viewer/dist/mtext-renderer-worker.js", "mtext-renderer-worker.js"],
];
for (const [from, to] of workerCopies) {
  const src = resolve(root, from);
  const dst = resolve(workersDir, to);
  if (!existsSync(src)) {
    console.warn(`[build-mlight] missing worker: ${from}`);
    continue;
  }
  copyFileSync(src, dst);
}

const t0 = Date.now();
await build({
  entryPoints: [resolve(root, "scripts/mlight-entry.mjs")],
  bundle: true,
  format: "esm",
  outfile: resolve(outdir, "bundle.js"),
  platform: "browser",
  target: ["es2022"],
  minify: true,
  sourcemap: false,
  legalComments: "none",
  // Tell esbuild how to handle non-JS assets that come in via deps.
  loader: {
    ".css": "css",       // CSS gets emitted to bundle.css alongside bundle.js
    ".svg": "dataurl",
    ".woff": "dataurl",
    ".woff2": "dataurl",
    ".ttf": "dataurl",
    ".png": "dataurl",
  },
  plugins: [
    vuePlugin(),
    // Stub Node-only modules that get pulled in by an unused branch in
    // @mlightcad/cad-simple-viewer (server-side fallback for filesystem ops).
    // We only run in the browser, so resolve them to an empty module.
    {
      name: "stub-node-builtins",
      setup(b) {
        const empty = "module.exports = {};";
        // Fake Stats.js: must be `new`-able with .dom (DOM node) and the
        // begin/end/update no-ops MLightCAD's perf-monitor calls every frame.
        const statsStub = `
          class Stats {
            constructor() {
              this.dom = (typeof document !== "undefined")
                ? document.createElement("div") : {};
              this.domElement = this.dom;
            }
            showPanel() {}
            begin() {}
            end() {}
            update() {}
            addPanel() {}
          }
          module.exports = Stats;
          module.exports.default = Stats;
        `;
        b.onResolve({ filter: /^(fs|path|os|crypto|stream|util)$/ }, (args) => ({
          path: args.path,
          namespace: "stub-node",
        }));
        b.onLoad({ filter: /^(fs|path|os|crypto|stream|util)$/, namespace: "stub-node" }, () => ({
          contents: empty,
          loader: "js",
        }));
        // three's old stats addon path was removed in 0.172+; map to a class stub.
        b.onResolve({ filter: /^three\/examples\/jsm\/libs\/stats\.module(\.js)?$/ }, () => ({
          path: "stats-stub",
          namespace: "stub-node",
        }));
        b.onLoad({ filter: /^stats-stub$/, namespace: "stub-node" }, () => ({
          contents: statsStub,
          loader: "js",
        }));
        // three@0.172 exports field requires explicit .js suffix on examples paths,
        // but cad-simple-viewer imports them without the suffix. Append it.
        b.onResolve({ filter: /^three\/examples\/jsm\/.+/ }, async (args) => {
          if (/\.(m?js|json)$/.test(args.path)) return null;
          const r = await b.resolve(args.path + ".js", {
            kind: args.kind,
            resolveDir: args.resolveDir,
            importer: args.importer,
          });
          return r.errors.length ? null : { path: r.path };
        });
      },
    },
  ],
  // Vue's runtime checks NODE_ENV; replace it so we don't ship dev warnings.
  define: {
    "process.env.NODE_ENV": '"production"',
    __VUE_OPTIONS_API__: "true",
    __VUE_PROD_DEVTOOLS__: "false",
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: "false",
  },
  logLevel: "info",
});
console.log(`[build-mlight] done in ${Date.now() - t0}ms → ${outdir}`);
