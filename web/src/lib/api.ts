// Tiny fetch wrapper -- adds X-Role / X-Actor headers, parses ErrorEnvelope.
//
// Headers come from localStorage so the user can switch roles via the
// RoleSwitcher component without re-login (M1 trust model; M3 will JWT).

import type { ErrorEnvelope, Role } from "./types";

const ROLE_KEY = "proline.role";
const ACTOR_KEY = "proline.actor";

export function getRole(): Role {
  if (typeof window === "undefined") return "viewer";
  const v = window.localStorage.getItem(ROLE_KEY);
  if (v === "viewer" || v === "operator" || v === "reviewer" || v === "admin") return v;
  return "viewer";
}

export function setRole(role: Role): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ROLE_KEY, role);
}

export function getActor(): string {
  if (typeof window === "undefined") return "anonymous@dev";
  return window.localStorage.getItem(ACTOR_KEY) || "anonymous@dev";
}

export function setActor(actor: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACTOR_KEY, actor);
}

export class ApiError extends Error {
  envelope: ErrorEnvelope | null;
  status: number;
  constructor(message: string, status: number, envelope: ErrorEnvelope | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.envelope = envelope;
  }
}

interface RequestOpts {
  method?: string;
  body?: BodyInit | null;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

async function request<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const headers: Record<string, string> = {
    "X-Role": getRole(),
    "X-Actor": getActor(),
    ...(opts.headers || {}),
  };
  // /api/* is rewritten to the backend by next.config.js (dev) and by your
  // ingress in prod. No CORS needed.
  const r = await fetch(`/api${path}`, {
    method: opts.method || "GET",
    body: opts.body ?? null,
    headers,
    signal: opts.signal,
  });
  const text = await r.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      // keep as null; non-JSON body
    }
  }
  if (!r.ok) {
    const env = (parsed && typeof parsed === "object" && "error_code" in parsed
      ? (parsed as ErrorEnvelope)
      : null);
    throw new ApiError(env?.message || r.statusText, r.status, env);
  }
  return parsed as T;
}

import type {
  RunCreatedResponse,
  RunDetail,
  RunListResponse,
} from "./types";

export const api = {
  listRuns: (page = 1, pageSize = 20) =>
    request<RunListResponse>(`/dashboard/runs?page=${page}&page_size=${pageSize}`),
  getRun: (id: string) => request<RunDetail>(`/dashboard/runs/${id}`),
  uploadRun: (file: File) => {
    const fd = new FormData();
    fd.append("cad_file", file);
    return request<RunCreatedResponse>("/dashboard/runs", {
      method: "POST",
      body: fd,
    });
  },
};
