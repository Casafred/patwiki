"""项目模型。"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50))
    product_id = Column(Integer, ForeignKey("products.id"))
    department_ids = Column(JSON, nullable=False, default=list)
    # 所属产品线：项目界面按产品线管理里配置的产品线进行多选。
    product_line_ids = Column(JSON, nullable=False, default=list)
    project_level = Column(String(30))
    project_type = Column(String(30))
    brands = Column(JSON, nullable=False, default=list)
    project_manager = Column(String(100))
    research_owner = Column(String(100))
    shipping_regions = Column(Text)
    current_stage = Column(String(30))
    product_model = Column(String(100))
    product_category = Column(String(200))
    description = Column(Text)
    module = Column(String(200))
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(50), default="in_progress")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    product = relationship("Product", back_populates="projects")
    patents = relationship("Patent", secondary="patent_projects", back_populates="projects")
    solution_versions = relationship(
        "ProjectSolutionVersion",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectSolutionVersion.id.desc()",
    )
    history = relationship(
        "ProjectHistory", back_populates="project", cascade="all, delete-orphan",
        order_by="ProjectHistory.id.desc()",
    )
    attachments = relationship(
        "ProjectAttachment", back_populates="project", cascade="all, delete-orphan",
        order_by="ProjectAttachment.id.desc()",
    )

    @property
    def project_no(self):
        """Public name for the legacy project code column."""
        return self.code


class ProjectHistory(Base):
    __tablename__ = "project_histories"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(30), nullable=False, default="updated")
    changed_by = Column(String(100), nullable=False, default="local-user")
    changes = Column(JSON, nullable=False, default=dict)
    snapshot = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, server_default=func.now())

    project = relationship("Project", back_populates="history")


class ProjectAttachment(Base):
    __tablename__ = "project_attachments"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="SET NULL"), nullable=True, index=True)
    scope = Column(String(30), nullable=False, default="project", index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    note = Column(Text)
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime, server_default=func.now())
    deleted_at = Column(DateTime, nullable=True, index=True)

    project = relationship("Project", back_populates="attachments")
