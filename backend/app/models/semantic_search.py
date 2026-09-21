"""Persistent state for the rebuildable semantic-search projection."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class SemanticProviderDefinition(Base):
    __tablename__ = "semantic_provider_definitions"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    provider_kind = Column(String(30), nullable=False, index=True)
    provider_type = Column(String(60), nullable=False)
    endpoint = Column(String(1000))
    credential_ref = Column(String(500))
    config_json = Column(JSON, default=dict, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    last_health_status = Column(String(30))
    last_health_at = Column(DateTime)
    last_error_code = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SemanticSearchProfile(Base):
    __tablename__ = "semantic_search_profiles"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    is_default = Column(Boolean, default=False, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    vector_backend = Column(String(60), default="zvec", nullable=False)
    embedding_provider_id = Column(Integer, ForeignKey("semantic_provider_definitions.id"))
    embedding_model = Column(String(200), default="text-embedding-3-small")
    embedding_dimensions = Column(Integer)
    rerank_provider_id = Column(Integer, ForeignKey("semantic_provider_definitions.id"))
    rerank_model = Column(String(200))
    rerank_enabled = Column(Boolean, default=False, nullable=False)
    rerank_top_n = Column(Integer, default=20, nullable=False)
    quality_gate_enabled = Column(Boolean, default=False, nullable=False)
    quality_thresholds = Column(JSON, default=dict, nullable=False)
    retrieval_mode = Column(String(20), default="hybrid", nullable=False)
    keyword_weight = Column(Integer, default=1, nullable=False)
    vector_weight = Column(Integer, default=1, nullable=False)
    rrf_k = Column(Integer, default=60, nullable=False)
    keyword_candidate_count = Column(Integer, default=100, nullable=False)
    vector_candidate_count = Column(Integer, default=100, nullable=False)
    result_top_k = Column(Integer, default=20, nullable=False)
    template_version = Column(String(60), default="patent-summary-v1", nullable=False)
    chunk_strategy_version = Column(String(60), default="summary-v1", nullable=False)
    distance_metric = Column(String(30), default="cosine", nullable=False)
    indexed_field_allowlist = Column(JSON, default=list, nullable=False)
    remote_field_allowlist = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SemanticIndex(Base):
    __tablename__ = "semantic_indexes"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("semantic_search_profiles.id"), nullable=False, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id"), index=True)
    index_version = Column(String(100), nullable=False, unique=True)
    backend_type = Column(String(60), nullable=False)
    path = Column(String(1000), nullable=False)
    status = Column(String(30), default="building", nullable=False, index=True)
    is_active = Column(Boolean, default=False, nullable=False, index=True)
    document_count = Column(Integer, default=0, nullable=False)
    patent_count = Column(Integer, default=0, nullable=False)
    source_watermark = Column(String(100))
    manifest_hash = Column(String(128))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    activated_at = Column(DateTime)
    last_error_code = Column(String(100))
    last_error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class SemanticIndexJob(Base):
    __tablename__ = "semantic_index_jobs"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("semantic_search_profiles.id"), nullable=False, index=True)
    index_id = Column(Integer, ForeignKey("semantic_indexes.id"), index=True)
    job_type = Column(String(30), nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    total_items = Column(Integer, default=0, nullable=False)
    processed_items = Column(Integer, default=0, nullable=False)
    failed_items = Column(Integer, default=0, nullable=False)
    skipped_items = Column(Integer, default=0, nullable=False)
    attempt_count = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    next_retry_at = Column(DateTime)
    lease_owner = Column(String(100))
    lease_expires_at = Column(DateTime)
    checkpoint_json = Column(JSON, default=dict, nullable=False)
    error_code = Column(String(100))
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime)
    finished_at = Column(DateTime)


class SemanticDocumentState(Base):
    __tablename__ = "semantic_document_states"
    __table_args__ = (UniqueConstraint("profile_id", "index_version", "document_id", name="uq_semantic_document_state"),)

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("semantic_search_profiles.id"), nullable=False, index=True)
    index_version = Column(String(100), nullable=False, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id"), nullable=False, index=True)
    document_type = Column(String(60), nullable=False)
    document_id = Column(String(200), nullable=False)
    content_hash = Column(String(128), nullable=False)
    indexed_hash = Column(String(128))
    status = Column(String(30), default="pending", nullable=False, index=True)
    chunk_count = Column(Integer, default=1, nullable=False)
    last_indexed_at = Column(DateTime)
    last_error_code = Column(String(100))
    last_error_message = Column(Text)


class SemanticIndexOutbox(Base):
    __tablename__ = "semantic_index_outbox"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_semantic_outbox_dedupe"),)

    id = Column(Integer, primary_key=True)
    operation = Column(String(20), nullable=False)
    patent_id = Column(Integer, ForeignKey("patents.id"), nullable=False, index=True)
    reason = Column(String(200), nullable=False)
    source_event_type = Column(String(100))
    source_event_id = Column(String(100))
    dedupe_key = Column(String(200), nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime)
    lease_owner = Column(String(100))
    lease_expires_at = Column(DateTime)
    last_error_code = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime)


class SemanticSearchLog(Base):
    __tablename__ = "semantic_search_logs"

    id = Column(Integer, primary_key=True)
    query_hash = Column(String(128), nullable=False, index=True)
    database_id = Column(Integer, index=True)
    profile_id = Column(Integer, ForeignKey("semantic_search_profiles.id"))
    index_version = Column(String(100))
    mode = Column(String(20), nullable=False)
    degraded_reasons = Column(JSON, default=list, nullable=False)
    candidate_count = Column(Integer, default=0, nullable=False)
    result_count = Column(Integer, default=0, nullable=False)
    latency_ms = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class SemanticEvaluationDataset(Base):
    __tablename__ = "semantic_evaluation_datasets"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_semantic_evaluation_dataset"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    version = Column(String(60), nullable=False)
    description = Column(Text)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class SemanticEvaluationCase(Base):
    __tablename__ = "semantic_evaluation_cases"
    __table_args__ = (UniqueConstraint("dataset_id", "case_key", name="uq_semantic_evaluation_case"),)

    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("semantic_evaluation_datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    case_key = Column(String(100), nullable=False)
    query = Column(Text, nullable=False)
    database_id = Column(Integer, ForeignKey("patent_databases.id"), index=True)
    relevant_patent_ids = Column(JSON, default=list, nullable=False)
    notes = Column(Text)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class SemanticEvaluationRun(Base):
    __tablename__ = "semantic_evaluation_runs"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("semantic_evaluation_datasets.id"), nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("semantic_search_profiles.id"), nullable=False, index=True)
    index_version = Column(String(100))
    mode = Column(String(20), nullable=False)
    top_k = Column(Integer, nullable=False)
    status = Column(String(30), default="running", nullable=False, index=True)
    metrics_json = Column(JSON, default=dict, nullable=False)
    threshold_json = Column(JSON, default=dict, nullable=False)
    error_code = Column(String(100))
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime)


class SemanticEvaluationResult(Base):
    __tablename__ = "semantic_evaluation_results"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("semantic_evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("semantic_evaluation_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    retrieved_patent_ids = Column(JSON, default=list, nullable=False)
    metrics_json = Column(JSON, default=dict, nullable=False)
    latency_ms = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
