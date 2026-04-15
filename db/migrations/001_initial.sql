-- ════════════════ ProLine CAD — 初始数据库 DDL ════════════════
-- 文件: db/migrations/001_initial.sql
-- 说明: 创建核心表结构，用于 SiteModel、mcp_context、约束和审计存储。
-- 参考: ExcPlan/执行计划 §1.1 数据库设置

-- ── MCP Context 表（按时间分区） ──
CREATE TABLE IF NOT EXISTS mcp_contexts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mcp_context_id VARCHAR(100) UNIQUE NOT NULL,
    agent VARCHAR(50) NOT NULL,
    agent_version VARCHAR(20) DEFAULT 'v1.0',
    parent_context_id VARCHAR(100) REFERENCES mcp_contexts(mcp_context_id),
    input_payload JSONB DEFAULT '{}',
    output_payload JSONB DEFAULT '{}',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    latency_ms INT DEFAULT 0,
    provenance JSONB DEFAULT '{}',
    status VARCHAR(30) NOT NULL DEFAULT 'SUCCESS',
    error_message TEXT,
    step_breakdown JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mcp_ctx_agent ON mcp_contexts(agent);
CREATE INDEX IF NOT EXISTS idx_mcp_ctx_parent ON mcp_contexts(parent_context_id);
CREATE INDEX IF NOT EXISTS idx_mcp_ctx_timestamp ON mcp_contexts(timestamp);
CREATE INDEX IF NOT EXISTS idx_mcp_ctx_status ON mcp_contexts(status);

-- ── SiteModel 表 ──
CREATE TABLE IF NOT EXISTS site_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_model_id VARCHAR(50) UNIQUE NOT NULL,
    cad_source JSONB NOT NULL DEFAULT '{}',
    assets JSONB NOT NULL DEFAULT '[]',
    links JSONB NOT NULL DEFAULT '[]',
    geometry_integrity_score NUMERIC(5, 4) DEFAULT 0.0,
    statistics JSONB DEFAULT '{}',
    mcp_context_id VARCHAR(100) REFERENCES mcp_contexts(mcp_context_id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_site_model_id ON site_models(site_model_id);

-- ── 约束集表 ──
CREATE TABLE IF NOT EXISTS constraint_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    constraint_set_id VARCHAR(50) UNIQUE NOT NULL,
    version VARCHAR(20) NOT NULL DEFAULT 'v1.0',
    hard_constraints JSONB NOT NULL DEFAULT '[]',
    soft_constraints JSONB NOT NULL DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 布局候选方案表 ──
CREATE TABLE IF NOT EXISTS layout_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_model_id VARCHAR(50) NOT NULL REFERENCES site_models(site_model_id),
    plan_id VARCHAR(10) NOT NULL,
    score NUMERIC(5, 4) DEFAULT 0.0,
    hard_pass BOOLEAN DEFAULT FALSE,
    adjustments JSONB DEFAULT '[]',
    reasoning TEXT DEFAULT '',
    reasoning_chain JSONB DEFAULT '[]',
    convergence_info JSONB DEFAULT '{}',
    mcp_context_id VARCHAR(100) REFERENCES mcp_contexts(mcp_context_id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_layout_site ON layout_candidates(site_model_id);
CREATE INDEX IF NOT EXISTS idx_layout_score ON layout_candidates(score DESC);

-- ── 审计记录表 ──
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id VARCHAR(100) UNIQUE NOT NULL,
    decision VARCHAR(30) NOT NULL,
    mcp_context_ids JSONB NOT NULL DEFAULT '[]',
    approver VARCHAR(200),
    signature TEXT,
    pdf_sha256 VARCHAR(64),
    artifact_urls JSONB DEFAULT '[]',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_decision ON audit_logs(decision);

-- ── 工作流状态表 ──
CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id VARCHAR(100) UNIQUE NOT NULL,
    state VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    cad_filename VARCHAR(500),
    site_model_id VARCHAR(50),
    iteration INT DEFAULT 0,
    max_iterations INT DEFAULT 3,
    context_chain JSONB DEFAULT '[]',
    error_message TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_state ON workflows(state);
