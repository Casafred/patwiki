"""Persistent field-governance registry.

The runtime FieldRegistry describes how PatWiki reads and writes fields.  The
models in this module describe where fields came from, what they mean, and
whether an import column has been approved for a runtime target.
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class FieldRegistrySnapshot(Base):
    __tablename__ = "field_registry_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    registry_version = Column(String(100), unique=True, nullable=False, index=True)
    source_files = Column(JSON, nullable=False)
    metadata_fields = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    loaded_at = Column(DateTime, server_default=func.now(), nullable=False)


class SourceTableDefinition(Base):
    __tablename__ = "source_table_definitions"

    id = Column(Integer, primary_key=True, index=True)
    table_key = Column(String(160), unique=True, nullable=False, index=True)
    title = Column(String(300), nullable=False)
    category = Column(String(100))
    purpose = Column(Text)
    usage_level = Column(String(100))
    purpose_system = Column(String(100))
    field_count = Column(Integer)
    target_shape = Column(String(200))
    source_file = Column(String(300), nullable=False)
    source_sheet = Column(String(200))
    status = Column(String(30), default="active", nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    source_fields = relationship("SourceFieldMapping", back_populates="source_table")


class FieldDefinition(Base):
    __tablename__ = "field_definitions"

    id = Column(Integer, primary_key=True, index=True)
    canonical_key = Column(String(200), unique=True, nullable=False, index=True)
    display_name = Column(String(300), nullable=False, index=True)
    owner_entity_type = Column(String(300))
    semantic_type = Column(String(100))
    source_type = Column(String(300))
    source_system = Column(String(200))
    source_timestamp = Column(DateTime)
    volatility = Column(String(200))
    update_policy = Column(String(200))
    freshness_ttl = Column(String(100))
    validation_schema = Column(JSON)
    sensitivity = Column(String(200))
    read_roles = Column(JSON)
    write_roles = Column(JSON)
    approval_policy = Column(JSON)
    lock_policy = Column(JSON)
    audit_policy = Column(String(300))
    ai_policy = Column(JSON)
    retention_policy = Column(JSON)
    index_policy = Column(String(100))
    promote_threshold = Column(JSON)
    storage_kind = Column(String(300))
    storage_locator = Column(String(300))
    business_key_scope = Column(String(200))
    migration_status = Column(String(50), default="candidate", nullable=False, index=True)
    responsibility_level = Column(String(200))
    change_owner = Column(String(200))
    change_ticket = Column(String(200))
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    source_mappings = relationship("SourceFieldMapping", back_populates="field_definition")


class SourceFieldMapping(Base):
    __tablename__ = "source_field_mappings"

    id = Column(Integer, primary_key=True, index=True)
    source_table_id = Column(Integer, ForeignKey("source_table_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    source_field_name = Column(String(300), nullable=False)
    normalized_alias = Column(String(300), nullable=False, index=True)
    canonical_field_key = Column(String(200), ForeignKey("field_definitions.canonical_key", ondelete="SET NULL"), index=True)
    target_field_key = Column(String(200), index=True)
    mapping_status = Column(String(30), nullable=False, index=True)
    mapping_version = Column(String(100), nullable=False, index=True)
    occurrence_count = Column(Integer, default=1, nullable=False)
    sample_values = Column(JSON)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    source_table = relationship("SourceTableDefinition", back_populates="source_fields")
    field_definition = relationship("FieldDefinition", back_populates="source_mappings")

    __table_args__ = (
        UniqueConstraint(
            "source_table_id",
            "source_field_name",
            "mapping_version",
            name="uq_source_field_mapping_version",
        ),
    )
