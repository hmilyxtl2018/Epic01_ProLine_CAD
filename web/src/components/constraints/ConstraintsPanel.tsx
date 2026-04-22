"use client";

/**
 * S2 工艺约束面板 (P2.3a)
 * ─────────────────────────
 * 三栏布局，与 S1 视觉一致：
 *   - 左：约束类型筛选 + 数量 + (后续) 新建按钮
 *   - 中：约束列表表格 + 顶部 ValidationBanner
 *   - 右：选中项 JSON 详情 + (后续) 编辑/删除
 *
 * P2.3a 范围：只读列表 + validator 错误条。写操作 (a/b/c 路线) 见后续 step。
 */

import { useMemo, useState } from "react";
import { ConstraintForm } from "./ConstraintForm";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ConstraintItem, ConstraintKind, ValidationIssue } from "@/lib/types";
import { Icon } from "@/components/icons";
import { ConstraintGraph } from "./ConstraintGraph";

// Static class mapping — Tailwind JIT cannot detect dynamically built
// `bg-${color}-50` strings, so we keep both color classes precomputed.
const KIND_META: Record<
  ConstraintKind,
  { label: string; icon: string; chipClass: string }
> = {
  predecessor: { label: "先后", icon: "→", chipClass: "bg-violet-50 text-violet-700" },
  resource:    { label: "资源", icon: "◆", chipClass: "bg-amber-50 text-amber-700" },
  takt:        { label: "节拍", icon: "⌛", chipClass: "bg-sky-50 text-sky-700" },
  exclusion:   { label: "互斥", icon: "✕", chipClass: "bg-rose-50 text-rose-700" },
};

interface Props {
  siteModelId: string;
}


  const [kindFilter, setKindFilter] = useState<ConstraintKind | "all">("all");
  const [activeOnly, setActiveOnly] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState<ConstraintKind | null>(null);

  const listQ = useQuery({
    queryKey: ["constraints", siteModelId, activeOnly],
    queryFn: () => api.listConstraints(siteModelId, { activeOnly, pageSize: 200 }),
    enabled: !!siteModelId,
  });

  const validateQ = useQuery({
    queryKey: ["constraints-validate", siteModelId],
    queryFn: () => api.validateConstraints(siteModelId),
    enabled: !!siteModelId,
  });

  const items = listQ.data?.items ?? [];
  // 自动聚合所有资产名
  const allAssets = useMemo(() => {
    const s = new Set<string>();
    for (const i of items) {
      if (i.kind === "predecessor") {
        s.add(i.payload.from); s.add(i.payload.to);
      } else if (i.kind === "resource") {
        for (const a of i.payload.asset_ids) s.add(a);
      } else if (i.kind === "takt") {
        s.add(i.payload.asset_id);
      } else if (i.kind === "exclusion") {
        for (const a of i.payload.asset_ids) s.add(a);
      }
    }
    return Array.from(s).sort();
  }, [items]);
  const filtered = useMemo(
    () => (kindFilter === "all" ? items : items.filter((i) => i.kind === kindFilter)),
    [items, kindFilter],
  );

  const counts = useMemo(() => {
    const out: Record<ConstraintKind | "all", number> = {
      all: items.length, predecessor: 0, resource: 0, takt: 0, exclusion: 0,
    };
    for (const i of items) out[i.kind]++;
    return out;
  }, [items]);

  const selected = filtered.find((i) => i.constraint_id === selectedId) ?? null;

  // Asset id derived from current selection — drives DAG node highlight.
  const selectedAsset = useMemo<string | null>(() => {
    if (!selected) return null;
    const p = selected.payload;
    if (p.kind === "predecessor") return p.from;
    if (p.kind === "takt") return p.asset_id;
    return null;
  }, [selected]);

  // Clicking a graph node selects the first predecessor edge it appears in.
  const handleSelectAsset = (asset: string | null) => {
    if (!asset) { setSelectedId(null); return; }
    const hit = items.find(
      (i) => i.kind === "predecessor" && i.is_active &&
        ((i.payload as { kind: "predecessor"; from: string; to: string }).from === asset ||
         (i.payload as { kind: "predecessor"; from: string; to: string }).to === asset),
    );
    if (hit) setSelectedId(hit.constraint_id);
  };

  // 新建约束 mutation
  const qc = useQueryClient();
  const createMut = useMutation({
    mutationFn: (data: any) => api.createConstraint(siteModelId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["constraints", siteModelId] });
      qc.invalidateQueries({ queryKey: ["constraints-validate", siteModelId] });
      setShowCreate(null);
    },
  });

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[220px_1fr_360px] gap-3 overflow-hidden p-3">
      <LeftFilter
        counts={counts}
        kindFilter={kindFilter}
        onKindChange={setKindFilter}
        activeOnly={activeOnly}
        onActiveOnlyChange={setActiveOnly}
        onCreate={setShowCreate}
      />
      <Center
        items={filtered}
        allItems={items}
        selectedId={selectedId}
        onSelect={setSelectedId}
        loading={listQ.isLoading}
        error={listQ.error}
        validation={validateQ.data?.issues ?? []}
        validationLoading={validateQ.isLoading}
        selectedAsset={selectedAsset}
        onSelectAsset={handleSelectAsset}
      />
      <RightDetail item={selected} />

      {/* 新建约束弹窗 */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20">
          <div className="rounded bg-white p-4 shadow-xl min-w-[340px] max-w-[96vw]">
            <div className="mb-2 font-bold text-[15px]">新建约束 · {KIND_META[showCreate].label}</div>
            <ConstraintForm
              kind={showCreate}
              assets={allAssets}
              onSubmit={(data) => createMut.mutate({
                constraint_id: `cst_${Date.now()}`,
                payload: { ...data, kind: showCreate },
                priority: data.priority ?? 1,
                is_active: data.is_active ?? true,
              })}
              onCancel={() => setShowCreate(null)}
            />
            {createMut.isPending && <div className="text-xs text-zinc-400 mt-2">提交中…</div>}
            {createMut.error && <div className="text-xs text-rose-500 mt-2">{String(createMut.error)}</div>}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Left filter ───────────────────────────────────────────────────────

function LeftFilter({
  counts, kindFilter, onKindChange, activeOnly, onActiveOnlyChange, onCreate,
}: {
  counts: Record<ConstraintKind | "all", number>;
  kindFilter: ConstraintKind | "all";
  onKindChange: (k: ConstraintKind | "all") => void;
  activeOnly: boolean;
  onActiveOnlyChange: (v: boolean) => void;
  onCreate: (k: ConstraintKind) => void;
}) {
  const KINDS: (ConstraintKind | "all")[] = ["all", "predecessor", "resource", "takt", "exclusion"];
  return (
    <aside className="flex flex-col gap-2 overflow-hidden rounded-md border border-zinc-200 bg-white p-2 text-[12px]">
      <div className="px-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
        约束类型
      </div>
      <ul className="flex flex-col">
        {KINDS.map((k) => {
          const active = k === kindFilter;
          const label = k === "all" ? "全部" : KIND_META[k].label;
          const icon = k === "all" ? "≡" : KIND_META[k].icon;
          return (
            <li key={k}>
              <button
                type="button"
                onClick={() => onKindChange(k)}
                className={[
                  "flex w-full items-center justify-between rounded px-2 py-1.5 text-left transition",
                  active ? "bg-violet-50 font-medium text-violet-700" : "hover:bg-zinc-50",
                ].join(" ")}
              >
                <span className="flex items-center gap-2">
                  <span className="w-3 text-center text-zinc-400">{icon}</span>
                  {label}
                </span>
                <span className="text-[11px] tabular-nums text-zinc-400">{counts[k]}</span>
              </button>
            </li>
          );
        })}
      </ul>

      <div className="mt-2 border-t border-zinc-100 pt-2">
        <label className="flex cursor-pointer items-center gap-2 px-1 text-[12px] text-zinc-700">
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => onActiveOnlyChange(e.target.checked)}
            className="h-3.5 w-3.5"
          />
          仅显示启用
        </label>
      </div>

      <div className="mt-auto flex flex-col gap-1 rounded border border-dashed border-zinc-200 px-2 py-2 text-[11px] leading-relaxed text-zinc-400">
        <div>新建约束：</div>
        <div className="flex flex-wrap gap-1 mt-1">
          {(["predecessor", "resource", "takt", "exclusion"] as ConstraintKind[]).map((k) => (
            <button
              key={k}
              type="button"
              className="rounded bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-700 border border-violet-200 hover:bg-violet-100"
              onClick={() => onCreate(k)}
            >
              {KIND_META[k].icon} {KIND_META[k].label}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}

// ── Center: validation banner + table ─────────────────────────────────

function Center({
  items, allItems, selectedId, onSelect, loading, error, validation, validationLoading,
  selectedAsset, onSelectAsset,
}: {
  items: ConstraintItem[];
  allItems: ConstraintItem[];
  selectedId: string | null;
  onSelect: (cid: string) => void;
  loading: boolean;
  error: unknown;
  validation: ValidationIssue[];
  validationLoading: boolean;
  selectedAsset: string | null;
  onSelectAsset: (asset: string | null) => void;
}) {
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-md border border-zinc-200 bg-white">
      <ValidationBanner issues={validation} loading={validationLoading} />
      <div className="h-[260px] shrink-0 border-b border-zinc-100">
        <ConstraintGraph
          items={allItems}
          validation={validation}
          selectedAsset={selectedAsset}
          onSelectAsset={onSelectAsset}
        />
      </div>
      {loading ? (
        <PadMsg>加载约束中…</PadMsg>
      ) : error ? (
        <PadMsg error>加载失败：{String((error as Error).message || "unknown")}</PadMsg>
      ) : items.length === 0 ? (
        <PadMsg>暂无约束。新建按钮即将上线。</PadMsg>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full text-left text-[12px]">
            <thead className="sticky top-0 z-10 bg-zinc-50 text-[11px] uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="px-3 py-2 font-medium">类型</th>
                <th className="px-3 py-2 font-medium">ID</th>
                <th className="px-3 py-2 font-medium">摘要</th>
                <th className="px-3 py-2 text-right font-medium">优先级</th>
                <th className="px-3 py-2 font-medium">状态</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {items.map((i) => {
                const active = i.constraint_id === selectedId;
                const meta = KIND_META[i.kind];
                return (
                  <tr
                    key={i.id}
                    onClick={() => onSelect(i.constraint_id)}
                    className={[
                      "cursor-pointer hover:bg-zinc-50",
                      active ? "bg-violet-50" : "",
                    ].join(" ")}
                  >
                    <td className="px-3 py-2">
                      <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${meta.chipClass}`}>
                        <span>{meta.icon}</span> {meta.label}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-zinc-600">
                      {i.constraint_id}
                    </td>
                    <td className="px-3 py-2 text-zinc-700">{summary(i)}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-zinc-500">
                      {i.priority}
                    </td>
                    <td className="px-3 py-2">
                      {i.is_active ? (
                        <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
                          启用
                        </span>
                      ) : (
                        <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium text-zinc-500">
                          停用
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function summary(i: ConstraintItem): string {
  const p = i.payload;
  switch (p.kind) {
    case "predecessor":
      return `${p.from} → ${p.to}${p.lag_s ? `  (lag ${p.lag_s}s)` : ""}`;
    case "resource":
      return `${p.resource} (cap=${p.capacity}) · ${p.asset_ids.length} 资产`;
    case "takt":
      return `${p.asset_id} · ${p.min_s}s ~ ${p.max_s}s`;
    case "exclusion":
      return `${p.asset_ids.length} 资产互斥${p.reason ? ` · ${p.reason}` : ""}`;
  }
}

// ── Validation banner ─────────────────────────────────────────────────

function ValidationBanner({
  issues, loading,
}: { issues: ValidationIssue[]; loading: boolean }) {
  if (loading) {
    return (
      <div className="border-b border-zinc-100 px-3 py-1.5 text-[11px] text-zinc-400">
        校验中…
      </div>
    );
  }
  if (issues.length === 0) {
    return (
      <div className="flex items-center gap-1.5 border-b border-emerald-100 bg-emerald-50/50 px-3 py-1.5 text-[12px] text-emerald-700">
        <Icon name="check" size={12} /> 校验通过 · 无循环依赖、资源超载或节拍异常
      </div>
    );
  }
  const errors = issues.filter((i) => i.severity === "error");
  const warns = issues.filter((i) => i.severity === "warning");
  return (
    <div
      className={[
        "border-b px-3 py-2 text-[12px]",
        errors.length > 0
          ? "border-rose-200 bg-rose-50 text-rose-800"
          : "border-amber-200 bg-amber-50 text-amber-800",
      ].join(" ")}
    >
      <div className="flex items-center gap-1.5 font-medium">
        <Icon name={errors.length > 0 ? "alert-circle" : "alert-triangle"} size={13} />
        校验问题 · {errors.length} 错误 · {warns.length} 警告
      </div>
      <ul className="mt-1 space-y-0.5 pl-5 text-[11px] leading-relaxed">
        {issues.slice(0, 5).map((iss, idx) => (
          <li key={idx}>
            <span className={iss.severity === "error" ? "font-mono text-rose-600" : "font-mono text-amber-600"}>
              [{iss.code}]
            </span>{" "}
            {iss.message}
            {iss.constraint_ids.length > 0 && (
              <span className="ml-1 text-zinc-500">
                ({iss.constraint_ids.join(", ")})
              </span>
            )}
          </li>
        ))}
        {issues.length > 5 && (
          <li className="text-zinc-500">…等 {issues.length - 5} 项</li>
        )}
      </ul>
    </div>
  );
}

// ── Right detail (read-only JSON) ─────────────────────────────────────

function RightDetail({ item }: { item: ConstraintItem | null }) {
  if (!item) {
    return (
      <aside className="flex items-center justify-center rounded-md border border-zinc-200 bg-white p-4 text-[12px] text-zinc-400">
        在左侧表格中选择一项
      </aside>
    );
  }
  const meta = KIND_META[item.kind];
  return (
    <aside className="flex flex-col gap-3 overflow-hidden rounded-md border border-zinc-200 bg-white p-3 text-[12px]">
      <header>
        <div className="flex items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${meta.chipClass}`}>
            {meta.icon} {meta.label}
          </span>
          <span className="font-mono text-[11px] text-zinc-600">{item.constraint_id}</span>
        </div>
        <div className="mt-1 text-[11px] text-zinc-500">
          优先级 {item.priority} · {item.is_active ? "启用中" : "已停用"} · 创建于{" "}
          {new Date(item.created_at).toLocaleString("zh-CN")}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto rounded border border-zinc-100 bg-zinc-50 p-2">
        <pre className="whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-zinc-700">
{JSON.stringify(item.payload, null, 2)}
        </pre>
      </div>

      <div className="text-[11px] text-zinc-500">
        创建者：<span className="font-mono">{item.created_by ?? "—"}</span>
      </div>

      <div className="rounded border border-dashed border-zinc-200 px-2 py-1.5 text-center text-[11px] text-zinc-400">
        编辑 / 删除 即将上线
      </div>
    </aside>
  );
}

function PadMsg({ children, error }: { children: React.ReactNode; error?: boolean }) {
  return (
    <div
      className={[
        "flex flex-1 items-center justify-center p-8 text-[12px]",
        error ? "text-rose-600" : "text-zinc-400",
      ].join(" ")}
    >
      {children}
    </div>
  );
}
