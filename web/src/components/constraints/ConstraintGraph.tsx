"use client";

/**
 * Layered DAG of `predecessor` constraints — industrial-grade.
 *
 * Stack:
 *   - @xyflow/react   : interactive graph surface (pan / zoom / minimap / a11y)
 *   - @dagrejs/dagre  : Sugiyama framework layered layout
 *       · rank assignment       — network-simplex (optimal w.r.t. Σ edge length)
 *       · crossing minimization — weighted median heuristic, multi-pass
 *       · x-coordinate assignment — Brandes-Köpf (balanced vertical alignment)
 *
 * Why this combination over hand-rolled SVG:
 *   - Network-simplex ranking minimises Σ |layer(v) − layer(u)| over all edges,
 *     producing tighter, more readable diagrams than longest-path / Kahn.
 *   - Brandes-Köpf coordinate assignment is the same algorithm used by
 *     Graphviz `dot` and yFiles hierarchic layouts; vertices end up vertically
 *     centred between predecessors and successors with O(V·E) cost.
 *   - Crossing minimisation is NP-hard in general; dagre's median heuristic
 *     is the same pragmatic choice production tools make.
 *
 * Cycle handling:
 *   Dagre breaks cycles internally (`acyclicer: greedy`) so layout always
 *   succeeds. The validator's `code === "cycle"` issues drive red node /
 *   edge highlighting so the topological violation stays visible.
 */

import { useMemo, useCallback } from "react";
import dagre from "@dagrejs/dagre";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  Position,
  Handle,
  type Node,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { ConstraintItem, ValidationIssue } from "@/lib/types";

interface Props {
  items: ConstraintItem[];
  validation: ValidationIssue[];
  selectedAsset: string | null;
  onSelectAsset: (asset: string | null) => void;
}

interface AssetNodeData {
  label: string;
  inCycle: boolean;
  selected: boolean;
  [key: string]: unknown;
}

// ── Custom node ───────────────────────────────────────────────────────
//
// Kept tiny on purpose: Tailwind palette only, no shadows. The visual
// language matches the surrounding S2 panel.
function AssetNode({ data }: NodeProps<Node<AssetNodeData>>) {
  const { label, inCycle, selected } = data;
  const cls = inCycle
    ? "border-rose-500 bg-rose-50 text-rose-900"
    : selected
      ? "border-violet-500 bg-violet-50 text-violet-900"
      : "border-zinc-300 bg-white text-zinc-800 hover:border-zinc-400";
  return (
    <div
      className={`rounded-md border px-2.5 py-1 font-mono text-[11px] leading-tight transition-colors ${cls}`}
      style={{ minWidth: 110, textAlign: "center" }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: "transparent", border: "none", width: 1, height: 1 }}
      />
      {label}
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: "transparent", border: "none", width: 1, height: 1 }}
      />
    </div>
  );
}

const NODE_TYPES = { asset: AssetNode };

// ── Layout ────────────────────────────────────────────────────────────

const NODE_WIDTH = 130;
const NODE_HEIGHT = 32;

function buildLayout(
  items: ConstraintItem[],
  cycleAssets: Set<string>,
  selectedAsset: string | null,
): { nodes: Node<AssetNodeData>[]; edges: Edge[] } {
  // 1. Collect predecessor edges (active only) and the asset universe.
  const assets = new Set<string>();
  const rawEdges: { from: string; to: string; cid: string; lag?: number }[] = [];
  for (const i of items) {
    if (i.kind !== "predecessor" || !i.is_active) continue;
    const p = i.payload as {
      kind: "predecessor"; from: string; to: string; lag_s?: number;
    };
    if (!p.from || !p.to) continue;
    assets.add(p.from);
    assets.add(p.to);
    rawEdges.push({ from: p.from, to: p.to, cid: i.constraint_id, lag: p.lag_s });
  }

  if (assets.size === 0) return { nodes: [], edges: [] };

  // 2. Run dagre — Sugiyama layered layout.
  //
  //    rankdir LR        — flow left → right (matches process semantics)
  //    ranker n-simplex  — minimises total edge length (vs longest-path)
  //    acyclicer greedy  — break cycles for layout; we still mark them red
  //    nodesep           — horizontal gap between nodes in the same rank
  //    ranksep           — gap between ranks
  const g = new dagre.graphlib.Graph({ directed: true, multigraph: false });
  g.setGraph({
    rankdir: "LR",
    ranker: "network-simplex",
    acyclicer: "greedy",
    nodesep: 18,
    ranksep: 60,
    marginx: 8,
    marginy: 8,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const a of assets) {
    g.setNode(a, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const e of rawEdges) {
    g.setEdge(e.from, e.to, { weight: 1, minlen: 1 });
  }
  dagre.layout(g);

  // 3. Translate to ReactFlow nodes / edges.
  const nodes: Node<AssetNodeData>[] = [];
  for (const a of assets) {
    const n = g.node(a);
    if (!n) continue;
    nodes.push({
      id: a,
      type: "asset",
      // dagre returns centre coordinates; ReactFlow expects top-left.
      position: { x: n.x - NODE_WIDTH / 2, y: n.y - NODE_HEIGHT / 2 },
      data: {
        label: a.length > 16 ? `${a.slice(0, 15)}…` : a,
        inCycle: cycleAssets.has(a),
        selected: a === selectedAsset,
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      draggable: false,
      connectable: false,
    });
  }

  const edges: Edge[] = rawEdges.map((e, idx) => {
    const inCycle = cycleAssets.has(e.from) && cycleAssets.has(e.to);
    return {
      id: `${e.cid}-${idx}`,
      source: e.from,
      target: e.to,
      type: "smoothstep",
      animated: false,
      label: e.lag ? `+${e.lag}s` : undefined,
      labelStyle: { fontSize: 10, fill: "#71717a" },
      labelBgStyle: { fill: "#ffffff", fillOpacity: 0.9 },
      labelBgPadding: [2, 2],
      style: {
        stroke: inCycle ? "#e11d48" : "#a1a1aa",
        strokeWidth: inCycle ? 1.6 : 1.1,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: inCycle ? "#e11d48" : "#a1a1aa",
        width: 14,
        height: 14,
      },
    };
  });

  return { nodes, edges };
}

// ── Component ─────────────────────────────────────────────────────────

function ConstraintGraphInner({
  items, validation, selectedAsset, onSelectAsset,
}: Props) {
  const cycleAssets = useMemo(() => {
    const s = new Set<string>();
    for (const v of validation) {
      if (v.code === "cycle") for (const a of v.asset_ids) s.add(a);
    }
    return s;
  }, [validation]);

  const { nodes, edges } = useMemo(
    () => buildLayout(items, cycleAssets, selectedAsset),
    [items, cycleAssets, selectedAsset],
  );

  const handleNodeClick = useCallback(
    (_evt: unknown, node: Node) => {
      onSelectAsset(node.id === selectedAsset ? null : node.id);
    },
    [onSelectAsset, selectedAsset],
  );

  const handlePaneClick = useCallback(() => onSelectAsset(null), [onSelectAsset]);

  if (nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-[12px] text-zinc-400">
        暂无 predecessor 约束 · 添加先后约束后此处显示工艺流程图
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={NODE_TYPES}
      onNodeClick={handleNodeClick}
      onPaneClick={handlePaneClick}
      fitView
      fitViewOptions={{ padding: 0.15 }}
      minZoom={0.3}
      maxZoom={2}
      proOptions={{ hideAttribution: true }}
      nodesDraggable={false}
      nodesConnectable={false}
      edgesFocusable={false}
      panOnScroll
      selectionOnDrag={false}
    >
      <Background gap={16} size={1} color="#e4e4e7" />
      <MiniMap
        pannable
        zoomable
        nodeColor={(n) => {
          const d = n.data as AssetNodeData | undefined;
          if (d?.inCycle) return "#fecdd3";
          if (d?.selected) return "#ddd6fe";
          return "#e4e4e7";
        }}
        maskColor="rgba(244,244,245,0.6)"
        style={{ background: "#fafafa" }}
      />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}

export function ConstraintGraph(props: Props) {
  // ReactFlow needs an explicit-size container; the parent gives 260px.
  return (
    <div className="h-full w-full bg-zinc-50">
      <ReactFlowProvider>
        <ConstraintGraphInner {...props} />
      </ReactFlowProvider>
    </div>
  );
}
