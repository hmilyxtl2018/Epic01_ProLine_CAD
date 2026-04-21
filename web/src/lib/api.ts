// Tiny fetch wrapper -- cookie session + double-submit CSRF.
//
// Auth model (M3, Phase E2 cookie path):
//   - POST /auth/login-cookie sets `proline_session` (httpOnly) + `proline_csrf`
//     (JS-readable). Browser then sends both on every same-origin request via
//     `credentials: "include"`.
//   - For state-changing methods we ALSO send the CSRF token in the
//     `X-CSRF-Token` header. Backend constant-time compares cookie vs header
//     and HMAC-verifies the token against the actor.
//   - Legacy `X-Role` / `X-Actor` headers are still sent so internal tooling
//     and tests that rely on them keep working until M4 fully retires them.

import type { ErrorEnvelope, Role } from "./types";

const ROLE_KEY = "proline.role";
const ACTOR_KEY = "proline.actor";
const CSRF_COOKIE = "proline_csrf";

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

export function readCsrfCookie(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(new RegExp(`(?:^|; )${CSRF_COOKIE}=([^;]+)`));
  return m ? decodeURIComponent(m[1]) : "";
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

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
  const method = (opts.method || "GET").toUpperCase();
  const headers: Record<string, string> = {
    // Legacy headers -- kept for backwards-compat during M3 rollout.
    "X-Role": getRole(),
    "X-Actor": getActor(),
    ...(opts.headers || {}),
  };
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCsrfCookie();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  const r = await fetch(`/api${path}`, {
    method,
    body: opts.body ?? null,
    headers,
    signal: opts.signal,
    credentials: "include",
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
    const env =
      parsed && typeof parsed === "object" && "error_code" in parsed
        ? (parsed as ErrorEnvelope)
        : null;
    throw new ApiError(env?.message || r.statusText, r.status, env);
  }
  return parsed as T;
}

import type {
  AuthIdentity,
  LoginCookieRequest,
  LoginCookieResponse,
  QuarantineDecideRequest,
  QuarantineDecideResponse,
  QuarantineListResponse,
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
  listQuarantine: (
    opts: { page?: number; pageSize?: number; status?: string; assetType?: string } = {},
  ) => {
    const p = new URLSearchParams();
    p.set("page", String(opts.page ?? 1));
    p.set("page_size", String(opts.pageSize ?? 20));
    if (opts.status) p.set("status", opts.status);
    if (opts.assetType) p.set("asset_type", opts.assetType);
    return request<QuarantineListResponse>(`/dashboard/quarantine?${p.toString()}`);
  },
  decideQuarantine: (id: string, body: QuarantineDecideRequest) =>
    request<QuarantineDecideResponse>(
      `/dashboard/quarantine/${encodeURIComponent(id)}/decide`,
      {
        method: "POST",
        body: JSON.stringify(body),
        headers: { "Content-Type": "application/json" },
      },
    ),
};

export const auth = {
  login: (body: LoginCookieRequest) =>
    request<LoginCookieResponse>("/auth/login-cookie", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  me: () => request<AuthIdentity>("/auth/me"),
};
