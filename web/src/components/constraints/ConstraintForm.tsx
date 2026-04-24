import type {
  ConstraintKind,
  PredecessorPayload,
  ResourcePayload,
  TaktPayload,
  ExclusionPayload,
} from "@/lib/types";
import { useState } from "react";

/**
 * A flat, partial-all-fields shape used as the form's `initial` prop.
 *
 * The 4 `ConstraintPayload` variants live on `ConstraintItem.payload`, not at
 * the top level of `ConstraintCreateRequest`, so typing `initial` as
 * `Partial<ConstraintCreateRequest | ConstraintUpdateRequest>` (the previous
 * version) made every field access (`initial.from`, `.asset_ids`, …) fail
 * with TS2339. Flattening the union across all kinds + form-only fields
 * (`priority`, `is_active`) matches how this component actually uses it.
 */
export interface ConstraintFormInitial {
  from?: string;
  to?: string;
  lag_s?: number;
  resource?: string;
  capacity?: number;
  asset_ids?: string[];
  asset_id?: string;
  min_s?: number;
  max_s?: number;
  reason?: string | null;
  priority?: number;
  is_active?: boolean;
}

/**
 * Shape handed to `onSubmit`. `ConstraintsPanel` is responsible for splitting
 * this back into `{ payload, priority, is_active }` before POSTing.
 */
export type ConstraintFormData =
  | (PredecessorPayload & { priority: number; is_active: boolean })
  | (ResourcePayload & { priority: number; is_active: boolean })
  | (TaktPayload & { priority: number; is_active: boolean })
  | (ExclusionPayload & { priority: number; is_active: boolean });

interface Props {
  kind: ConstraintKind;
  initial?: ConstraintFormInitial;
  assets: string[];
  onSubmit: (data: ConstraintFormData) => void;
  onCancel: () => void;
}

export function ConstraintForm({ kind, initial = {}, assets, onSubmit, onCancel }: Props) {
  // Discriminated union: 4 forms by kind
  const [form, setForm] = useState<ConstraintFormData>(() => {
    const base = {
      priority: initial.priority ?? 1,
      is_active: initial.is_active ?? true,
    };
    switch (kind) {
      case "predecessor":
        return {
          kind,
          from: initial.from ?? "",
          to: initial.to ?? "",
          lag_s: initial.lag_s ?? 0,
          ...base,
        };
      case "resource":
        return {
          kind,
          resource: initial.resource ?? "",
          capacity: initial.capacity ?? 1,
          asset_ids: initial.asset_ids ?? [],
          ...base,
        };
      case "takt":
        return {
          kind,
          asset_id: initial.asset_id ?? "",
          min_s: initial.min_s ?? 0,
          max_s: initial.max_s ?? 0,
          ...base,
        };
      case "exclusion":
        return {
          kind,
          asset_ids: initial.asset_ids ?? [],
          reason: initial.reason ?? "",
          ...base,
        };
    }
  });

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) {
    // `checked` only exists on HTMLInputElement, and on the union
    // HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement TypeScript
    // correctly refuses to let us destructure it. Narrow explicitly.
    const target = e.target as HTMLInputElement;
    const { name, value, type } = target;
    const checked = target.checked;
    setForm((f) => ({
      ...(f as unknown as Record<string, unknown>),
      [name]:
        type === "checkbox" ? checked : type === "number" ? Number(value) : value,
    }) as unknown as ConstraintFormData);
  }

  function handleAssetIdsChange(ids: string[]) {
    setForm(
      (f) =>
        ({
          ...(f as unknown as Record<string, unknown>),
          asset_ids: ids,
        }) as unknown as ConstraintFormData,
    );
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit(form);
  }

  // Per-kind form fields.
  // We read `form` through a narrow helper so the JSX below doesn't need
  // discriminated-union guards on every field.
  const f = form as ConstraintFormData & Record<string, any>;

  let fields: React.ReactNode = null;
  switch (kind) {
    case "predecessor":
      fields = (
        <>
          <label>前置资产
            <select name="from" value={f.from ?? ""} onChange={handleChange} required>
              <option value="">请选择</option>
              {assets.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label>后置资产
            <select name="to" value={f.to ?? ""} onChange={handleChange} required>
              <option value="">请选择</option>
              {assets.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label>滞后秒数
            <input name="lag_s" type="number" min={0} value={f.lag_s ?? 0} onChange={handleChange} />
          </label>
        </>
      );
      break;
    case "resource":
      fields = (
        <>
          <label>资源名
            <input name="resource" value={f.resource ?? ""} onChange={handleChange} required />
          </label>
          <label>容量
            <input name="capacity" type="number" min={1} value={f.capacity ?? 1} onChange={handleChange} required />
          </label>
          <label>资产
            <select
              multiple
              value={f.asset_ids ?? []}
              onChange={(e) =>
                handleAssetIdsChange(Array.from(e.target.selectedOptions, (o) => o.value))
              }
            >
              {assets.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
        </>
      );
      break;
    case "takt":
      fields = (
        <>
          <label>资产
            <select name="asset_id" value={f.asset_id ?? ""} onChange={handleChange} required>
              <option value="">请选择</option>
              {assets.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label>最小秒数
            <input name="min_s" type="number" min={0} value={f.min_s ?? 0} onChange={handleChange} required />
          </label>
          <label>最大秒数
            <input name="max_s" type="number" min={0} value={f.max_s ?? 0} onChange={handleChange} required />
          </label>
        </>
      );
      break;
    case "exclusion":
      fields = (
        <>
          <label>资产
            <select
              multiple
              value={f.asset_ids ?? []}
              onChange={(e) =>
                handleAssetIdsChange(Array.from(e.target.selectedOptions, (o) => o.value))
              }
            >
              {assets.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label>理由
            <input name="reason" value={f.reason ?? ""} onChange={handleChange} />
          </label>
        </>
      );
      break;
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 p-3">
      {fields}
      <label>优先级
        <input
          name="priority"
          type="number"
          min={1}
          max={10}
          value={f.priority}
          onChange={handleChange}
          required
        />
      </label>
      <label>
        <input
          name="is_active"
          type="checkbox"
          checked={f.is_active}
          onChange={handleChange}
        />{" "}
        启用
      </label>
      <div className="flex gap-2 mt-2">
        <button type="submit" className="btn btn-primary">保存</button>
        <button type="button" className="btn btn-secondary" onClick={onCancel}>取消</button>
      </div>
    </form>
  );
}
