// Entry that the iframe page calls into. Re-exports just what we need so the
// iframe HTML stays tiny: vue's createApp + h + ref, MlCadViewer + i18n, and
// ElementPlus default export. esbuild then bundles vue + element-plus +
// @mlightcad/* + their CSS into a single self-contained chunk.
import { createApp, h, ref } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import { MlCadViewer, i18n } from "@mlightcad/cad-viewer";
import { AcApDocManager, eventBus } from "@mlightcad/cad-simple-viewer";

// Suppress the "字体找不到" notification: DWG files exported from old AutoCAD
// often embed GBK-encoded font names (`仿宋_gb2312`, `黑体`, etc) that
// libredwg can't transcode and that aren't in MLightCAD's font CDN anyway.
// The geometry renders fine — only text glyphs fall back to filled boxes —
// so the toast is pure noise for our preview use case. We intercept the
// underlying eventBus events; the notification center subscribes via
// addEventListener so removing them after our handler still leaves the
// notification system disconnected from these particular events.
try {
  // mitt's `.off(type)` (no handler) removes ALL listeners for that event.
  // Call it once after a tick so MlCadViewer's NotificationCenter has had
  // time to register first; we then unwire just these two noisy events.
  setTimeout(() => {
    try { eventBus.off?.("fonts-not-found"); } catch {}
    try { eventBus.off?.("fonts-not-loaded"); } catch {}
    try { eventBus.off?.("font-not-found"); } catch {}
  }, 0);
} catch {}

// Suppress a known class of MLightCAD `console.warn` noise that triggers on
// almost every DWG-converted DXF in our corpus. The library logs (via
// loglevel → console.warn) when an individual hatch's boundaries can't be
// triangulated — typically because the source DWG had self-intersecting or
// degenerate hatch loops. The drawing itself still renders fine; only the
// fill of that one hatch is dropped, which we accept for a preview.
//
// Without this, every preview prints dozens of:
//   "Failed to convert hatch boundaries!"
//   "Polybool error: ..., epsilon is 1e-6"
//   "Triangulate shape error: ..."
//   "mergedHoles.regions is empty!"
// to the host page's console, which makes the dashboard look broken to
// reviewers. We keep all *other* warns (font issues, render errors, etc.)
// flowing through untouched.
//
// ⚠️  TIMING CAVEAT ⚠️ — When this entry runs, the `loglevel` library has
// ALREADY been imported at the top of this file (via @mlightcad/*), and
// loglevel's `methodFactory` cached `console.warn.bind(console)` on every
// logger instance at that import time. So patching `console.warn` here is
// TOO LATE for any logger that was created during module init — those
// loggers hold the original reference and skip our wrapper. That bug
// produced thousands of `Failed to convert hatch boundaries!` lines
// streaming into the dashboard console.
//
// The REAL fix — and the one that actually silences the noise — lives in
// `public/mlight-viewer.html`, where the same patch runs in a synchronous
// IIFE BEFORE `await import("/mlight/bundle.js")`. That guarantees every
// loglevel logger created during bundle init sees our wrapper.
//
// We keep this block as defense-in-depth for two scenarios:
//   1. Loggers created LAZILY at first warn-time (post-init) — those will
//      pick up our wrapper here.
//   2. Embedders that load `bundle.js` from a host page that DOESN'T do
//      the early patch (e.g. ad-hoc devtools experiments, tests).
try {
  const NOISE = [
    "Failed to convert hatch boundaries",
    "Polybool error",
    "Triangulate shape error",
    "mergedHoles.regions is empty",
  ];
  const isNoise = (args) => {
    for (const a of args) {
      if (typeof a === "string") {
        for (const n of NOISE) if (a.includes(n)) return true;
      }
    }
    return false;
  };
  const origWarn = console.warn.bind(console);
  const origError = console.error.bind(console);
  // Counter exposed for debugging — `window.__mlight.suppressedHatchWarns`.
  // The early patch in mlight-viewer.html seeds this with {warn, error}; we
  // merge so neither side clobbers the other.
  const existing =
    (typeof window !== "undefined" && window.__mlight?.suppressedHatchWarns) ||
    null;
  const counter = existing && typeof existing === "object"
    ? existing
    : { count: 0, warn: 0, error: 0 };
  console.warn = (...args) => {
    if (isNoise(args)) {
      counter.count = (counter.count || 0) + 1;
      counter.warn = (counter.warn || 0) + 1;
      return;
    }
    origWarn(...args);
  };
  console.error = (...args) => {
    if (isNoise(args)) {
      counter.count = (counter.count || 0) + 1;
      counter.error = (counter.error || 0) + 1;
      return;
    }
    origError(...args);
  };
  if (typeof window !== "undefined") {
    window.__mlight = window.__mlight || {};
    window.__mlight.suppressedHatchWarns = counter;
  }
} catch {}


// MLightCAD spawns three Web Workers (DXF parser, DWG parser via libredwg,
// MText renderer). Defaults look like "./assets/<name>.js" relative to the
// host page (/mlight-viewer.html → /assets/<name>.js → 404). We bundle the
// worker files into /mlight/workers/ in build-mlight.mjs and override the
// URLs here. MlCadViewer calls AcApDocManager.createInstance(opts) on mount
// but only forwards {container, baseUrl, autoResize, useMainThreadDraw} —
// it never sets webworkerFileUrls. We patch the static factory to merge our
// URLs into every call.
const WORKER_URLS = {
  dxfParser: "/mlight/workers/dxf-parser-worker.js",
  dwgParser: "/mlight/workers/libredwg-parser-worker.js",
  mtextRender: "/mlight/workers/mtext-renderer-worker.js",
};
const _origCreate = AcApDocManager.createInstance.bind(AcApDocManager);
AcApDocManager.createInstance = (opts = {}) =>
  _origCreate({
    ...opts,
    webworkerFileUrls: { ...WORKER_URLS, ...(opts.webworkerFileUrls || {}) },
  });

// Mount helper so the iframe just calls window.__mlight.mount(host, file).
function mount(host, file, opts = {}) {
  const fileRef = ref(file);
  const app = createApp({
    setup() {
      return () =>
        h(MlCadViewer, {
          background: opts.background ?? 0xffffff,
          localFile: fileRef.value,
          locale: opts.locale ?? "zh",
        });
    },
  });
  if (i18n) app.use(i18n);
  app.use(ElementPlus);
  app.mount(host);

  // Auto zoom-to-extents after the document finishes opening. The library
  // claims openDocument() does this, but on DWG-converted DXFs with bad
  // hatch boundaries the initial extents come out skewed and the drawing
  // ends up off-screen. We re-fit on documentActivated as a safety net.
  try {
    const mgr = AcApDocManager.instance;
    const refit = () => {
      // Wait one tick so the renderer has actually appended the entities,
      // then call zoomToFitDrawing with a generous timeout (some entities
      // are still being batchConvert-ed when documentActivated fires).
      setTimeout(() => {
        try { mgr.curView?.zoomToFitDrawing?.(2000); } catch (e) {
          console.warn("[mlight] zoomToFitDrawing failed:", e);
        }
      }, 600);
    };
    mgr.events?.documentActivated?.addEventListener?.(refit);
  } catch (e) {
    console.warn("[mlight] auto-fit hook failed:", e);
  }

  return {
    setFile(f) {
      fileRef.value = f;
    },
    unmount() {
      app.unmount();
    },
  };
}

// Expose on window for the iframe HTML to call. Merge into any existing
// __mlight (the noise-filter block above seeds suppressedHatchWarns there
// before the module finishes evaluating, and we don't want to clobber it).
if (typeof window !== "undefined") {
  window.__mlight = Object.assign(window.__mlight || {}, { mount });
}


export { mount };
