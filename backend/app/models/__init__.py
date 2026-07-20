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
- ai:             AITask / AIFieldValue
- importing:      FieldMapping / ImportBatch
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

# 库（P0-8 新增）
from app.models.database import PatentDatabase

# 专利主表+同族+引用
from app.models.patent import Patent, PatentFamily, Citation

# AI
from app.models.ai import AITask, AIFieldValue

# 导入
from app.models.importing import FieldMapping, ImportBatch

# 用户与协作（权限管理 MVP）
from app.models.user import User, DatabaseMembership

# 修改历史
from app.models.history import PatentHistory


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
    "CustomField",
    # database
    "PatentDatabase",
    # patent
    "Patent", "PatentFamily", "Citation",
    # ai
    "AITask", "AIFieldValue",
    # importing
    "FieldMapping", "ImportBatch",
    # user / membership
    "User", "DatabaseMembership",
    # history
    "PatentHistory",
]
