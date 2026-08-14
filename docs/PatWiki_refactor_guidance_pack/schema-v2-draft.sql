-- PatWiki Schema V2 — conceptual draft for technical review
-- IMPORTANT: This is NOT a production migration.
-- Read 21-implementation-contract.md and
-- 24-patent-information-hub-functional-spec.md before implementation.
-- Adapt types/FKs/naming to this repository's SQLAlchemy + versioned migration
-- conventions. The current physical `patents` table remains the compatible
-- PatentDocument target; do not rename or execute this file against production.
-- Every workspace-scoped V2 Case, Artifact, AI execution, and report snapshot
-- should carry database_id. `database_id` supports query/workspace ownership
-- and is NOT an authentication boundary in the current app. Shared taxonomy
-- and child/event rows inherit scope from their aggregate root.

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

CREATE TABLE IF NOT EXISTS product_category_links (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL,
    product_category_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'primary', -- primary/secondary
    created_at DATETIME NOT NULL,
    UNIQUE(product_id, product_category_id, role),
    FOREIGN KEY(product_id) REFERENCES products(id),
    FOREIGN KEY(product_category_id) REFERENCES product_categories(id)
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
    UNIQUE(department_id, product_line_id, role),
    FOREIGN KEY(department_id) REFERENCES departments(id),
    FOREIGN KEY(product_line_id) REFERENCES product_lines(id)
);

CREATE TABLE IF NOT EXISTS product_line_category_links (
    id INTEGER PRIMARY KEY,
    product_line_id INTEGER NOT NULL,
    product_category_id INTEGER NOT NULL,
    emphasis_level TEXT,
    created_at DATETIME NOT NULL,
    UNIQUE(product_line_id, product_category_id),
    FOREIGN KEY(product_line_id) REFERENCES product_lines(id),
    FOREIGN KEY(product_category_id) REFERENCES product_categories(id)
);

CREATE TABLE IF NOT EXISTS technical_features (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE,
    name TEXT NOT NULL,
    feature_type TEXT,
    description TEXT,
    taxonomy_version TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS taxonomy_edges (
    id INTEGER PRIMARY KEY,
    parent_feature_id INTEGER NOT NULL,
    child_feature_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'broader', -- broader/related/equivalent
    valid_from DATETIME,
    valid_to DATETIME,
    created_at DATETIME NOT NULL,
    UNIQUE(parent_feature_id, child_feature_id, relation_type),
    FOREIGN KEY(parent_feature_id) REFERENCES technical_features(id),
    FOREIGN KEY(child_feature_id) REFERENCES technical_features(id)
);

-- =========================================================
-- Project solution versions
-- =========================================================

CREATE TABLE IF NOT EXISTS project_solution_versions (
    id INTEGER PRIMARY KEY,
    database_id INTEGER NOT NULL,
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
    FOREIGN KEY(database_id) REFERENCES patent_databases(id),
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(source_solution_version_id) REFERENCES project_solution_versions(id),
    FOREIGN KEY(inherited_product_id) REFERENCES products(id),
    FOREIGN KEY(confirmed_by) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS project_region_links (
    id INTEGER PRIMARY KEY,
    database_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    jurisdiction_code TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'target', -- target/current/sales/manufacturing
    source TEXT,
    confirmed_by INTEGER,
    confirmed_at DATETIME,
    created_at DATETIME NOT NULL,
    UNIQUE(project_id, jurisdiction_code, role),
    FOREIGN KEY(database_id) REFERENCES patent_databases(id),
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(confirmed_by) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS solution_version_region_links (
    id INTEGER PRIMARY KEY,
    solution_version_id INTEGER NOT NULL,
    jurisdiction_code TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'target', -- target/sales/manufacturing/review
    source TEXT,
    confirmed_by INTEGER,
    confirmed_at DATETIME,
    created_at DATETIME NOT NULL,
    UNIQUE(solution_version_id, jurisdiction_code, role),
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id),
    FOREIGN KEY(confirmed_by) REFERENCES people(id)
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
    FOREIGN KEY(technical_feature_id) REFERENCES technical_features(id),
    FOREIGN KEY(confirmed_by) REFERENCES people(id)
);

-- =========================================================
-- Patent family / legal status extensions
-- Assumes existing patents table is PatentDocument-like.
-- =========================================================

CREATE TABLE IF NOT EXISTS patent_identifiers (
    id INTEGER PRIMARY KEY,
    patent_id INTEGER NOT NULL,
    identifier_namespace TEXT NOT NULL DEFAULT 'official', -- official/source system
    identifier_type TEXT NOT NULL, -- application/publication/grant/external
    raw_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    jurisdiction_code TEXT,
    kind_code TEXT,
    source_system TEXT,
    source_timestamp DATETIME,
    is_primary INTEGER NOT NULL DEFAULT 0,
    valid_from DATETIME,
    valid_to DATETIME,
    created_at DATETIME NOT NULL,
    UNIQUE(identifier_namespace, identifier_type, normalized_value),
    FOREIGN KEY(patent_id) REFERENCES patents(id)
);

CREATE TABLE IF NOT EXISTS import_batch_sources (
    id INTEGER PRIMARY KEY,
    import_batch_id INTEGER NOT NULL UNIQUE,
    workbook_filename TEXT NOT NULL,
    source_table_title TEXT NOT NULL,
    worksheet_name TEXT,
    source_system TEXT,
    mapping_version TEXT NOT NULL,
    source_exported_at DATETIME,
    file_hash TEXT NOT NULL,
    source_artifact_id INTEGER,
    imported_at DATETIME NOT NULL,
    FOREIGN KEY(import_batch_id) REFERENCES import_batches(id),
    FOREIGN KEY(source_artifact_id) REFERENCES artifacts(id)
);

CREATE TABLE IF NOT EXISTS import_source_rows (
    id INTEGER PRIMARY KEY,
    import_batch_id INTEGER NOT NULL,
    source_row INTEGER NOT NULL,
    source_record_key TEXT,
    raw_row_json JSON NOT NULL,
    row_hash TEXT,
    resolution_status TEXT NOT NULL DEFAULT 'unmapped_retained', -- resolved/unmapped_retained/quarantined
    resolved_patent_id INTEGER,
    created_at DATETIME NOT NULL,
    UNIQUE(import_batch_id, source_row),
    FOREIGN KEY(import_batch_id) REFERENCES import_batches(id),
    FOREIGN KEY(resolved_patent_id) REFERENCES patents(id)
);

CREATE TABLE IF NOT EXISTS patent_import_events (
    id INTEGER PRIMARY KEY,
    patent_id INTEGER NOT NULL,
    import_batch_id INTEGER NOT NULL,
    source_row_id INTEGER NOT NULL,
    source_row INTEGER NOT NULL,
    source_record_key TEXT,
    matched_identifier_id INTEGER,
    match_method TEXT NOT NULL, -- exact/candidate/created/manual
    result TEXT NOT NULL, -- created/matched/partial/conflict/quarantined
    observed_field_count INTEGER NOT NULL DEFAULT 0,
    added_count INTEGER NOT NULL DEFAULT 0,
    same_count INTEGER NOT NULL DEFAULT 0,
    format_diff_count INTEGER NOT NULL DEFAULT 0,
    conflict_count INTEGER NOT NULL DEFAULT 0,
    review_status TEXT NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL,
    UNIQUE(import_batch_id, source_row, patent_id),
    FOREIGN KEY(patent_id) REFERENCES patents(id),
    FOREIGN KEY(import_batch_id) REFERENCES import_batches(id),
    FOREIGN KEY(source_row_id) REFERENCES import_source_rows(id),
    FOREIGN KEY(matched_identifier_id) REFERENCES patent_identifiers(id)
);

CREATE TABLE IF NOT EXISTS field_observations (
    id INTEGER PRIMARY KEY,
    patent_import_event_id INTEGER,
    import_source_row_id INTEGER NOT NULL,
    source_field_name TEXT NOT NULL,
    source_column_index INTEGER,
    canonical_field_key TEXT,
    field_resolution TEXT NOT NULL DEFAULT 'unmapped_retained', -- mapped/candidate/unmapped_retained/quarantined
    value_index INTEGER NOT NULL DEFAULT 0,
    raw_value TEXT,
    normalized_value TEXT,
    adopted_value_before TEXT,
    candidate_value TEXT,
    adopted_value_after TEXT,
    difference_type TEXT NOT NULL, -- new/same/format/content/identity/protected/unknown
    proposed_action TEXT NOT NULL, -- fill/append/keep/version/retain/map/block
    final_decision TEXT,
    decided_by INTEGER,
    decided_at DATETIME,
    created_at DATETIME NOT NULL,
    UNIQUE(import_source_row_id, source_field_name, value_index),
    FOREIGN KEY(patent_import_event_id) REFERENCES patent_import_events(id),
    FOREIGN KEY(import_source_row_id) REFERENCES import_source_rows(id),
    FOREIGN KEY(decided_by) REFERENCES people(id)
);

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
    UNIQUE(patent_id, event_code, effective_date, payload_hash),
    FOREIGN KEY(patent_id) REFERENCES patents(id)
);

CREATE TABLE IF NOT EXISTS family_relations (
    id INTEGER PRIMARY KEY,
    parent_patent_id INTEGER NOT NULL,
    child_patent_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL, -- divisional/continuation/CIP/PCT/national_phase/etc
    source_system TEXT,
    source_timestamp DATETIME,
    created_at DATETIME NOT NULL,
    UNIQUE(parent_patent_id, child_patent_id, relation_type),
    FOREIGN KEY(parent_patent_id) REFERENCES patents(id),
    FOREIGN KEY(child_patent_id) REFERENCES patents(id)
);

-- =========================================================
-- Search
-- =========================================================

CREATE TABLE IF NOT EXISTS search_cases (
    id INTEGER PRIMARY KEY,
    database_id INTEGER NOT NULL,
    tc_no TEXT UNIQUE,
    purpose TEXT NOT NULL,
    project_id INTEGER,
    solution_version_id INTEGER,
    owner_id INTEGER,
    status TEXT NOT NULL DEFAULT 'draft',
    scope_note TEXT,
    background TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    completed_at DATETIME,
    FOREIGN KEY(database_id) REFERENCES patent_databases(id),
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id),
    FOREIGN KEY(owner_id) REFERENCES people(id)
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
    FOREIGN KEY(search_case_id) REFERENCES search_cases(id),
    FOREIGN KEY(created_by) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS search_concepts (
    id INTEGER PRIMARY KEY,
    search_case_id INTEGER NOT NULL,
    technical_feature_id INTEGER,
    concept_text TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'required', -- required/optional/excluded/synonym
    source TEXT,
    created_by INTEGER,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(search_case_id) REFERENCES search_cases(id),
    FOREIGN KEY(technical_feature_id) REFERENCES technical_features(id),
    FOREIGN KEY(created_by) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS search_query_runs (
    id INTEGER PRIMARY KEY,
    search_query_id INTEGER NOT NULL,
    operator_id INTEGER,
    run_at DATETIME NOT NULL,
    input_scope_json JSON, -- query parameters, never arrays of relational IDs
    source_version TEXT,
    result_count INTEGER,
    result_hash TEXT,
    elapsed_ms INTEGER,
    status TEXT,
    error_message TEXT,
    result_artifact_id INTEGER,
    FOREIGN KEY(search_query_id) REFERENCES search_queries(id),
    FOREIGN KEY(operator_id) REFERENCES people(id),
    FOREIGN KEY(result_artifact_id) REFERENCES artifacts(id)
);

CREATE TABLE IF NOT EXISTS search_hits (
    id INTEGER PRIMARY KEY,
    search_case_id INTEGER NOT NULL,
    query_run_id INTEGER,
    patent_id INTEGER NOT NULL,
    rank_no INTEGER,
    created_at DATETIME NOT NULL,
    UNIQUE(search_case_id, patent_id, query_run_id),
    FOREIGN KEY(search_case_id) REFERENCES search_cases(id),
    FOREIGN KEY(query_run_id) REFERENCES search_query_runs(id),
    FOREIGN KEY(patent_id) REFERENCES patents(id)
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
    FOREIGN KEY(patent_id) REFERENCES patents(id),
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id),
    FOREIGN KEY(reviewer_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS search_hit_concept_links (
    id INTEGER PRIMARY KEY,
    search_hit_id INTEGER NOT NULL,
    search_concept_id INTEGER NOT NULL,
    match_kind TEXT,
    created_at DATETIME NOT NULL,
    UNIQUE(search_hit_id, search_concept_id),
    FOREIGN KEY(search_hit_id) REFERENCES search_hits(id),
    FOREIGN KEY(search_concept_id) REFERENCES search_concepts(id)
);

-- =========================================================
-- Risk
-- =========================================================

CREATE TABLE IF NOT EXISTS risk_cases (
    id INTEGER PRIMARY KEY,
    database_id INTEGER NOT NULL,
    risk_no TEXT UNIQUE,
    title TEXT NOT NULL,
    risk_subject TEXT,
    discovery_reason TEXT,
    discovered_at DATETIME,
    discovered_by INTEGER,
    owner_id INTEGER,
    source_system TEXT,
    source_reference TEXT,
    current_status TEXT NOT NULL DEFAULT 'identified',
    current_risk_level TEXT,
    current_assessment_id INTEGER,
    closed_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(database_id) REFERENCES patent_databases(id),
    FOREIGN KEY(discovered_by) REFERENCES people(id),
    FOREIGN KEY(owner_id) REFERENCES people(id),
    FOREIGN KEY(current_assessment_id) REFERENCES risk_assessment_versions(id)
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
    FOREIGN KEY(risk_case_id) REFERENCES risk_cases(id),
    FOREIGN KEY(patent_id) REFERENCES patents(id)
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
    primary_evidence_artifact_id INTEGER,
    supersedes_id INTEGER,
    created_at DATETIME NOT NULL,
    UNIQUE(risk_case_id, version_no),
    FOREIGN KEY(risk_case_id) REFERENCES risk_cases(id),
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id),
    FOREIGN KEY(assessed_by) REFERENCES people(id),
    FOREIGN KEY(confirmed_by) REFERENCES people(id),
    FOREIGN KEY(primary_evidence_artifact_id) REFERENCES artifacts(id),
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
    FOREIGN KEY(patent_id) REFERENCES patents(id),
    FOREIGN KEY(solution_feature_id) REFERENCES technical_features(id),
    FOREIGN KEY(evidence_artifact_id) REFERENCES artifacts(id),
    FOREIGN KEY(prior_art_patent_id) REFERENCES patents(id)
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
    FOREIGN KEY(risk_case_id) REFERENCES risk_cases(id),
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id),
    FOREIGN KEY(owner_id) REFERENCES people(id),
    FOREIGN KEY(verified_by) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS risk_decisions (
    id INTEGER PRIMARY KEY,
    risk_case_id INTEGER NOT NULL,
    decision_type TEXT NOT NULL,
    decision_at DATETIME NOT NULL,
    decision_maker_id INTEGER NOT NULL,
    conclusion TEXT NOT NULL,
    accepted_risk_level TEXT,
    conditions TEXT,
    review_at DATETIME,
    supersedes_decision_id INTEGER,
    created_by INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(risk_case_id) REFERENCES risk_cases(id),
    FOREIGN KEY(decision_maker_id) REFERENCES people(id),
    FOREIGN KEY(created_by) REFERENCES people(id),
    FOREIGN KEY(supersedes_decision_id) REFERENCES risk_decisions(id)
);

CREATE TABLE IF NOT EXISTS risk_decision_actions (
    id INTEGER PRIMARY KEY,
    risk_decision_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    description TEXT NOT NULL,
    owner_id INTEGER,
    due_at DATETIME,
    status TEXT NOT NULL DEFAULT 'open',
    completed_at DATETIME,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(risk_decision_id) REFERENCES risk_decisions(id),
    FOREIGN KEY(owner_id) REFERENCES people(id)
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
    FOREIGN KEY(risk_case_id) REFERENCES risk_cases(id),
    FOREIGN KEY(patent_id) REFERENCES patents(id),
    FOREIGN KEY(solution_version_id) REFERENCES project_solution_versions(id)
);

-- =========================================================
-- Protection / filing
-- =========================================================

CREATE TABLE IF NOT EXISTS protection_cases (
    id INTEGER PRIMARY KEY,
    database_id INTEGER NOT NULL,
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
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(database_id) REFERENCES patent_databases(id),
    FOREIGN KEY(owner_id) REFERENCES people(id),
    FOREIGN KEY(approved_by) REFERENCES people(id)
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
    FOREIGN KEY(protection_case_id) REFERENCES protection_cases(id),
    FOREIGN KEY(patent_id) REFERENCES patents(id),
    FOREIGN KEY(agency_id) REFERENCES people(id),
    FOREIGN KEY(internal_owner_id) REFERENCES people(id)
);

-- =========================================================
-- Artifact
-- =========================================================

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY,
    database_id INTEGER NOT NULL,
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
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(database_id) REFERENCES patent_databases(id),
    FOREIGN KEY(owner_id) REFERENCES people(id)
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
    FOREIGN KEY(artifact_id) REFERENCES artifacts(id),
    FOREIGN KEY(created_by) REFERENCES people(id)
);

-- =========================================================
-- Audit / AI / snapshot
-- =========================================================

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY,
    database_id INTEGER NOT NULL,
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
    created_at DATETIME NOT NULL,
    FOREIGN KEY(database_id) REFERENCES patent_databases(id),
    FOREIGN KEY(actor_id) REFERENCES people(id),
    FOREIGN KEY(source_view_id) REFERENCES patent_views(id)
);

CREATE INDEX IF NOT EXISTS ix_audit_entity
ON audit_events(entity_type, entity_id, created_at);

CREATE TABLE IF NOT EXISTS ai_executions (
    id INTEGER PRIMARY KEY,
    database_id INTEGER NOT NULL,
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
    FOREIGN KEY(database_id) REFERENCES patent_databases(id),
    FOREIGN KEY(reviewer_id) REFERENCES people(id),
    FOREIGN KEY(superseded_by) REFERENCES ai_executions(id)
);

CREATE TABLE IF NOT EXISTS report_snapshots (
    id INTEGER PRIMARY KEY,
    database_id INTEGER NOT NULL,
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
    published_at DATETIME,
    FOREIGN KEY(database_id) REFERENCES patent_databases(id),
    FOREIGN KEY(generated_by) REFERENCES people(id),
    FOREIGN KEY(reviewed_by) REFERENCES people(id)
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

CREATE TABLE IF NOT EXISTS artifact_versions (
    id INTEGER PRIMARY KEY,
    artifact_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    storage_uri TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER,
    captured_at DATETIME,
    created_by INTEGER,
    created_at DATETIME NOT NULL,
    UNIQUE(artifact_id, version_no),
    UNIQUE(artifact_id, content_hash),
    FOREIGN KEY(artifact_id) REFERENCES artifacts(id),
    FOREIGN KEY(created_by) REFERENCES people(id)
);

-- =========================================================
-- Suggested indexes (review against actual queries)
-- =========================================================

CREATE INDEX IF NOT EXISTS ix_solution_project
ON project_solution_versions(project_id, version_no);

CREATE INDEX IF NOT EXISTS ix_patent_identifier_patent
ON patent_identifiers(patent_id, identifier_type, is_primary);

CREATE INDEX IF NOT EXISTS ix_patent_import_history
ON patent_import_events(patent_id, created_at);

CREATE INDEX IF NOT EXISTS ix_import_source_row_resolution
ON import_source_rows(resolution_status, created_at);

CREATE INDEX IF NOT EXISTS ix_field_observation_review
ON field_observations(difference_type, final_decision, created_at);

CREATE INDEX IF NOT EXISTS ix_solution_database_project
ON project_solution_versions(database_id, project_id, status);

CREATE INDEX IF NOT EXISTS ix_search_case_database_status
ON search_cases(database_id, status, updated_at);

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

-- Constraint implementation notes:
-- 1. SQLite cannot express all state-machine rules here. Services enforce valid
--    transitions, confirmed assessment completeness, append-only decisions,
--    aggregate-level database_id consistency, and ArtifactLink's entity whitelist.
-- 2. Foreign keys to artifacts/risk assessments appear before those tables in
--    this conceptual file. The production migration order must create referenced
--    tables first (or add foreign keys during a later SQLite table rebuild).
-- 3. Every external identifier needs an idempotency/business-key constraint
--    defined from the actual source system before its import path is enabled.
