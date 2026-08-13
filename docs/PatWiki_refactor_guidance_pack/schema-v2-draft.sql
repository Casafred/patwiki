-- PatWiki Schema V2 — conceptual draft for technical review
-- IMPORTANT: This is NOT a production migration.
-- Adapt types/FKs/naming to the repository's SQLAlchemy + Alembic conventions.

PRAGMA foreign_keys = ON;

-- =========================================================
-- Product / taxonomy
-- =========================================================

CREATE TABLE IF NOT EXISTS product_categories (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE,
    name TEXT NOT NULL,
    parent_id INTEGER,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(parent_id) REFERENCES product_categories(id)
);

CREATE TABLE IF NOT EXISTS department_product_line_links (
    id INTEGER PRIMARY KEY,
    department_id INTEGER NOT NULL,
    product_line_id INTEGER NOT NULL,
    role TEXT DEFAULT 'covered',
    is_primary INTEGER NOT NULL DEFAULT 0,
    valid_from DATETIME,
    valid_to DATETIME,
    created_at DATETIME NOT NULL,
    UNIQUE(department_id, product_line_id, role)
);

CREATE TABLE IF NOT EXISTS product_line_category_links (
    id INTEGER PRIMARY KEY,
    product_line_id INTEGER NOT NULL,
    product_category_id INTEGER NOT NULL,
    emphasis_level TEXT,
    created_at DATETIME NOT NULL,
    UNIQUE(product_line_id, product_category_id),
    FOREIGN KEY(product_category_id) REFERENCES product_categories(id)
);

CREATE TABLE IF NOT EXISTS technical_features (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE,
    name TEXT NOT NULL,
    parent_id INTEGER,
    feature_type TEXT,
    description TEXT,
    taxonomy_version TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(parent_id) REFERENCES technical_features(id)
);

-- =========================================================
-- Project solution versions
-- =========================================================

CREATE TABLE IF NOT EXISTS project_solution_versions (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    name TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    project_stage TEXT,
    effective_from DATETIME,
    effective_to DATETIME,
    source_solution_version_id INTEGER,
    inherited_product_id INTEGER,
    change_summary TEXT,
    change_reason TEXT,
    confirmed_by INTEGER,
    confirmed_at DATETIME,
    provenance TEXT DEFAULT 'internal_confirmed',
    confidence REAL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE(project_id, version_no),
    FOREIGN KEY(source_solution_version_id) REFERENCES project_solution_versions(id)
);

CREATE TABLE IF NOT EXISTS solution_feature_links (
    id INTEGER PRIMARY KEY,
    solution_version_id INTEGER NOT NULL,
    technical_feature_id INTEGER NOT NULL,
    change_type TEXT, -- inherited/added/modified/removed
    importance TEXT,
    source TEXT,
    confirmed_by INTEGER,
    confirmed_at DATETIME,
    note TEXT,
    created_at DATETIME NOT NULL,
    UNIQUE(solution_version_id, technical_feature_id, change_type),
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id),
    FOREIGN KEY(technical_feature_id) REFERENCES technical_features(id)
);

-- =========================================================
-- Patent family / legal status extensions
-- Assumes existing patents table is PatentDocument-like.
-- =========================================================

CREATE TABLE IF NOT EXISTS legal_status_events (
    id INTEGER PRIMARY KEY,
    patent_id INTEGER NOT NULL,
    jurisdiction TEXT,
    event_code TEXT,
    raw_status TEXT,
    normalized_status TEXT,
    effective_date DATE,
    source_system TEXT NOT NULL,
    source_timestamp DATETIME NOT NULL,
    source_reference TEXT,
    payload_hash TEXT,
    created_at DATETIME NOT NULL,
    UNIQUE(patent_id, event_code, effective_date, payload_hash)
);

CREATE TABLE IF NOT EXISTS family_relations (
    id INTEGER PRIMARY KEY,
    parent_patent_id INTEGER NOT NULL,
    child_patent_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL, -- divisional/continuation/CIP/PCT/national_phase/etc
    source_system TEXT,
    source_timestamp DATETIME,
    created_at DATETIME NOT NULL,
    UNIQUE(parent_patent_id, child_patent_id, relation_type)
);

-- =========================================================
-- Search
-- =========================================================

CREATE TABLE IF NOT EXISTS search_cases (
    id INTEGER PRIMARY KEY,
    tc_no TEXT UNIQUE,
    purpose TEXT NOT NULL,
    project_id INTEGER,
    solution_version_id INTEGER,
    owner_id INTEGER,
    status TEXT NOT NULL DEFAULT 'draft',
    scope_json JSON,
    region_scope_json JSON,
    background TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    completed_at DATETIME,
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id)
);

CREATE TABLE IF NOT EXISTS search_queries (
    id INTEGER PRIMARY KEY,
    search_case_id INTEGER NOT NULL,
    query_text TEXT NOT NULL,
    database_platform TEXT,
    search_fields TEXT,
    strategy_note TEXT,
    filter_strategy TEXT,
    created_by INTEGER,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(search_case_id) REFERENCES search_cases(id)
);

CREATE TABLE IF NOT EXISTS search_query_runs (
    id INTEGER PRIMARY KEY,
    search_query_id INTEGER NOT NULL,
    run_at DATETIME NOT NULL,
    source_version TEXT,
    result_count INTEGER,
    result_hash TEXT,
    elapsed_ms INTEGER,
    status TEXT,
    error_message TEXT,
    FOREIGN KEY(search_query_id) REFERENCES search_queries(id)
);

CREATE TABLE IF NOT EXISTS search_hits (
    id INTEGER PRIMARY KEY,
    search_case_id INTEGER NOT NULL,
    query_run_id INTEGER,
    patent_id INTEGER NOT NULL,
    rank_no INTEGER,
    matched_concepts_json JSON,
    created_at DATETIME NOT NULL,
    UNIQUE(search_case_id, patent_id, query_run_id),
    FOREIGN KEY(search_case_id) REFERENCES search_cases(id),
    FOREIGN KEY(query_run_id) REFERENCES search_query_runs(id)
);

CREATE TABLE IF NOT EXISTS relevance_reviews (
    id INTEGER PRIMARY KEY,
    search_case_id INTEGER NOT NULL,
    patent_id INTEGER NOT NULL,
    solution_version_id INTEGER,
    relevance_level TEXT,
    relevance_score REAL,
    review_note TEXT,
    reviewer_id INTEGER,
    reviewed_at DATETIME,
    provenance TEXT,
    status TEXT DEFAULT 'confirmed',
    created_at DATETIME NOT NULL,
    FOREIGN KEY(search_case_id) REFERENCES search_cases(id),
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id)
);

-- =========================================================
-- Risk
-- =========================================================

CREATE TABLE IF NOT EXISTS risk_cases (
    id INTEGER PRIMARY KEY,
    risk_no TEXT UNIQUE,
    title TEXT NOT NULL,
    risk_subject TEXT,
    discovery_reason TEXT,
    discovered_at DATETIME,
    discovered_by INTEGER,
    owner_id INTEGER,
    current_status TEXT NOT NULL DEFAULT 'identified',
    current_risk_level TEXT,
    current_assessment_id INTEGER,
    closed_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_patent_links (
    id INTEGER PRIMARY KEY,
    risk_case_id INTEGER NOT NULL,
    patent_id INTEGER NOT NULL,
    role TEXT DEFAULT 'primary',
    jurisdiction TEXT,
    watch_priority TEXT,
    source TEXT,
    created_at DATETIME NOT NULL,
    UNIQUE(risk_case_id, patent_id, role),
    FOREIGN KEY(risk_case_id) REFERENCES risk_cases(id)
);

CREATE TABLE IF NOT EXISTS risk_solution_links (
    id INTEGER PRIMARY KEY,
    risk_case_id INTEGER NOT NULL,
    solution_version_id INTEGER NOT NULL,
    relationship TEXT DEFAULT 'affected',
    adoption_status TEXT,
    mitigation_status TEXT,
    created_at DATETIME NOT NULL,
    UNIQUE(risk_case_id, solution_version_id, relationship),
    FOREIGN KEY(risk_case_id) REFERENCES risk_cases(id),
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id)
);

CREATE TABLE IF NOT EXISTS risk_assessment_versions (
    id INTEGER PRIMARY KEY,
    risk_case_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    solution_version_id INTEGER,
    jurisdiction TEXT,
    patent_claim_version TEXT,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft', -- draft/confirmed/outdated/superseded
    conflict_status TEXT, -- yes/no/uncertain
    risk_level TEXT,
    conclusion TEXT,
    rationale TEXT,
    assessed_by INTEGER,
    assessed_at DATETIME,
    confirmed_by INTEGER,
    confirmed_at DATETIME,
    supersedes_id INTEGER,
    created_at DATETIME NOT NULL,
    UNIQUE(risk_case_id, version_no),
    FOREIGN KEY(risk_case_id) REFERENCES risk_cases(id),
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id),
    FOREIGN KEY(supersedes_id) REFERENCES risk_assessment_versions(id)
);

CREATE TABLE IF NOT EXISTS claim_element_analyses (
    id INTEGER PRIMARY KEY,
    assessment_id INTEGER NOT NULL,
    patent_id INTEGER NOT NULL,
    claim_no TEXT NOT NULL,
    element_no INTEGER,
    claim_text TEXT,
    translation TEXT,
    interpretation TEXT,
    solution_feature_id INTEGER,
    match_status TEXT,
    rationale TEXT,
    evidence_artifact_id INTEGER,
    prior_art_patent_id INTEGER,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(assessment_id) REFERENCES risk_assessment_versions(id),
    FOREIGN KEY(solution_feature_id) REFERENCES technical_features(id)
);

CREATE TABLE IF NOT EXISTS mitigation_plans (
    id INTEGER PRIMARY KEY,
    risk_case_id INTEGER NOT NULL,
    solution_version_id INTEGER,
    title TEXT,
    description TEXT,
    current_status TEXT,
    owner_id INTEGER,
    due_at DATETIME,
    verification_summary TEXT,
    verified_by INTEGER,
    verified_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(risk_case_id) REFERENCES risk_cases(id)
);

CREATE TABLE IF NOT EXISTS risk_decisions (
    id INTEGER PRIMARY KEY,
    risk_case_id INTEGER NOT NULL,
    decision_type TEXT NOT NULL,
    decision_at DATETIME NOT NULL,
    decision_maker_id INTEGER NOT NULL,
    conclusion TEXT NOT NULL,
    accepted_risk_level TEXT,
    required_actions_json JSON,
    conditions TEXT,
    review_at DATETIME,
    supersedes_decision_id INTEGER,
    created_by INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(risk_case_id) REFERENCES risk_cases(id),
    FOREIGN KEY(supersedes_decision_id) REFERENCES risk_decisions(id)
);

CREATE TABLE IF NOT EXISTS risk_watch_events (
    id INTEGER PRIMARY KEY,
    risk_case_id INTEGER NOT NULL,
    patent_id INTEGER,
    solution_version_id INTEGER,
    trigger_type TEXT NOT NULL,
    source_event_ref TEXT,
    impact_level TEXT,
    requires_reassessment INTEGER NOT NULL DEFAULT 0,
    processed_at DATETIME,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(risk_case_id) REFERENCES risk_cases(id)
);

-- =========================================================
-- Protection / filing
-- =========================================================

CREATE TABLE IF NOT EXISTS protection_cases (
    id INTEGER PRIMARY KEY,
    protection_no TEXT UNIQUE,
    title TEXT NOT NULL,
    invention_theme TEXT,
    protection_scope_strategy TEXT,
    business_importance TEXT,
    owner_id INTEGER,
    status TEXT NOT NULL DEFAULT 'idea',
    approved_by INTEGER,
    approved_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS protection_solution_links (
    id INTEGER PRIMARY KEY,
    protection_case_id INTEGER NOT NULL,
    solution_version_id INTEGER NOT NULL,
    role TEXT DEFAULT 'source',
    created_at DATETIME NOT NULL,
    UNIQUE(protection_case_id, solution_version_id, role),
    FOREIGN KEY(protection_case_id) REFERENCES protection_cases(id),
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id)
);

CREATE TABLE IF NOT EXISTS filing_cases (
    id INTEGER PRIMARY KEY,
    protection_case_id INTEGER NOT NULL,
    internal_docket_no TEXT UNIQUE,
    jurisdiction TEXT NOT NULL,
    filing_route TEXT,
    filing_type TEXT,
    patent_id INTEGER,
    application_no TEXT,
    publication_no TEXT,
    agency_id INTEGER,
    internal_owner_id INTEGER,
    current_status TEXT,
    filing_date DATE,
    target_filing_date DATE,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(protection_case_id) REFERENCES protection_cases(id)
);

-- =========================================================
-- Artifact
-- =========================================================

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    title TEXT,
    description TEXT,
    storage_uri TEXT,
    external_url TEXT,
    content_hash TEXT,
    mime_type TEXT,
    file_size INTEGER,
    sensitivity TEXT NOT NULL DEFAULT 'internal',
    owner_id INTEGER,
    source TEXT,
    captured_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_links (
    id INTEGER PRIMARY KEY,
    artifact_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    role TEXT,
    created_by INTEGER,
    created_at DATETIME NOT NULL,
    UNIQUE(artifact_id, entity_type, entity_id, role),
    FOREIGN KEY(artifact_id) REFERENCES artifacts(id)
);

-- =========================================================
-- Audit / AI / snapshot
-- =========================================================

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    field_key TEXT,
    old_value_json JSON,
    new_value_json JSON,
    actor_id INTEGER,
    acting_role TEXT,
    source TEXT,
    source_view_id INTEGER,
    reason TEXT,
    request_id TEXT,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_entity
ON audit_events(entity_type, entity_id, created_at);

CREATE TABLE IF NOT EXISTS ai_executions (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,
    field_key TEXT,
    model_provider TEXT,
    model_name TEXT NOT NULL,
    model_version TEXT,
    prompt_template_id TEXT,
    prompt_version TEXT,
    input_hash TEXT NOT NULL,
    input_refs_json JSON,
    output_json JSON,
    output_schema_version TEXT,
    confidence REAL,
    latency_ms INTEGER,
    token_count INTEGER,
    cost REAL,
    review_status TEXT NOT NULL DEFAULT 'pending',
    reviewer_id INTEGER,
    reviewed_at DATETIME,
    superseded_by INTEGER,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(superseded_by) REFERENCES ai_executions(id)
);

CREATE TABLE IF NOT EXISTS report_snapshots (
    id INTEGER PRIMARY KEY,
    report_type TEXT NOT NULL,
    reporting_period TEXT,
    source_dataset TEXT,
    source_revision TEXT,
    checksum TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    sensitivity TEXT DEFAULT 'internal',
    generated_by INTEGER,
    generated_at DATETIME NOT NULL,
    reviewed_by INTEGER,
    reviewed_at DATETIME,
    published_at DATETIME
);

CREATE TABLE IF NOT EXISTS report_snapshot_items (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL,
    source_entity_type TEXT NOT NULL,
    source_entity_id INTEGER NOT NULL,
    source_revision TEXT,
    rendered_values_json JSON,
    FOREIGN KEY(snapshot_id) REFERENCES report_snapshots(id)
);

-- =========================================================
-- Suggested indexes (review against actual queries)
-- =========================================================

CREATE INDEX IF NOT EXISTS ix_solution_project
ON project_solution_versions(project_id, version_no);

CREATE INDEX IF NOT EXISTS ix_risk_status_level
ON risk_cases(current_status, current_risk_level);

CREATE INDEX IF NOT EXISTS ix_assessment_risk_status
ON risk_assessment_versions(risk_case_id, status, assessed_at);

CREATE INDEX IF NOT EXISTS ix_watch_reassessment
ON risk_watch_events(requires_reassessment, created_at);

CREATE INDEX IF NOT EXISTS ix_search_hit_patent
ON search_hits(patent_id, search_case_id);

CREATE INDEX IF NOT EXISTS ix_artifact_link_entity
ON artifact_links(entity_type, entity_id);
