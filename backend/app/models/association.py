"""关联表/关联模型。

P0-9：patent_project 从 Table 升级为 PatentProjectLink 模型，
支持 relation_type / risk_level / document_role / relevance_score / importance / assigned_to_id 等多维属性。

向后兼容策略：
- `patent_projects` 表名保持不变，原列 patent_id/project_id/role/notes 不变
- 新增多维属性列，SQLite 会自动 ADD COLUMN（init_db 用 create_all）
- `patent_project` 变量指向 PatentProjectLink.__table__，继续作为 secondary 使用
- 旧代码 `patent.projects = [...]` 仍可用（ORM 只管理 patent_id/project_id，其他列由 PatentProjectLink 显式操作）
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, Table,
    Enum as SQLEnum,
)
from sqlalchemy.sql import func

from app.database import Base
from app.models.enums import ProjectRole, RiskLevel, RelationType, DocumentRole


# 简单多对多：专利-标签（无额外属性）
patent_tag = Table(
    "patent_tags",
    Base.metadata,
    Column("patent_id", Integer, ForeignKey("patents.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
    Column("created_at", DateTime, server_default=func.now()),
)


class PatentProjectLink(Base):
    """专利-项目关联（带多维属性）。

    relation_type: 风险相关 / 申请相关 / 参考相关 / 防御相关 / 布局相关
    document_role: 专利性文件 / 前案 / 案卷 / 被引用文献
    risk_level: 关联风险等级（与 Patent.risk_level 互补，更细粒度）
    relevance_score: 0-100 相关度评分
    importance: S/A/B/C/D 重要度评级
    """
    __tablename__ = "patent_projects"
    id = Column(Integer, primary_key=True, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    role = Column(SQLEnum(ProjectRole), default=ProjectRole.REFERENCE)
    relation_type = Column(SQLEnum(RelationType), default=RelationType.REFERENCE)
    risk_level = Column(SQLEnum(RiskLevel), default=RiskLevel.NONE)
    document_role = Column(SQLEnum(DocumentRole), default=DocumentRole.OTHER)
    relevance_score = Column(Integer)
    importance = Column(String(20))
    notes = Column(Text)
    assigned_to_id = Column(Integer, ForeignKey("people.id"))
    linked_at = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("patent_id", "project_id", name="_patent_project_uc"),
    )


# 兼容引用：旧代码用 patent_project 作为 secondary 参数
patent_project = PatentProjectLink.__table__
