"""Membership of a canonical Patent Wiki record in one or more databases."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PatentDatabaseMembership(Base):
    """A database is a view over the global patent index.

    Patent.database_id remains a legacy owner projection. This table is
    authoritative for visibility, so importing an existing Wiki never moves
    or duplicates the canonical record.
    """

    __tablename__ = "patent_database_memberships"
    __table_args__ = (
        UniqueConstraint("patent_id", "database_id", name="uq_patent_database_membership"),
        Index("ix_patent_database_memberships_database", "database_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())

    patent = relationship("Patent")
    database = relationship("PatentDatabase", back_populates="patent_memberships")
