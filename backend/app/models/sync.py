"""External patent data synchronization models.

Provider evidence and synchronization state stay outside the canonical
Patent row. Only the sync service may apply accepted observations.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ConnectorDefinition(Base):
    __tablename__ = "connector_definitions"
    __table_args__ = (UniqueConstraint("code", name="uq_connector_definitions_code"),)

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    transport = Column(String(20), nullable=False, default="api")
    provider_type = Column(String(100), nullable=False, default="generic_json")
    endpoint = Column(String(1000))
    capabilities_json = Column(JSON, nullable=False, default=dict)
    config_json = Column(JSON, nullable=False, default=dict)
    mcp_catalog_json = Column(JSON, nullable=False, default=dict)
    mcp_catalog_updated_at = Column(DateTime)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    credentials = relationship("ConnectorCredential", back_populates="connector", cascade="all, delete-orphan")
    subscriptions = relationship("SyncSubscription", back_populates="connector")


class ConnectorCredential(Base):
    __tablename__ = "connector_credentials"

    id = Column(Integer, primary_key=True, index=True)
    connector_id = Column(Integer, ForeignKey("connector_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_ref = Column(String(500), nullable=False)
    credential_type = Column(String(50), nullable=False, default="api_key")
    label = Column(String(200))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    connector = relationship("ConnectorDefinition", back_populates="credentials")


class SavedPatentQuery(Base):
    __tablename__ = "saved_patent_queries"
    __table_args__ = (Index("ix_saved_patent_queries_database_enabled", "database_id", "enabled"),)

    id = Column(Integer, primary_key=True, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    query_json = Column(JSON, nullable=False, default=dict)
    query_version = Column(Integer, nullable=False, default=1)
    query_hash = Column(String(128), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class SyncSubscription(Base):
    __tablename__ = "sync_subscriptions"
    __table_args__ = (Index("ix_sync_subscriptions_due", "enabled", "next_run_at"),)

    id = Column(Integer, primary_key=True, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    connector_id = Column(Integer, ForeignKey("connector_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    saved_query_id = Column(Integer, ForeignKey("saved_patent_queries.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    mode = Column(String(30), nullable=False, default="query")
    scope_json = Column(JSON, nullable=False, default=dict)
    schedule_json = Column(JSON, nullable=False, default=dict)
    review_policy = Column(String(30), nullable=False, default="safe_auto_apply")
    enabled = Column(Boolean, nullable=False, default=True)
    next_run_at = Column(DateTime, index=True)
    last_run_at = Column(DateTime)
    last_status = Column(String(30))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    connector = relationship("ConnectorDefinition", back_populates="subscriptions")
    saved_query = relationship("SavedPatentQuery")
    cursor = relationship("SyncCursor", back_populates="subscription", uselist=False, cascade="all, delete-orphan")
    runs = relationship("SyncRun", back_populates="subscription", cascade="all, delete-orphan")


class SyncCursor(Base):
    __tablename__ = "sync_cursors"

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("sync_subscriptions.id", ondelete="CASCADE"), nullable=False, unique=True)
    cursor = Column(String(1000))
    watermark = Column(DateTime)
    overlap_seconds = Column(Integer, nullable=False, default=86400)
    provider_snapshot_version = Column(String(200))
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    subscription = relationship("SyncSubscription", back_populates="cursor")


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (Index("ix_sync_runs_subscription_created", "subscription_id", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("sync_subscriptions.id", ondelete="CASCADE"), nullable=True, index=True)
    connector_id = Column(Integer, ForeignKey("connector_definitions.id", ondelete="SET NULL"), nullable=False, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="SET NULL"), nullable=True, index=True)
    trigger = Column(String(30), nullable=False, default="manual")
    status = Column(String(30), nullable=False, default="queued", index=True)
    cursor_before = Column(String(1000))
    cursor_after = Column(String(1000))
    counts_json = Column(JSON, nullable=False, default=dict)
    rate_limit_json = Column(JSON)
    error_code = Column(String(100))
    error_message = Column(Text)
    retry_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    subscription = relationship("SyncSubscription", back_populates="runs")
    connector = relationship("ConnectorDefinition")
    snapshots = relationship("ExternalSnapshot", back_populates="run", cascade="all, delete-orphan")
    records = relationship("SyncRecord", back_populates="run", cascade="all, delete-orphan")
    observations = relationship("ExternalFactObservation", back_populates="run", cascade="all, delete-orphan")


class ExternalSnapshot(Base):
    __tablename__ = "external_snapshots"
    __table_args__ = (Index("ix_external_snapshots_connector_hash", "connector_id", "payload_hash"),)

    id = Column(Integer, primary_key=True, index=True)
    connector_id = Column(Integer, ForeignKey("connector_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    sync_run_id = Column(Integer, ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    request_metadata = Column(JSON, nullable=False, default=dict)
    payload_json = Column(JSON, nullable=False)
    payload_hash = Column(String(128), nullable=False, index=True)
    source_version = Column(String(200))
    fetched_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    connector = relationship("ConnectorDefinition")
    run = relationship("SyncRun", back_populates="snapshots")


class SyncRecord(Base):
    __tablename__ = "sync_records"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_sync_records_idempotency_key"),
        Index("ix_sync_records_run_outcome", "sync_run_id", "outcome"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sync_run_id = Column(Integer, ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    external_record_id = Column(String(500), nullable=False, index=True)
    record_kind = Column(String(40), nullable=False, default="patent")
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="SET NULL"), nullable=True, index=True)
    external_snapshot_id = Column(Integer, ForeignKey("external_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    identity_status = Column(String(40), nullable=False, default="unresolved")
    identity_candidate_patent_ids = Column(JSON, nullable=False, default=list)
    outcome = Column(String(40), nullable=False, default="pending")
    idempotency_key = Column(String(128), nullable=False)
    error_code = Column(String(100))
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    run = relationship("SyncRun", back_populates="records")
    snapshot = relationship("ExternalSnapshot")
    patent = relationship("Patent")


class ExternalFactObservation(Base):
    __tablename__ = "external_fact_observations"
    __table_args__ = (Index("ix_external_observations_review", "decision", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    sync_run_id = Column(Integer, ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    external_snapshot_id = Column(Integer, ForeignKey("external_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    sync_record_id = Column(Integer, ForeignKey("sync_records.id", ondelete="CASCADE"), nullable=False, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="SET NULL"), nullable=True, index=True)
    canonical_field_key = Column(String(200), nullable=False, index=True)
    raw_value = Column(Text)
    normalized_value = Column(Text)
    current_value = Column(Text)
    candidate_value = Column(Text)
    confidence = Column(String(30), nullable=False, default="high")
    decision = Column(String(30), nullable=False, default="pending_review", index=True)
    decision_reason = Column(Text)
    source_timestamp = Column(DateTime)
    decided_by = Column(String(100))
    decided_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    run = relationship("SyncRun", back_populates="observations")
    snapshot = relationship("ExternalSnapshot")
    sync_record = relationship("SyncRecord")
    patent = relationship("Patent")


class LegalStatusEvent(Base):
    __tablename__ = "legal_status_events"
    __table_args__ = (
        UniqueConstraint("connector_id", "provider_event_id", name="uq_legal_status_provider_event"),
        Index("ix_legal_status_events_patent_date", "patent_id", "event_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False, index=True)
    connector_id = Column(Integer, ForeignKey("connector_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    external_snapshot_id = Column(Integer, ForeignKey("external_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_event_id = Column(String(500), nullable=False)
    jurisdiction_code = Column(String(10))
    event_code = Column(String(100), nullable=False)
    event_date = Column(DateTime, nullable=False, index=True)
    status = Column(String(50), nullable=False, default="unknown")
    raw_description = Column(Text)
    payload_hash = Column(String(128))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    patent = relationship("Patent")
    connector = relationship("ConnectorDefinition")
    snapshot = relationship("ExternalSnapshot")


class WatchEvent(Base):
    __tablename__ = "watch_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_watch_events_dedupe_key"),
        Index("ix_watch_events_state", "status", "occurred_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=True, index=True)
    sync_subscription_id = Column(Integer, ForeignKey("sync_subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default="info")
    dedupe_key = Column(String(128), nullable=False)
    payload_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="unread", index=True)
    acknowledged_by = Column(String(100))
    acknowledged_at = Column(DateTime)
    occurred_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    patent = relationship("Patent")
    subscription = relationship("SyncSubscription")


class SyncDeadLetter(Base):
    __tablename__ = "sync_dead_letters"

    id = Column(Integer, primary_key=True, index=True)
    sync_run_id = Column(Integer, ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    sync_record_id = Column(Integer, ForeignKey("sync_records.id", ondelete="CASCADE"), nullable=True, index=True)
    error_class = Column(String(40), nullable=False)
    error_code = Column(String(100))
    error_message = Column(Text, nullable=False)
    retry_count = Column(Integer, nullable=False, default=0)
    replay_status = Column(String(30), nullable=False, default="pending")
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    replayed_at = Column(DateTime)


class SyncLease(Base):
    __tablename__ = "sync_leases"
    __table_args__ = (UniqueConstraint("subscription_id", name="uq_sync_leases_subscription"),)

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("sync_subscriptions.id", ondelete="CASCADE"), nullable=False)
    owner_id = Column(String(100), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class SyncUpdateBatch(Base):
    """A preview/confirmation transaction for explicit external overwrites."""
    __tablename__ = "sync_update_batches"
    __table_args__ = (Index("ix_sync_update_batches_status_created", "status", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    connector_id = Column(Integer, ForeignKey("connector_definitions.id", ondelete="SET NULL"), nullable=True, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="SET NULL"), nullable=True, index=True)
    sync_run_id = Column(Integer, ForeignKey("sync_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="preview", index=True)
    requested_patent_ids = Column(JSON, nullable=False, default=list)
    selected_fields = Column(JSON, nullable=False, default=list)
    expires_at = Column(DateTime, nullable=False, index=True)
    confirmed_at = Column(DateTime)
    confirmed_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    connector = relationship("ConnectorDefinition")
    database = relationship("PatentDatabase")
    run = relationship("SyncRun")
    items = relationship("SyncUpdateItem", back_populates="batch", cascade="all, delete-orphan", order_by="SyncUpdateItem.id")


class SyncUpdateItem(Base):
    """Provider result and field-level choices for one Patent in a batch."""
    __tablename__ = "sync_update_items"
    __table_args__ = (
        Index("ix_sync_update_items_batch_status", "batch_id", "status"),
        Index("ix_sync_update_items_patent", "patent_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("sync_update_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="SET NULL"), nullable=True, index=True)
    external_record_id = Column(String(500))
    sync_record_id = Column(Integer, ForeignKey("sync_records.id", ondelete="SET NULL"), nullable=True, index=True)
    external_snapshot_id = Column(Integer, ForeignKey("external_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    current_fields = Column(JSON, nullable=False, default=dict)
    candidate_fields = Column(JSON, nullable=False, default=dict)
    changed_fields = Column(JSON, nullable=False, default=list)
    selected_fields = Column(JSON, nullable=False, default=list)
    error_code = Column(String(100))
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    batch = relationship("SyncUpdateBatch", back_populates="items")
    patent = relationship("Patent")
    sync_record = relationship("SyncRecord")
    snapshot = relationship("ExternalSnapshot")
