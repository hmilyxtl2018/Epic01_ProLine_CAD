"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ApiError, api, getRole } from "@/lib/api";

export function UploadForm() {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const role = typeof window === "undefined" ? "viewer" : getRole();
  const allowed = role === "operator" || role === "admin";

  const mutation = useMutation({
    mutationFn: (file: File) => api.uploadRun(file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      if (inputRef.current) inputRef.current.value = "";
      setError(null);
    },
    onError: (e: unknown) => {
      if (e instanceof ApiError) {
        setError(`${e.envelope?.error_code || e.status}: ${e.envelope?.message || e.message}`);
      } else {
        setError(String(e));
      }
    },
  });

  if (!allowed) {
    return (
      <div className="rounded border border-dashed p-4 text-sm text-zinc-500">
        Switch role to <code>operator</code> or <code>admin</code> to upload.
      </div>
    );
  }

  return (
    <form
      className="flex flex-col gap-2 rounded border bg-white p-4"
      onSubmit={(e) => {
        e.preventDefault();
        const f = inputRef.current?.files?.[0];
        if (f) mutation.mutate(f);
      }}
    >
      <label className="text-sm font-medium">Upload CAD file (≤ 50 MB)</label>
      <input
        ref={inputRef}
        type="file"
        accept=".dwg,.dxf,.ifc,.step,.stp"
        className="text-sm"
        disabled={mutation.isPending}
      />
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="rounded bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          {mutation.isPending ? "Uploading…" : "Upload & enqueue"}
        </button>
        {mutation.isSuccess && (
          <span className="text-xs text-status-success">
            Created run <code>{mutation.data.run_id.slice(0, 8)}…</code>
          </span>
        )}
      </div>
      {error && <p className="text-xs text-status-error">{error}</p>}
    </form>
  );
}
