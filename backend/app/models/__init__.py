"""数据模型汇总 re-export。

按 03-项目结构与代码规范.md 拆分为多个子模块，本文件仅做聚合 re-export，
保持向后兼容（所有 `from app.models import X` 仍可用）。

子模块组织：
- enums:          枚举类型
- association:    关联表（patent_tag, patent_project/PatentProjectLink）
- organization:   Department / Person / ProductLine / Product
- project:        Project
- tag:            TagGroup / Tag
- field:          CustomField
- database:       PatentDatabase（P0-8 新增）
- patent:         Patent / PatentFamily / Citation
- identity:       PatentIdentifier（统一专利身份索引）
- ai:             AITask / AIFieldValue
- importing:      FieldMapping / ImportBatch
- user:           User / DatabaseMembership
- view:           PatentView / ViewLocalField / PatentViewFieldValue（P0-13 新增）
- history:        PatentHistory
- cross_table_link: CrossTableLink（通用 Link 字段关联）
"""
# 枚举
from app.models.enums import (
    LegalStatus, PatentType, ProjectRole, RiskLevel,
    ImportBatchStatus, CustomFieldType,
    RelationType, DocumentRole,
)

# 关联表
from app.models.association import (
    patent_tag, patent_project, PatentProjectLink,
)

# 组织/人员/产品
from app.models.organization import (
    Department, Person, ProductLine, Product,
)

# 项目
from app.models.project import Project

# 标签
from app.models.tag import TagGroup, Tag

# 自定义字段
from app.models.field import CustomField

# 通用跨表关联
from app.models.cross_table_link import CrossTableLink

# 公式字段依赖
from app.models.formula import FormulaDependency

# 库（P0-8 新增）
from app.models.database import PatentDatabase

# 专利主表+同族+引用
from app.models.patent import Patent, PatentFamily, Citation
from app.models.identity import PatentIdentifier
from app.models.export_template import PatentExportTemplate

# AI
from app.models.ai import AITask, AIFieldValue

# 导入
from app.models.importing import FieldMapping, ImportBatch
from app.models.governance import ImportSourceRow, FieldObservation, GovernanceDecision, GovernanceReversal

# 用户与协作（权限管理 MVP）
from app.models.user import User, DatabaseMembership

# 视图（小表）—— P0-13 新增
from app.models.view import PatentView, ViewLocalField, PatentViewFieldValue

# 表单视图公开提交链接
from app.models.form import FormShareLink

# 修改历史
from app.models.history import PatentHistory

# 单专利只读分享
from app.models.share import PatentShare

# 自动化规则与执行日志
from app.models.automation import AutomationRule, AutomationLog
from app.models.attachment import Attachment
from app.models.dashboard import Dashboard
from app.models.comment import Comment


__all__ = [
    # enums
    "LegalStatus", "PatentType", "ProjectRole", "RiskLevel",
    "ImportBatchStatus", "CustomFieldType",
    "RelationType", "DocumentRole",
    # association
    "patent_tag", "patent_project", "PatentProjectLink",
    # organization
    "Department", "Person", "ProductLine", "Product",
    # project
    "Project",
    # tag
    "TagGroup", "Tag",
    # field
    "CustomField", "CrossTableLink", "FormulaDependency",
    # database
    "PatentDatabase",
    # patent
    "Patent", "PatentFamily", "Citation", "PatentIdentifier", "PatentExportTemplate",
    # ai
    "AITask", "AIFieldValue",
    # importing
    "FieldMapping", "ImportBatch", "ImportSourceRow", "FieldObservation", "GovernanceDecision",
    # user / membership
    "User", "DatabaseMembership",
    # view (P0-13)
    "PatentView", "ViewLocalField", "PatentViewFieldValue",
    "FormShareLink",
    # history
    "PatentHistory",
    # public share
    "PatentShare",
    # automation
    "AutomationRule", "AutomationLog",
    "Attachment",
    "Dashboard",
    "Comment",
]
