"""Attachment metadata model. Binary files stay outside the SQLite database."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False, index=True)
    field_key = Column(String(100), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime, server_default=func.now())
    # Provenance for imported or linked media.  The binary remains on disk;
    # these fields make the source cell and import batch auditable.
    source_type = Column(String(40), nullable=False, default="manual_upload", index=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True, index=True)
    source_sheet = Column(String(200))
    source_cell = Column(String(30))
    source_row = Column(Integer)
    source_column = Column(Integer)
    source_url = Column(String(2000))
    sha256 = Column(String(64), index=True)
    width = Column(Integer)
    height = Column(Integer)
