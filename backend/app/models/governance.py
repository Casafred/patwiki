"""Import lineage and field-observation records.

These records deliberately sit outside Patent.custom_fields. An input
column that is not yet registered is still valuable evidence, but it is not a
canonical field until a user explicitly maps and confirms it.
"""
from sqlalchemy import Boolean, Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func

from app.database import Base


class ImportSourceRow(Base):
    __tablename__ = "import_source_rows"

    id = Column(Integer, primary_key=True, index=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    source_row = Column(Integer, nullable=False)
    raw_row = Column(JSON, nullable=False)
    row_hash = Column(String(128), index=True)
    resolution_status = Column(String(30), nullable=False, default="unmapped_retained", index=True)
    resolution_reason = Column(Text)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class FieldObservation(Base):
    __tablename__ = "field_observations"

    id = Column(Integer, primary_key=True, index=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    source_row_id = Column(Integer, ForeignKey("import_source_rows.id", ondelete="CASCADE"), nullable=False, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="SET NULL"), nullable=True, index=True)
    source_field_name = Column(String(500), nullable=False, index=True)
    source_column_index = Column(Integer)
    canonical_field_key = Column(String(200), nullable=True, index=True)
    raw_value = Column(Text)
    normalized_value = Column(Text)
    current_value = Column(Text)
    candidate_value = Column(Text)
    difference_type = Column(String(30), nullable=False, default="unknown", index=True)
    field_resolution = Column(String(30), nullable=False, default="unmapped_retained", index=True)
    proposed_action = Column(String(30))
    final_decision = Column(String(30))
    decided_by = Column(String(100))
    decided_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class GovernanceDecision(Base):
    """Append-only record of a user's decision about a field observation."""

    __tablename__ = "governance_decisions"

    id = Column(Integer, primary_key=True, index=True)
    observation_id = Column(
        Integer,
        ForeignKey("field_observations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_batch_id = Column(String(64), nullable=True, index=True)
    action = Column(String(40), nullable=False, index=True)
    scope = Column(String(30), nullable=False, default="single")
    canonical_field_key = Column(String(200), nullable=True, index=True)
    mapping_version = Column(String(100), nullable=True)
    before_field_resolution = Column(String(30), nullable=True)
    before_final_decision = Column(String(30), nullable=True)
    before_proposed_action = Column(String(30), nullable=True)
    before_canonical_field_key = Column(String(200), nullable=True)
    before_decided_by = Column(String(100), nullable=True)
    before_decided_at = Column(DateTime, nullable=True)
    patent_id = Column(Integer, nullable=True, index=True)
    patent_field_key = Column(String(200), nullable=True)
    patent_value_before = Column(Text, nullable=True)
    patent_value_after = Column(Text, nullable=True)
    patent_value_changed = Column(Boolean, nullable=False, default=False)
    adopted_value = Column(Boolean, nullable=False, default=False)
    decided_by = Column(String(100), nullable=False, default="local-user")
    reason = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class GovernanceReversal(Base):
    """Append-only record that a governance decision batch was reverted."""

    __tablename__ = "governance_reversals"

    id = Column(Integer, primary_key=True, index=True)
    decision_batch_id = Column(String(64), nullable=False, index=True)
    reversed_by = Column(String(100), nullable=False, default="local-user")
    reason = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), index=True)
