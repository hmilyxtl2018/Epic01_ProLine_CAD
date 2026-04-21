-- ════════════════ Minimal Seed Data ════════════════
-- B5: provides the smallest set of rows that lets every B0-B6 table be
-- exercised by integration tests without producing FK violations.
-- Idempotent: every INSERT uses ON CONFLICT DO NOTHING.
--
-- Loaded by pytest `db_fixture` after `alembic upgrade head`.

-- ── mcp_context root ──
INSERT INTO mcp_contexts (mcp_context_id, agent, status)
VALUES ('mcp_seed_root', 'parse_agent', 'SUCCESS')
ON CONFLICT (mcp_context_id) DO NOTHING;

-- ── site_model + bbox ──
INSERT INTO site_models (site_model_id, cad_source, mcp_context_id, bbox)
VALUES (
    'site_seed_001',
    '{"format":"DWG","filename":"seed.dwg","dwg_hash":"deadbeef"}'::jsonb,
    'mcp_seed_root',
    ST_GeomFromText('POLYGON((0 0, 100 0, 100 100, 0 100, 0 0))', 0)
)
ON CONFLICT (site_model_id) DO NOTHING;

-- ── asset_geometry (uses CHECK on asset_type + confidence) ──
INSERT INTO asset_geometries (
    site_model_id, asset_guid, asset_type, footprint, centroid, confidence,
    classifier_kind, mcp_context_id
)
VALUES (
    'site_seed_001', 'asset_seed_001', 'Equipment',
    ST_GeomFromText('POLYGON((10 10, 30 10, 30 30, 10 30, 10 10))', 0),
    ST_GeomFromText('POINT(20 20)', 0),
    0.95, 'rule_classifier', 'mcp_seed_root'
)
ON CONFLICT (site_model_id, asset_guid) DO NOTHING;

-- ── taxonomy_terms gold sample ──
INSERT INTO taxonomy_terms (term_normalized, term_display, asset_type, source)
VALUES ('conveyor', 'Conveyor', 'Conveyor', 'gold')
ON CONFLICT DO NOTHING;

-- ── quarantine_terms pending sample ──
INSERT INTO quarantine_terms (
    term_normalized, term_display, asset_type, count, first_seen, last_seen,
    decision, mcp_context_id
)
VALUES (
    'roller belt assembly', 'Roller Belt Assembly', 'Conveyor', 3,
    NOW() - INTERVAL '2 days', NOW(), 'pending', 'mcp_seed_root'
)
ON CONFLICT DO NOTHING;

-- ── audit_log_actions sample ──
INSERT INTO audit_log_actions (
    actor, actor_role, action, target_type, target_id, payload, mcp_context_id
)
VALUES (
    'seed@local', 'system', 'seed_load', 'site_model', 'site_seed_001',
    '{"reason":"integration test fixture"}'::jsonb, 'mcp_seed_root'
);
