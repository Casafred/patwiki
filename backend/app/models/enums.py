"""枚举类型定义。"""
import enum


class LegalStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    EXAMINING = "examining"
    GRANTED = "granted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    DEEMED_WITHDRAWN = "deemed_withdrawn"
    EXPIRED = "expired"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class PatentType(str, enum.Enum):
    INVENTION = "invention"
    UTILITY_MODEL = "utility_model"
    DESIGN = "design"
    PCT = "pct"


class ProjectRole(str, enum.Enum):
    CORE = "core"
    APPLIED = "applied"
    RISK = "risk"
    REFERENCE = "reference"
    PERIPHERAL = "peripheral"
    DEFENSIVE = "defensive"


class RiskLevel(str, enum.Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImportBatchStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class CustomFieldType(str, enum.Enum):
    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    URL = "url"
    RATING = "rating"
    AI_FIELD = "ai_field"


class RelationType(str, enum.Enum):
    """专利-项目关联类型。"""
    RISK = "risk"               # 风险相关
    APPLICATION = "application"  # 申请相关
    REFERENCE = "reference"      # 参考相关
    DEFENSE = "defense"          # 防御相关
    LAYOUT = "layout"            # 布局相关


class DocumentRole(str, enum.Enum):
    """专利在项目中的文件性质。"""
    CORE_PATENT = "core_patent"      # 专利性文件
    PRIOR_ART = "prior_art"          # 前案
    FILE_WRAPPER = "file_wrapper"    # 案卷
    CITED = "cited"                  # 被引用文献
    OTHER = "other"


class HistorySource(str, enum.Enum):
    """专利字段修改来源类型（P1-13）。

    用于 PatentHistory.source 字段，实现完整溯源：
    - manual: 大表上手动编辑
    - view_edit: 在小表视图中编辑共享字段（同时记录 source_view_id）
    - import: Excel 导入合并
    - ai: AI 字段计算
    - promote: 视图本地字段提升为全局字段
    - bulk: 批量编辑
    - api: 其他 API 调用
    """
    MANUAL = "manual"
    VIEW_EDIT = "view_edit"
    IMPORT = "import"
    AI = "ai"
    PROMOTE = "promote"
    BULK = "bulk"
    API = "api"
