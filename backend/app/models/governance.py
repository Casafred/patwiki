"""Import lineage and field-observation records.

These records deliberately sit outside Patent.custom_fields. An input
column that is not yet registered is still valuable evidence, but it is not a
canonical field until a user explicitly maps and confirms it.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
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
