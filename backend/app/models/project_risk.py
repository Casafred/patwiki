"""Project solution context and append-only risk tracking models.

These models intentionally keep project and risk context outside ``Patent``.
The patent remains the navigation anchor, while each case keeps its own
lifecycle, evidence context and historical assessments.
"""
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ProjectSolutionVersion(Base):
    __tablename__ = "project_solution_versions"

    id = Column(Integer, primary_key=True, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    project_stage = Column(String(30), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="draft", index=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    change_summary = Column(Text, nullable=True)
    change_reason = Column(Text, nullable=True)
    source_type = Column(String(50), nullable=True)
    source_description = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=False, default="local-user")
    confirmed_by = Column(String(100), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("Project", back_populates="solution_versions")
    changes = relationship(
        "ProjectSolutionChange",
        back_populates="solution_version",
        cascade="all, delete-orphan",
        order_by="ProjectSolutionChange.id",
    )
    regions = relationship(
        "ProjectSolutionRegion",
        back_populates="solution_version",
        cascade="all, delete-orphan",
        order_by="ProjectSolutionRegion.id",
    )
    risk_links = relationship("RiskSolutionLink", back_populates="solution_version")

    __table_args__ = (
        UniqueConstraint("project_id", "version_no", name="uq_project_solution_version_no"),
    )


class ProjectSolutionChange(Base):
    __tablename__ = "project_solution_changes"

    id = Column(Integer, primary_key=True, index=True)
    solution_version_id = Column(
        Integer,
        ForeignKey("project_solution_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    change_type = Column(String(50), nullable=True)
    feature_name = Column(String(200), nullable=False)
    before_description = Column(Text, nullable=True)
    after_description = Column(Text, nullable=True)
    impact_description = Column(Text, nullable=True)
    source_description = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=False, default="local-user")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    solution_version = relationship("ProjectSolutionVersion", back_populates="changes")


class ProjectSolutionRegion(Base):
    __tablename__ = "project_solution_regions"

    id = Column(Integer, primary_key=True, index=True)
    solution_version_id = Column(
        Integer,
        ForeignKey("project_solution_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    region_code = Column(String(30), nullable=False)
    region_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    solution_version = relationship("ProjectSolutionVersion", back_populates="regions")

    __table_args__ = (
        UniqueConstraint("solution_version_id", "region_code", name="uq_solution_region"),
    )


class RiskCase(Base):
    __tablename__ = "risk_cases"

    id = Column(Integer, primary_key=True, index=True)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    case_no = Column(String(80), nullable=True, index=True)
    title = Column(String(300), nullable=False)
    trigger_reason = Column(Text, nullable=False)
    status = Column(String(40), nullable=False, default="open", index=True)
    current_risk_level = Column(String(30), nullable=False, default="none", index=True)
    current_decision = Column(String(50), nullable=False, default="pending")
    current_gate_impact = Column(String(50), nullable=False, default="unknown")
    current_gate = Column(String(30), nullable=True)
    next_review_condition = Column(Text, nullable=True)
    next_review_at = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=False, default="local-user")
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    patent_links = relationship(
        "RiskPatentLink",
        back_populates="risk_case",
        cascade="all, delete-orphan",
        order_by="RiskPatentLink.id",
    )
    solution_links = relationship(
        "RiskSolutionLink",
        back_populates="risk_case",
        cascade="all, delete-orphan",
        order_by="RiskSolutionLink.id",
    )
    regions = relationship(
        "RiskCaseRegion",
        back_populates="risk_case",
        cascade="all, delete-orphan",
        order_by="RiskCaseRegion.id",
    )
    assessments = relationship(
        "RiskAssessmentVersion",
        back_populates="risk_case",
        cascade="all, delete-orphan",
        order_by="RiskAssessmentVersion.version_no.desc()",
    )
    reviews = relationship(
        "RiskReviewEvent",
        back_populates="risk_case",
        cascade="all, delete-orphan",
        order_by="RiskReviewEvent.id.desc()",
    )


class RiskPatentLink(Base):
    __tablename__ = "risk_patent_links"

    id = Column(Integer, primary_key=True, index=True)
    risk_case_id = Column(Integer, ForeignKey("risk_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False, index=True)
    link_role = Column(String(40), nullable=False, default="risk_patent")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    risk_case = relationship("RiskCase", back_populates="patent_links")
    patent = relationship("Patent", back_populates="risk_links")

    __table_args__ = (
        UniqueConstraint("risk_case_id", "patent_id", name="uq_risk_patent_link"),
    )


class RiskSolutionLink(Base):
    __tablename__ = "risk_solution_links"

    id = Column(Integer, primary_key=True, index=True)
    risk_case_id = Column(Integer, ForeignKey("risk_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    solution_version_id = Column(
        Integer,
        ForeignKey("project_solution_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    link_role = Column(String(40), nullable=False, default="primary_solution")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    risk_case = relationship("RiskCase", back_populates="solution_links")
    solution_version = relationship("ProjectSolutionVersion", back_populates="risk_links")

    __table_args__ = (
        UniqueConstraint("risk_case_id", "solution_version_id", name="uq_risk_solution_link"),
    )


class RiskCaseRegion(Base):
    __tablename__ = "risk_case_regions"

    id = Column(Integer, primary_key=True, index=True)
    risk_case_id = Column(Integer, ForeignKey("risk_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    region_code = Column(String(30), nullable=False)
    region_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    risk_case = relationship("RiskCase", back_populates="regions")

    __table_args__ = (
        UniqueConstraint("risk_case_id", "region_code", name="uq_risk_case_region"),
    )


class RiskAssessmentVersion(Base):
    __tablename__ = "risk_assessment_versions"

    id = Column(Integer, primary_key=True, index=True)
    risk_case_id = Column(Integer, ForeignKey("risk_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    solution_version_id = Column(
        Integer,
        ForeignKey("project_solution_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    jurisdiction_code = Column(String(30), nullable=True, index=True)
    input_hash = Column(String(128), nullable=True)
    version_no = Column(Integer, nullable=False)
    assessment_stage = Column(String(30), nullable=True)
    preliminary_assessment = Column(Text, nullable=True)
    analysis_confirmation = Column(Text, nullable=True)
    discussion_conclusion = Column(Text, nullable=True)
    leadership_confirmation = Column(Text, nullable=True)
    decision = Column(String(50), nullable=False, default="pending")
    risk_level = Column(String(30), nullable=False, default="none")
    gate_impact = Column(String(50), nullable=False, default="unknown")
    decision_basis = Column(Text, nullable=True)
    mitigation_summary = Column(Text, nullable=True)
    evidence_summary = Column(Text, nullable=True)
    assessed_by = Column(String(100), nullable=True)
    reviewed_by = Column(String(100), nullable=True)
    confirmed_by = Column(String(100), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    decided_by = Column(String(100), nullable=True)
    decision_at = Column(DateTime, nullable=True)
    created_by = Column(String(100), nullable=False, default="local-user")
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    risk_case = relationship("RiskCase", back_populates="assessments")
    solution_version = relationship("ProjectSolutionVersion")

    __table_args__ = (
        UniqueConstraint("risk_case_id", "version_no", name="uq_risk_assessment_version"),
    )


class RiskReviewEvent(Base):
    __tablename__ = "risk_review_events"

    id = Column(Integer, primary_key=True, index=True)
    risk_case_id = Column(Integer, ForeignKey("risk_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_type = Column(String(50), nullable=False)
    trigger_description = Column(Text, nullable=True)
    review_outcome = Column(Text, nullable=False)
    next_review_condition = Column(Text, nullable=True)
    next_review_at = Column(Date, nullable=True)
    reviewed_by = Column(String(100), nullable=False, default="local-user")
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    risk_case = relationship("RiskCase", back_populates="reviews")
