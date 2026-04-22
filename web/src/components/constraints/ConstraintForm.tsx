import type { ConstraintKind, ConstraintCreateRequest, ConstraintUpdateRequest, ConstraintItem } from "@/lib/types";
import { useState } from "react";

interface Props {
  kind: ConstraintKind;
  initial?: Partial<ConstraintCreateRequest | ConstraintUpdateRequest>;
  assets: string[];
  onSubmit: (data: ConstraintCreateRequest | ConstraintUpdateRequest) => void;
  onCancel: () => void;
}

export function ConstraintForm({ kind, initial = {}, assets, onSubmit, onCancel }: Props) {
  // Discriminated union: 4 forms by kind
  const [form, setForm] = useState(() => {
    switch (kind) {
      case "predecessor":
        return {
          kind,
          from: initial.from ?? "",
          to: initial.to ?? "",
          lag_s: initial.lag_s ?? 0,
          priority: initial.priority ?? 1,
          is_active: initial.is_active ?? true,
        };
      case "resource":
        return {
          kind,
          resource: initial.resource ?? "",
          capacity: initial.capacity ?? 1,
          asset_ids: initial.asset_ids ?? [],
          priority: initial.priority ?? 1,
          is_active: initial.is_active ?? true,
        };
      case "takt":
        return {
          kind,
          asset_id: initial.asset_id ?? "",
          min_s: initial.min_s ?? 0,
          max_s: initial.max_s ?? 0,
          priority: initial.priority ?? 1,
          is_active: initial.is_active ?? true,
        };
      case "exclusion":
        return {
          kind,
          asset_ids: initial.asset_ids ?? [],
          reason: initial.reason ?? "",
          priority: initial.priority ?? 1,
          is_active: initial.is_active ?? true,
        };
    }
  });

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
    const { name, value, type, checked } = e.target;
    setForm((f: any) => ({
      ...f,
      [name]: type === "checkbox" ? checked : type === "number" ? Number(value) : value,
    }));
  }

  function handleAssetIdsChange(ids: string[]) {
    setForm((f: any) => ({ ...f, asset_ids: ids }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit(form as any);
  }

  // Per-kind form fields
  let fields: React.ReactNode = null;
  switch (kind) {
    case "predecessor":
      fields = (
        <>
          <label>前置资产
            <select name="from" value={(form as any).from} onChange={handleChange} required>
              <option value="">请选择</option>
              {assets.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label>后置资产
            <select name="to" value={(form as any).to} onChange={handleChange} required>
              <option value="">请选择</option>
              {assets.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label>滞后秒数
            <input name="lag_s" type="number" min={0} value={(form as any).lag_s} onChange={handleChange} />
          </label>
        </>
      );
      break;
    case "resource":
      fields = (
        <>
          <label>资源名
            <input name="resource" value={(form as any).resource} onChange={handleChange} required />
          </label>
          <label>容量
            <input name="capacity" type="number" min={1} value={(form as any).capacity} onChange={handleChange} required />
          </label>
          <label>资产
            <select multiple value={(form as any).asset_ids} onChange={e => handleAssetIdsChange(Array.from(e.target.selectedOptions, o => o.value))}>
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
            <select name="asset_id" value={(form as any).asset_id} onChange={handleChange} required>
              <option value="">请选择</option>
              {assets.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label>最小秒数
            <input name="min_s" type="number" min={0} value={(form as any).min_s} onChange={handleChange} required />
          </label>
          <label>最大秒数
            <input name="max_s" type="number" min={0} value={(form as any).max_s} onChange={handleChange} required />
          </label>
        </>
      );
      break;
    case "exclusion":
      fields = (
        <>
          <label>资产
            <select multiple value={(form as any).asset_ids} onChange={e => handleAssetIdsChange(Array.from(e.target.selectedOptions, o => o.value))}>
              {assets.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label>理由
            <input name="reason" value={(form as any).reason} onChange={handleChange} />
          </label>
        </>
      );
      break;
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 p-3">
      {fields}
      <label>优先级
        <input name="priority" type="number" min={1} max={10} value={(form as any).priority} onChange={handleChange} required />
      </label>
      <label>
        <input name="is_active" type="checkbox" checked={(form as any).is_active} onChange={handleChange} /> 启用
      </label>
      <div className="flex gap-2 mt-2">
        <button type="submit" className="btn btn-primary">保存</button>
        <button type="button" className="btn btn-secondary" onClick={onCancel}>取消</button>
      </div>
    </form>
  );
}
