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
