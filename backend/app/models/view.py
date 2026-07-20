"""部门级总表与小表（视图）模型——P0-13 新增。

核心架构：单源大表 + 视图小表（Master + View）
- PatentDatabase 作为部门级"大表"（单源）
- PatentView 作为"小表"（保存的视图：筛选 + 列投影 + 视图本地字段）
- 共享字段编辑实时贯通到大表
- 视图本地字段不污染大表，可一键提升为全局 CustomField
- PatentHistory 记录每次字段修改的来源视图，支持追溯
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PatentView(Base):
    """小表（视图）定义。

    view_type:
      - personal:          个人视图（仅 owner 可见）
      - shared:            共享视图（同库成员可见）
      - department_master: 部门总表视图（每个 database 唯一一个，is_department_master=True）

    filter_config: 与 PatentService.list_patents 的 filters 参数同构
        {"category": {"contains": "传感器"}, "has_risk": {"eq": true}, ...}

    column_config: 列投影配置
        [{"key": "application_number", "visible": true, "width": 150, "order": 0},
         {"key": "title", "visible": true, "width": 320, "order": 1}, ...]

    sort_config: 默认排序
        {"sort_by": "filing_date", "sort_order": "desc"}
    """
    __tablename__ = "patent_views"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    database_id = Column(Integer, ForeignKey("patent_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    view_type = Column(String(30), default="personal")  # personal / shared / department_master
    is_department_master = Column(Boolean, default=False, index=True)

    filter_config = Column(JSON, default=dict)
    column_config = Column(JSON, default=list)
    sort_config = Column(JSON, default=dict)

    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    database = relationship("PatentDatabase", backref="views")
    owner = relationship("User", foreign_keys=[owner_id])
    local_fields = relationship(
        "ViewLocalField", back_populates="view",
        cascade="all, delete-orphan", order_by="ViewLocalField.sort_order",
    )


class ViewLocalField(Base):
    """视图本地字段定义。

    仅属于某个小表的字段（任务专属属性），不污染大表。
    可通过 promote 操作转为全局 CustomField（存储 promoted_field_key）。
    """
    __tablename__ = "view_local_fields"
    __table_args__ = (
        UniqueConstraint("view_id", "key", name="uq_view_field_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    view_id = Column(Integer, ForeignKey("patent_views.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(100), nullable=False)  # vlf_ 前缀，与 cf_ 区分
    name = Column(String(200), nullable=False)
    field_type = Column(String(30), nullable=False)  # text/number/date/select/boolean/textarea
    options = Column(JSON)  # select 类型的可选值
    description = Column(Text)
    default_value = Column(Text)
    is_required = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)

    # 提升状态：已提升为全局 CustomField 后，记录全局字段 key
    is_promoted = Column(Boolean, default=False)
    promoted_field_key = Column(String(100), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    view = relationship("PatentView", back_populates="local_fields")


class PatentViewFieldValue(Base):
    """视图本地字段的值（按 patent × view × field 三元组存储）。

    与 Patent.custom_fields 平行，但仅在小表视图中可见。
    """
    __tablename__ = "patent_view_field_values"
    __table_args__ = (
        UniqueConstraint("patent_id", "view_id", "field_key", name="uq_patent_view_field"),
        Index("ix_pvfv_view_field", "view_id", "field_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False, index=True)
    view_id = Column(Integer, ForeignKey("patent_views.id", ondelete="CASCADE"), nullable=False, index=True)
    field_key = Column(String(100), nullable=False)
    value = Column(Text)

    updated_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
