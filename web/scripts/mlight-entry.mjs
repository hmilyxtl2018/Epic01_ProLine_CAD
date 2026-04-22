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

// Expose on window for the iframe HTML to call.
if (typeof window !== "undefined") {
  window.__mlight = { mount };
}

export { mount };
