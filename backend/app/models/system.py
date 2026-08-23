"""System audit models used by the migration and governance platform.

These tables are deliberately append-oriented.  They are operational evidence
for the local SQLite database, not business workflow records.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func

from app.database import Base


class MigrationRun(Base):
    __tablename__ = "migration_runs"

    id = Column(Integer, primary_key=True, index=True)
    migration_version = Column(String(100), nullable=False, index=True)
    checksum = Column(String(128), nullable=False)
    app_version = Column(String(100), nullable=False)
    operator = Column(String(200), nullable=False)
    status = Column(String(30), nullable=False, index=True)
    backup_path = Column(String(1000))
    integrity_before = Column(String(100))
    integrity_after = Column(String(100))
    table_counts_before = Column(JSON)
    table_counts_after = Column(JSON)
    error = Column(Text)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)


class MigrationIssue(Base):
    __tablename__ = "migration_issues"

    id = Column(Integer, primary_key=True, index=True)
    migration_run_id = Column(Integer, ForeignKey("migration_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    entity = Column(String(200), nullable=False)
    issue_type = Column(String(100), nullable=False)
    detail = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
