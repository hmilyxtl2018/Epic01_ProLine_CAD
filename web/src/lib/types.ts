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
  filename: string | null;
  size_bytes: number | null;
  detected_format: string | null;
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
  site_model_statistics: Record<string, unknown>;
  site_model_cad_source: Record<string, unknown>;
  site_model_assets_count: number;
}

// ── LLM enrichment shape (lives under output_payload.llm_enrichment) ──

export interface LLMEnrichment {
  sections: {
    A_normalize?: { items: any[]; stats: any; rationale: string };
    B_softmatch?: { matches: any[]; stats: any; thresholds: any };
    C_arbiter?: { counts: any; review_queue: any[]; promotion_candidates: any[]; rationale: string };
    D_cluster_proposals?: { proposals: any[]; stats: any; rationale: string };
    E_block_kind?: { items: any[]; kind_counts: Record<string, number>; total_classified: number; rationale: string };
    F_quality_breakdown?: { parse: number; semantic: number; integrity: number; overall: number; why: string; weights: Record<string, number> };
    G_root_cause?: { root_causes: any[]; uncategorized: string[]; rationale?: string };
    H_audit_narrative?: { narrative: string; cited_fields: string[] };
    I_self_check?: { should_block: boolean; severity: string; blockers: string[]; advice: string };
    J_site_describe?: { title: string; description: string; suggested_tags: string[]; evidence: any[] };
    K_asset_extract?: { assets: any[]; stats: any; rationale: string; backlog: string[] };
    L_geom_anomaly?: { findings: any[]; rationale: string };
    M_provenance_note?: { release: string; languages: string[]; multi_team_source: boolean; note: string; evidence: any[] };
    [k: string]: any;
  };
  timings_ms: Record<string, number>;
  errors: Record<string, string>;
  steps_run: string[];
  version: string;
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

// ── Phase 2.3 process_constraints ──────────────────────────────────────

export type ConstraintKind = "predecessor" | "resource" | "takt" | "exclusion";

export interface PredecessorPayload {
  kind: "predecessor";
  from: string;
  to: string;
  lag_s?: number;
}
export interface ResourcePayload {
  kind: "resource";
  asset_ids: string[];
  resource: string;
  capacity: number;
}
export interface TaktPayload {
  kind: "takt";
  asset_id: string;
  min_s: number;
  max_s: number;
}
export interface ExclusionPayload {
  kind: "exclusion";
  asset_ids: string[];
  reason?: string | null;
}
export type ConstraintPayload =
  | PredecessorPayload
  | ResourcePayload
  | TaktPayload
  | ExclusionPayload;

// ── M0 (blueprint G1/G2/G4) — closed enums mirrored from shared/models.py ──

export const CONSTRAINT_CATEGORIES = [
  "SPATIAL",
  "SEQUENCE",
  "TORQUE",
  "SAFETY",
  "ENVIRONMENTAL",
  "REGULATORY",
  "QUALITY",
  "RESOURCE",
  "LOGISTICS",
  "OTHER",
] as const;
export type ConstraintCategory = (typeof CONSTRAINT_CATEGORIES)[number];

export const CONSTRAINT_REVIEW_STATUSES = [
  "draft",
  "under_review",
  "approved",
  "rejected",
  "superseded",
] as const;
export type ConstraintReviewStatus =
  (typeof CONSTRAINT_REVIEW_STATUSES)[number];

export const CONSTRAINT_PARSE_METHODS = [
  "MANUAL_UI",
  "EXCEL_IMPORT",
  "MBOM_IMPORT",
  "PMI_ENGINE",
  "LLM_INFERENCE",
] as const;
export type ConstraintParseMethod = (typeof CONSTRAINT_PARSE_METHODS)[number];

export const CONSTRAINT_SOURCE_CLASSIFICATIONS = [
  "PUBLIC",
  "INTERNAL",
  "CONFIDENTIAL",
  "SECRET",
] as const;
export type ConstraintSourceClassification =
  (typeof CONSTRAINT_SOURCE_CLASSIFICATIONS)[number];

export interface ConstraintItem {
  id: string;
  constraint_id: string;
  site_model_id: string;
  kind: ConstraintKind;
  payload: ConstraintPayload;
  priority: number;
  is_active: boolean;
  category: ConstraintCategory;
  review_status: ConstraintReviewStatus;
  parse_method: ConstraintParseMethod;
  verified_by_user_id: string | null;
  verified_at: string | null;
  needs_re_review: boolean;
  created_by: string | null;
  mcp_context_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConstraintListResponse {
  items: ConstraintItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ConstraintCreateRequest {
  constraint_id: string;
  payload: ConstraintPayload;
  priority?: number;
  is_active?: boolean;
  category?: ConstraintCategory;
  review_status?: ConstraintReviewStatus;
  parse_method?: ConstraintParseMethod;
}

export interface ConstraintUpdateRequest {
  payload?: ConstraintPayload;
  priority?: number;
  is_active?: boolean;
  category?: ConstraintCategory;
  review_status?: ConstraintReviewStatus;
  needs_re_review?: boolean;
}

export interface ValidationIssue {
  severity: "error" | "warning";
  code: string;
  message: string;
  constraint_ids: string[];
  asset_ids: string[];
}

export interface ValidationReport {
  site_model_id: string;
  ok: boolean;
  checked_count: number;
  issues: ValidationIssue[];
}
