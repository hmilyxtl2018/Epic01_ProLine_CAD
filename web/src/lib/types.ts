// Shared types mirroring app/schemas/runs.py.
// Keep field names in sync; backend is source of truth.

export type RunStatus =
  | "PENDING"
  | "RUNNING"
  | "SUCCESS"
  | "SUCCESS_WITH_WARNINGS"
  | "ERROR";

export interface RunSummary {
  mcp_context_id: string;
  agent: string;
  agent_version: string | null;
  status: RunStatus | string;
  timestamp: string;
  latency_ms: number | null;
}

export interface RunListResponse {
  items: RunSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface RunDetail extends RunSummary {
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error_message: string | null;
  site_model_id: string | null;
  geometry_integrity_score: number | null;
}

export interface RunCreatedResponse {
  run_id: string;
  mcp_context_id: string;
  status: RunStatus;
  upload_path: string;
}

export interface ErrorEnvelope {
  error_code: string;
  message: string;
  mcp_context_id: string | null;
  retryable: boolean;
}

export type Role = "viewer" | "operator" | "reviewer" | "admin";

// ── Auth ──────────────────────────────────────────────────────────────

export interface AuthIdentity {
  actor: string;
  role: Role | string;
}

export interface LoginCookieRequest {
  email: string;
  password: string;
  role: Role | string;
}

// /auth/login-cookie returns MeResponse on the wire: { actor, role }.
export type LoginCookieResponse = AuthIdentity;

// ── WebSocket frames ──────────────────────────────────────────────────

export interface WsStatusFrame {
  event: "status";
  mcp_context_id: string;
  status: RunStatus | string;
  ts: string;
}

export interface WsNotFoundFrame {
  event: "not_found";
  mcp_context_id: string;
}

export type WsRunFrame = WsStatusFrame | WsNotFoundFrame;

// ── Quarantine ────────────────────────────────────────────────────────

export type QuarantineDecision = "approve" | "reject" | "merge";

export interface QuarantineItem {
  id: string;
  term_normalized: string;
  term_display: string;
  asset_type: string;
  count: number;
  evidence: unknown[];
  first_seen: string;
  last_seen: string;
  decision: string | null;
  reviewer: string | null;
  reviewed_at: string | null;
  merge_target_id: string | null;
  mcp_context_id: string | null;
  created_at: string;
}

export interface QuarantineListResponse {
  items: QuarantineItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface QuarantineDecideRequest {
  decision: QuarantineDecision;
  merge_target_id?: string | null;
  reason?: string | null;
}

export interface QuarantineDecideResponse {
  id: string;
  decision: string;
  reviewer: string;
  reviewed_at: string;
}
