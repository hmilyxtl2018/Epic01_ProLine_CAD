"use client";

/**
 * TopologyGraphCard — knowledge-graph view of the SiteModel ontology.
 *
 * Lives inside the "原始文件解析" (RawView) sub-tab on
 * `web/src/app/sites/[runId]/page.tsx`. The point of this card is to
 * make the *relational* shape of the parse output visible — the part
 * of D3 (拓扑/关系) the 5×4×4 framework calls out — *without* needing
 * the LayoutAgent to land first.
 *
 * Data sources (fall through):
 *   1. `output_payload.links` — the canonical Pydantic SiteModel.links
 *      array shape `{source_guid, target_guid, link_type, metadata}`.
 *      ParseAgent v1.0 may not emit any (D3 is allowed to be N/A) but
 *      we render whatever IS there.
 *   2. `output_payload.site_model.links` — alternate persistence shape
 *      that some legacy runs use.
 *   3. Derived bipartite from `enrichment.D_cluster_proposals.proposals`
 *      ⊕ `C_arbiter.promotion_candidates`: nodes = asset_type centres
 *      + their child terms (cluster names / promoted candidates), edges
 *      = `containment` (asset_type → term). Always shown with a
 *      "派生" badge so reviewers know the edges are NOT real
 *      ParseAgent links.
 *
 * Layout: hand-rolled Fruchterman-Reingold (60 iterations) so we stay
 * dependency-free (no d3 / cytoscape). For < ~120 nodes this is well
 * under one frame and the result is visually decent.
 *
 * Why a custom impl rather than a library:
 * - The bundle already carries Three.js (via MLightCAD) + dxf-viewer in
 *   neighbouring routes; another graph lib is real weight for one card.
 * - The card has fixed semantics ("show me the ontology relations of
 *   one parsed run") — no need for cross-filter / minimap / live edit.
 * - Re-running 60 FR iterations on data swap is cheaper than the
 *   v8 cost of importing d3-force lazily.
 */

import { useMemo, useRef, useState } from "react";
import { Icon } from "@/components/icons";
import type { LLMEnrichment, RunDetail } from "@/lib/types";

// ─────────────────────────────────────────────────────────────────────
// Public types
// ─────────────────────────────────────────────────────────────────────

type GraphNode = {
  id: string;
  /** display label */
  label: string;
  /** semantic group, drives node color */
  group: string;
  /** size proxy (member_count / occurrences) */
  weight: number;
  /** layout-only position (mutated by FR sim, immutable after) */
  x: number;
  y: number;
};

type GraphEdge = {
  source: string;
  target: string;
  /** "APPLIES_TO" / "PAIR_WITH" / … or "containment" / "co-type" derived */
  kind: string;
};

type GraphData = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** "ontology" = real SiteModel.links; "derived" = synthesized from D/C */
  source: "ontology" | "derived" | "empty";
  /** human-readable note shown in the card footer */
  note: string;
};

// ─────────────────────────────────────────────────────────────────────
// Data extraction
// ─────────────────────────────────────────────────────────────────────

function extractOntologyLinks(run: RunDetail): GraphData | null {
  const op: any = run.output_payload || {};
  // Pydantic SiteModel serialises directly into output_payload.links / .assets,
  // but legacy runs nest under output_payload.site_model.
  const links: any[] = Array.isArray(op.links)
    ? op.links
    : Array.isArray(op.site_model?.links)
      ? op.site_model.links
      : Array.isArray(op.relationships?.links)
        ? op.relationships.links
        : [];
  if (!links.length) return null;

  const assets: any[] = Array.isArray(op.assets)
    ? op.assets
    : Array.isArray(op.site_model?.assets)
      ? op.site_model.assets
      : [];
  // Build a lookup from guid → (label, type) so edges can render with
  // human names instead of MDI-XXXX identifiers.
  const assetMap = new Map<string, { label: string; type: string }>();
  for (const a of assets) {
    if (!a?.asset_guid) continue;
    assetMap.set(a.asset_guid, {
      label: String(a.label || a.block_name || a.asset_guid).slice(0, 24),
      type: String(a.type || "Other"),
    });
  }

  const nodeIds = new Set<string>();
  for (const l of links) {
    if (l.source_guid) nodeIds.add(String(l.source_guid));
    if (l.target_guid) nodeIds.add(String(l.target_guid));
  }
  const nodes: GraphNode[] = [];
  for (const id of nodeIds) {
    const meta = assetMap.get(id);
    nodes.push({
      id,
      label: meta?.label || id.slice(0, 12),
      group: meta?.type || "Unknown",
      weight: 1,
      x: 0,
      y: 0,
    });
  }
  const edges: GraphEdge[] = links
    .filter((l) => l.source_guid && l.target_guid)
    .map((l) => ({
      source: String(l.source_guid),
      target: String(l.target_guid),
      kind: String(l.link_type || "RELATED"),
    }));

  return {
    nodes,
    edges,
    source: "ontology",
    note: `SiteModel.links · ${nodes.length} 节点 · ${edges.length} 边`,
  };
}

function deriveFromEnrichment(run: RunDetail): GraphData {
  const enrich: LLMEnrichment | null =
    ((run.output_payload as any)?.llm_enrichment as LLMEnrichment) || null;
  const proposals: any[] = enrich?.sections.D_cluster_proposals?.proposals || [];
  const promoted: any[] = enrich?.sections.C_arbiter?.promotion_candidates || [];

  if (!proposals.length && !promoted.length) {
    return {
      nodes: [],
      edges: [],
      source: "empty",
      note: "ParseAgent 未生成关系/拓扑数据",
    };
  }

  // Group asset_type centres
  const types = new Map<string, number>();
  for (const p of proposals) {
    const t = String(p.asset_type_hint || "Other");
    types.set(t, (types.get(t) || 0) + (p.member_count || 1));
  }
  for (const p of promoted) {
    const t = String(p.asset_type_hint || p.target_type || "Other");
    types.set(t, (types.get(t) || 0) + 1);
  }

  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];

  // Type-centre nodes (one per unique asset_type)
  for (const [t, w] of types) {
    nodes.push({
      id: `type:${t}`,
      label: t,
      group: "_type",
      weight: Math.max(2, Math.log10(w + 1) * 4),
      x: 0,
      y: 0,
    });
  }

  // Term/cluster leaves
  for (const p of proposals) {
    const id = `cluster:${p.cluster_id || p.suggested_term || Math.random().toString(36).slice(2)}`;
    const label = String(p.suggested_term || p.cluster_id || "?").slice(0, 22);
    const type = String(p.asset_type_hint || "Other");
    nodes.push({
      id,
      label,
      group: type,
      weight: Math.max(1, Math.log10((p.member_count || 1) + 1) * 2 + 1),
      x: 0,
      y: 0,
    });
    edges.push({ source: `type:${type}`, target: id, kind: "containment" });
  }
  for (const p of promoted) {
    const id = `term:${p.candidate || p.best_match || Math.random().toString(36).slice(2)}`;
    const label = String(p.candidate || p.best_match || "?").slice(0, 22);
    const type = String(p.asset_type_hint || p.target_type || "Other");
    if (nodes.some((n) => n.id === id)) continue; // dedup
    nodes.push({
      id,
      label,
      group: type,
      weight: 1.5,
      x: 0,
      y: 0,
    });
    edges.push({ source: `type:${type}`, target: id, kind: "promoted" });
  }

  return {
    nodes,
    edges,
    source: "derived",
    note: `派生自 D_cluster_proposals × C_arbiter · ${nodes.length} 节点 · ${edges.length} 边 · 边语义=containment`,
  };
}

function buildGraph(run: RunDetail): GraphData {
  return extractOntologyLinks(run) || deriveFromEnrichment(run);
}

// ─────────────────────────────────────────────────────────────────────
// Layout: simplified Fruchterman-Reingold (no d3 dep)
// ─────────────────────────────────────────────────────────────────────

const W = 800;
const H = 540;

function fruchtermanReingold(g: GraphData) {
  const nodes = g.nodes;
  const edges = g.edges;
  const n = nodes.length;
  if (n === 0) return;
  const area = W * H;
  const k = Math.sqrt(area / n);
  const idx = new Map(nodes.map((n, i) => [n.id, i] as const));

  // Seed positions deterministically (hash node id).
  for (let i = 0; i < n; i++) {
    const s = nodes[i].id;
    let h = 0;
    for (let j = 0; j < s.length; j++) h = (h * 31 + s.charCodeAt(j)) >>> 0;
    nodes[i].x = (h % 1000) / 1000 * W;
    nodes[i].y = (((h >>> 10) % 1000) / 1000) * H;
  }

  let temperature = Math.min(W, H) / 8;
  const iters = Math.min(80, 30 + Math.floor(120 / Math.max(1, n / 20)));
  const dx = new Float32Array(n);
  const dy = new Float32Array(n);

  for (let iter = 0; iter < iters; iter++) {
    dx.fill(0);
    dy.fill(0);

    // Repulsive: O(n²) is fine for n ≤ ~150 in our use-case.
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let ddx = nodes[i].x - nodes[j].x;
        let ddy = nodes[i].y - nodes[j].y;
        let d2 = ddx * ddx + ddy * ddy;
        if (d2 < 0.01) {
          ddx = (Math.random() - 0.5) * 0.1;
          ddy = (Math.random() - 0.5) * 0.1;
          d2 = ddx * ddx + ddy * ddy + 0.01;
        }
        const d = Math.sqrt(d2);
        const force = (k * k) / d;
        dx[i] += (ddx / d) * force;
        dy[i] += (ddy / d) * force;
        dx[j] -= (ddx / d) * force;
        dy[j] -= (ddy / d) * force;
      }
    }
    // Attractive on edges.
    for (const e of edges) {
      const i = idx.get(e.source);
      const j = idx.get(e.target);
      if (i == null || j == null) continue;
      const ddx = nodes[i].x - nodes[j].x;
      const ddy = nodes[i].y - nodes[j].y;
      const d = Math.max(0.1, Math.sqrt(ddx * ddx + ddy * ddy));
      const force = (d * d) / k;
      dx[i] -= (ddx / d) * force;
      dy[i] -= (ddy / d) * force;
      dx[j] += (ddx / d) * force;
      dy[j] += (ddy / d) * force;
    }

    // Limit by temperature, clamp to viewport.
    for (let i = 0; i < n; i++) {
      const d = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 1;
      nodes[i].x += (dx[i] / d) * Math.min(d, temperature);
      nodes[i].y += (dy[i] / d) * Math.min(d, temperature);
      nodes[i].x = Math.max(20, Math.min(W - 20, nodes[i].x));
      nodes[i].y = Math.max(20, Math.min(H - 20, nodes[i].y));
    }
    temperature *= 0.96; // cool down
  }
}

// ─────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────

export function TopologyGraphCard({ run }: { run: RunDetail }) {
  // Build & lay out the graph once per run (memoised). FR mutates the
  // GraphNode positions in-place which is fine because the array is
  // freshly constructed inside `buildGraph`.
  const graph = useMemo(() => {
    const g = buildGraph(run);
    fruchtermanReingold(g);
    return g;
  }, [run]);

  // Pan/zoom state.
  const [view, setView] = useState({ tx: 0, ty: 0, k: 1 });
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<{ sx: number; sy: number; stx: number; sty: number } | null>(null);
  const [hover, setHover] = useState<string | null>(null);

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const r = svgRef.current?.getBoundingClientRect();
    if (!r) return;
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    const f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const nk = Math.max(0.3, Math.min(4, view.k * f));
    setView({
      tx: mx - (mx - view.tx) * (nk / view.k),
      ty: my - (my - view.ty) * (nk / view.k),
      k: nk,
    });
  };
  const onDown = (e: React.MouseEvent) => {
    drag.current = { sx: e.clientX, sy: e.clientY, stx: view.tx, sty: view.ty };
  };
  const onMove = (e: React.MouseEvent) => {
    if (!drag.current) return;
    setView((v) => ({
      ...v,
      tx: drag.current!.stx + (e.clientX - drag.current!.sx),
      ty: drag.current!.sty + (e.clientY - drag.current!.sy),
    }));
  };
  const reset = () => setView({ tx: 0, ty: 0, k: 1 });

  // Map group → color (deterministic HSL, with Type centres in violet).
  const colorOf = (group: string): string => {
    if (group === "_type") return "#7c3aed"; // violet-600
    let h = 0;
    for (let i = 0; i < group.length; i++) h = (h * 31 + group.charCodeAt(i)) >>> 0;
    return `hsl(${h % 360}, 55%, 50%)`;
  };

  // Build a quick id→node map for edge endpoints.
  const byId = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph]);
  const groups = useMemo(() => {
    const s = new Set<string>();
    for (const n of graph.nodes) s.add(n.group);
    return [...s];
  }, [graph]);

  // Highlight the 1-hop neighbourhood when hovering.
  const neighbours = useMemo(() => {
    if (!hover) return null;
    const set = new Set<string>([hover]);
    for (const e of graph.edges) {
      if (e.source === hover) set.add(e.target);
      if (e.target === hover) set.add(e.source);
    }
    return set;
  }, [hover, graph.edges]);

  return (
    <div className="flex flex-col overflow-hidden rounded border border-zinc-200 bg-white">
      {/* Header. Marked `rgl-drag-handle` so when this card is hosted by
          DraggableCardGrid the header doubles as the drag affordance.
          Outside that grid the class is harmless (no styles attached). */}
      <header className="rgl-drag-handle flex cursor-grab select-none items-center gap-1.5 border-b border-zinc-100 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-700 active:cursor-grabbing">
        <Icon name="link" size={13} className="text-zinc-500" />
        <span>拓扑关系图谱</span>
        <span className="text-[10px] font-normal normal-case text-zinc-400">
          · {graph.nodes.length} 节点 · {graph.edges.length} 边
        </span>
        {graph.source === "derived" && (
          <span
            className="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-normal normal-case text-amber-700"
            title="ParseAgent v1.0 暂不输出 SiteModel.links；图谱由 cluster_proposals × arbiter 派生 · 边语义=containment"
          >
            派生
          </span>
        )}
        {graph.source === "ontology" && (
          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[9px] font-normal normal-case text-emerald-700">
            ontology
          </span>
        )}
        <div className="ml-auto flex items-center gap-1 text-[11px] font-normal normal-case text-zinc-500">
          <button
            onClick={() => setView((v) => ({ ...v, k: Math.min(4, v.k * 1.2) }))}
            className="rounded px-1.5 py-0.5 hover:bg-zinc-100"
            title="放大"
          >
            +
          </button>
          <span className="font-mono">{Math.round(view.k * 100)}%</span>
          <button
            onClick={() => setView((v) => ({ ...v, k: Math.max(0.3, v.k / 1.2) }))}
            className="rounded px-1.5 py-0.5 hover:bg-zinc-100"
            title="缩小"
          >
            −
          </button>
          <button onClick={reset} className="rounded px-1.5 py-0.5 hover:bg-zinc-100">
            重置
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="relative flex-1 overflow-hidden bg-[radial-gradient(ellipse_at_center,#f8fafc_0%,#f1f5f9_100%)]">
        {graph.source === "empty" ? (
          <div className="flex h-full items-center justify-center p-6">
            <div className="max-w-sm rounded border border-dashed border-zinc-300 p-5 text-center text-[12px] text-zinc-500">
              <Icon name="alert-circle" size={20} className="mx-auto mb-2 text-zinc-400" />
              {graph.note}
              <div className="mt-1 text-[11px] text-zinc-400">
                ParseAgent v1.0 默认不出关系；后续 ConstraintAgent 写入 links 后此处自动有图。
              </div>
            </div>
          </div>
        ) : (
          <svg
            ref={svgRef}
            className="h-full w-full cursor-grab active:cursor-grabbing"
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="xMidYMid meet"
            onWheel={onWheel}
            onMouseDown={onDown}
            onMouseMove={onMove}
            onMouseUp={() => (drag.current = null)}
            onMouseLeave={() => {
              drag.current = null;
              setHover(null);
            }}
          >
            <g transform={`translate(${view.tx}, ${view.ty}) scale(${view.k})`}>
              {/* Edges */}
              {graph.edges.map((e, i) => {
                const a = byId.get(e.source);
                const b = byId.get(e.target);
                if (!a || !b) return null;
                const dim = neighbours ? !(neighbours.has(e.source) && neighbours.has(e.target)) : false;
                return (
                  <line
                    key={i}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke={e.kind === "containment" ? "#a8a29e" : "#6366f1"}
                    strokeWidth={dim ? 0.6 : 1.2}
                    strokeOpacity={dim ? 0.2 : 0.7}
                    strokeDasharray={e.kind === "containment" ? "3 3" : undefined}
                  />
                );
              })}
              {/* Nodes */}
              {graph.nodes.map((n) => {
                const dim = neighbours ? !neighbours.has(n.id) : false;
                const r = 4 + n.weight;
                const isType = n.group === "_type";
                return (
                  <g
                    key={n.id}
                    transform={`translate(${n.x}, ${n.y})`}
                    onMouseEnter={() => setHover(n.id)}
                    style={{ cursor: "pointer", opacity: dim ? 0.25 : 1 }}
                  >
                    <circle
                      r={r}
                      fill={colorOf(n.group)}
                      fillOpacity={isType ? 0.85 : 0.7}
                      stroke="#ffffff"
                      strokeWidth={1.2}
                    />
                    <text
                      y={r + 9}
                      textAnchor="middle"
                      fontSize={isType ? 11 : 9}
                      fontWeight={isType ? 600 : 500}
                      fill="#27272a"
                      style={{ pointerEvents: "none", userSelect: "none" }}
                    >
                      {n.label}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
        )}

        {/* Legend (group → color) */}
        {graph.nodes.length > 0 && (
          <div className="pointer-events-none absolute bottom-2 right-2 max-w-[200px] rounded bg-white/95 px-2 py-1.5 text-[10px] shadow-sm">
            <div className="mb-1 font-semibold uppercase tracking-wide text-zinc-500">资产类型</div>
            <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
              {groups
                .filter((g) => g !== "_type")
                .slice(0, 12)
                .map((g) => (
                  <div key={g} className="flex items-center gap-1.5 truncate">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ background: colorOf(g) }}
                    />
                    <span className="truncate text-zinc-700">{g}</span>
                  </div>
                ))}
              <div className="col-span-2 mt-0.5 flex items-center gap-1.5 border-t border-zinc-100 pt-0.5">
                <span className="inline-block h-2 w-2 rounded-full bg-violet-600" />
                <span className="text-zinc-700">类型中心节点</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center gap-2 border-t border-zinc-100 px-3 py-1.5 text-[11px] text-zinc-500">
        <Icon
          name="circle-dot"
          size={11}
          className={
            graph.source === "ontology"
              ? "text-emerald-500"
              : graph.source === "derived"
                ? "text-amber-500"
                : "text-zinc-400"
          }
        />
        <span className="truncate">{graph.note}</span>
        <span className="ml-auto italic text-zinc-400">滚轮缩放 · 拖拽平移 · 悬停高亮邻接</span>
      </div>
    </div>
  );
}
