"use client";

/**
 * DraggableCardGrid — small wrapper around `react-grid-layout` so callers
 * (currently the RawView 3-card layout in
 * `web/src/app/sites/[runId]/page.tsx`) can ship a "users can rearrange
 * + resize their cards" UX without re-implementing drag/resize math or
 * persistence by hand.
 *
 * Why react-grid-layout (and not rolling our own):
 * - Mature, battle-tested across dashboard products (Grafana,
 *   react-admin, etc.). Drag, resize, breakpoint-aware layouts and
 *   z-index conflict resolution are all already correct.
 * - SSR + Next.js compatibility: we gate render behind `mounted` so the
 *   first paint is pre-React (server) and React only takes over after
 *   `WidthProvider` has measured the actual container, avoiding the
 *   "fallback width 1280" hydration mismatch.
 * - Persistence: `localStorage` via `storageKey`, scoped per surface so
 *   each page can have its own remembered layout without collisions.
 *
 * Design choices specific to ProLine:
 * - `draggableHandle=".rgl-drag-handle"` → only the card *header* drags,
 *   so users can still highlight text inside the card body without the
 *   whole card flying away.
 * - `compactType="vertical"` + `preventCollision=false` matches Grafana
 *   "auto-pack upward" behaviour, which is the least-surprising default
 *   for analyst dashboards.
 * - `resizeHandles=["se"]` (bottom-right only) — enough surface area
 *   without spawning 8 grabby hot-zones on every card.
 * - Reset button → trash localStorage and re-seed defaultLayouts. Lives
 *   in the toolbar, *not* in the card itself, so users can recover from
 *   an accidentally-collapsed-to-zero card.
 */

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Responsive, WidthProvider, type Layouts, type Layout } from "react-grid-layout";
import { Icon } from "@/components/icons";

import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

const ResponsiveReactGridLayout = WidthProvider(Responsive);

// Standard react-grid-layout breakpoints — kept identical to the lib's
// docs example so any future contributor can google freely.
const BREAKPOINTS = { lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 } as const;
const COLS = { lg: 12, md: 12, sm: 8, xs: 4, xxs: 2 } as const;

export type DraggableItem = {
  /** Stable key that survives re-renders. Used as `Layout.i` and React key. */
  id: string;
  /** Default placement on the *lg* breakpoint. The lib derives smaller
   *  breakpoints automatically by clamping. Override per-bp in
   *  `defaultLayouts` if you need bespoke mobile geometry. */
  defaultLayout: { x: number; y: number; w: number; h: number; minW?: number; minH?: number };
  /** Card body. Should NOT itself be draggable; the `<DraggableCard>`
   *  wrapper renders the drag handle in its header. */
  render: () => ReactNode;
  /** Header label — also the visible drag handle. */
  title: string;
  /** Optional icon name from the shared icon set. */
  icon?: string;
  /** Optional right-aligned slot (e.g. mode pill, secondary actions). */
  headerExtra?: ReactNode;
  /**
   * When true, the grid does NOT wrap `render()` in `<DraggableCard>`
   * chrome. The caller is fully responsible for outer
   * border/header/scroll, and *must* place an element with class
   * `rgl-drag-handle` inside the rendered subtree (typically the
   * card header) — otherwise the cell becomes un-draggable.
   *
   * Use this when the child already has its own chrome (e.g.
   * `<TopologyGraphCard>` carries header + footer + tooltips that we
   * don't want duplicated by `<DraggableCard>`).
   */
  bare?: boolean;
};

export type DraggableCardGridHandle = {
  reset: () => void;
};

type Props = {
  storageKey: string;
  items: DraggableItem[];
  /** Pixel height of one row. 36 ≈ matches existing 4 grid-row cadence. */
  rowHeight?: number;
  /** Show the floating "重置布局" + "锁定" toolbar at top-right. */
  toolbar?: boolean;
};

/**
 * Build initial Layouts dict from item defaults. We intentionally copy
 * the `lg` layout to every smaller breakpoint and let RGL clamp `x+w`
 * into the smaller column count. This is good enough for our 3-card
 * use-case and avoids forcing every caller to spell out 5 layouts.
 */
function deriveDefaultLayouts(items: DraggableItem[]): Layouts {
  const lg: Layout[] = items.map((it) => ({ i: it.id, ...it.defaultLayout }));
  const out: Layouts = { lg };
  for (const bp of ["md", "sm", "xs", "xxs"] as const) {
    const cols = COLS[bp];
    out[bp] = lg.map((l) => ({
      ...l,
      x: Math.min(l.x, Math.max(0, cols - 1)),
      w: Math.min(l.w, cols),
    }));
  }
  return out;
}

export const DraggableCardGrid = forwardRef<DraggableCardGridHandle, Props>(function DraggableCardGrid(
  { storageKey, items, rowHeight = 36, toolbar = true },
  ref,
) {
  // SSR-safe mount gate. RGL's WidthProvider measures the container on
  // mount; rendering before that produces a flash + hydration mismatch.
  const [mounted, setMounted] = useState(false);
  const [locked, setLocked] = useState(false);

  const defaults = useMemo(() => deriveDefaultLayouts(items), [items]);
  const [layouts, setLayouts] = useState<Layouts>(defaults);

  // Hydrate from localStorage *after* mount so SSR and CSR markup match.
  useEffect(() => {
    setMounted(true);
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object") {
          // Sanity: the persisted layout must still know about every
          // current item id; if a card was removed/renamed since the
          // user last edited, fall back to defaults to avoid orphan
          // layouts that RGL silently drops.
          const ids = new Set(items.map((i) => i.id));
          const ok = ["lg", "md", "sm", "xs", "xxs"].every((bp) =>
            Array.isArray(parsed[bp]) ? parsed[bp].every((l: Layout) => ids.has(l.i)) : true,
          );
          if (ok) setLayouts(parsed as Layouts);
        }
      }
    } catch {
      /* ignore: fall back to defaults */
    }
    // We deliberately leave `items` out of deps — re-running this on
    // every render would clobber the user's in-flight drag with the
    // persisted snapshot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  const handleChange = useCallback(
    (_cur: Layout[], all: Layouts) => {
      setLayouts(all);
      try {
        localStorage.setItem(storageKey, JSON.stringify(all));
      } catch {
        /* quota exceeded etc. — silently no-op */
      }
    },
    [storageKey],
  );

  const reset = useCallback(() => {
    try {
      localStorage.removeItem(storageKey);
    } catch {
      /* no-op */
    }
    setLayouts(deriveDefaultLayouts(items));
  }, [items, storageKey]);

  useImperativeHandle(ref, () => ({ reset }), [reset]);

  // Keep a ref to the current items so the rendered children always
  // reflect the latest props (item.render closure capture).
  const itemsRef = useRef(items);
  itemsRef.current = items;

  return (
    <div className="relative h-full w-full overflow-y-auto">
      {toolbar && (
        <div className="pointer-events-none sticky top-0 z-10 mb-1 flex justify-end gap-1 px-1 pt-1 text-[11px]">
          <button
            onClick={() => setLocked((v) => !v)}
            className="pointer-events-auto inline-flex items-center gap-1 rounded border border-zinc-200 bg-white/95 px-2 py-1 text-zinc-600 shadow-sm hover:bg-zinc-50"
            title={locked ? "解锁后可拖拽与缩放卡片" : "锁定后禁止拖拽与缩放（避免误操作）"}
          >
            <Icon name={locked ? "shield-check" : "shield-alert"} size={12} />
            {locked ? "已锁定" : "可编辑"}
          </button>
          <button
            onClick={reset}
            className="pointer-events-auto inline-flex items-center gap-1 rounded border border-zinc-200 bg-white/95 px-2 py-1 text-zinc-600 shadow-sm hover:bg-zinc-50"
            title="清空 localStorage 中此页面的布局缓存，恢复到默认 2×2 布局"
          >
            <Icon name="history" size={12} />
            重置布局
          </button>
        </div>
      )}

      {mounted ? (
        <ResponsiveReactGridLayout
          className="layout"
          layouts={layouts}
          breakpoints={BREAKPOINTS}
          cols={COLS}
          rowHeight={rowHeight}
          margin={[8, 8]}
          containerPadding={[4, 4]}
          isDraggable={!locked}
          isResizable={!locked}
          draggableHandle=".rgl-drag-handle"
          resizeHandles={["se"]}
          compactType="vertical"
          preventCollision={false}
          onLayoutChange={handleChange}
          // Animations on drag are nice but resize gets jittery on
          // large card content (e.g. the SVG topology graph) so we
          // disable transitions while dragging.
          useCSSTransforms
        >
          {items.map((it) => (
            <div
              key={it.id}
              // Each cell must contain a `.rgl-drag-handle` element
              // somewhere in its subtree, otherwise it cannot be moved.
              // For non-bare items, `<DraggableCard>` provides one in
              // its header. For bare items, the caller is on the hook.
              className="overflow-hidden"
            >
              {it.bare ? (
                it.render()
              ) : (
                <DraggableCard
                  title={it.title}
                  icon={it.icon}
                  headerExtra={it.headerExtra}
                  locked={locked}
                >
                  {it.render()}
                </DraggableCard>
              )}
            </div>
          ))}
        </ResponsiveReactGridLayout>
      ) : (
        // Pre-mount placeholder: keep the surface area so the page
        // doesn't reflow once RGL takes over.
        <div className="grid h-full w-full place-items-center text-[11px] text-zinc-400">
          加载布局中…
        </div>
      )}
    </div>
  );
});

// ─────────────────────────────────────────────────────────────────────
// DraggableCard — chrome around each grid cell. Header doubles as the
// drag handle (matches `draggableHandle=".rgl-drag-handle"` above).
// ─────────────────────────────────────────────────────────────────────

function DraggableCard({
  title,
  icon,
  headerExtra,
  locked,
  children,
}: {
  title: string;
  icon?: string;
  headerExtra?: ReactNode;
  locked: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex h-full w-full flex-col overflow-hidden rounded border border-zinc-200 bg-white shadow-sm">
      <header
        className={[
          "rgl-drag-handle flex items-center gap-1.5 border-b border-zinc-100 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-700 select-none",
          locked ? "cursor-default" : "cursor-grab active:cursor-grabbing",
        ].join(" ")}
        title={locked ? title : `${title} · 按住拖拽 / 右下角缩放`}
      >
        {icon && <Icon name={icon as any} size={13} className="text-zinc-500" />}
        <span>{title}</span>
        <div className="ml-auto flex items-center gap-2">{headerExtra}</div>
        {!locked && (
          <span className="ml-1 text-zinc-300" aria-hidden>
            ⋮⋮
          </span>
        )}
      </header>
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </div>
  );
}
