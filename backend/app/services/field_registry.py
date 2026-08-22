from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


FieldMeta = dict[str, Any]

# 关系列是正式的只读展示字段：导入时保留原始单元格，关系实体另行解析。
# 这些键位于 Patent.custom_fields 中，避免把来源文本误当作关系 ID。
RELATION_FIELD_KEYS = {"family_members", "cited_patents", "citing_patents"}


class FieldHandler:
    """字段适配器基类，统一字段元数据和记录值访问边界。"""

    def list_fields(self, db) -> list[FieldMeta]:
        return []

    def get_field(self, key: str, db=None) -> FieldMeta | None:
        return next((field for field in self.list_fields(db) if field.get("key") == key), None)

    def read_value(self, record: Any, key: str) -> Any:
        return getattr(record, key, None)

    def write_value(self, record: Any, key: str, value: Any) -> None:
        setattr(record, key, value)


@dataclass(frozen=True)
class SystemFieldHandler(FieldHandler):
    definition: Mapping[str, Any]

    def list_fields(self, db=None) -> list[FieldMeta]:
        return [{**self.definition, "is_system": True}]


class CustomFieldHandler(FieldHandler):
    """把 CustomField 模型转换为表格统一字段元数据。"""

    @staticmethod
    def _field_type(field: Any) -> str:
        return field.field_type.value if hasattr(field.field_type, "value") else str(field.field_type)

    def list_fields(self, db) -> list[FieldMeta]:
        if db is None:
            return []
        from app.models import CustomField

        fields = db.query(CustomField).filter(CustomField.is_active == True).order_by(
            CustomField.sort_order, CustomField.name
        ).all()
        return [self.to_meta(field) for field in fields]

    def to_meta(self, field: Any) -> FieldMeta:
        field_type = self._field_type(field)
        is_formula = field_type == "formula"
        return {
            "key": field.key,
            "name": field.name,
            "field_type": field_type,
            "group_name": field.group_name or "自定义",
            "options": field.options,
            "option_labels": None,
            "width": 140,
            "sortable": field_type in ("text", "number", "date", "select", "boolean"),
            "filterable": True,
            "editable": not is_formula,
            "frozen": False,
            "visible": True,
            "is_system": False,
            "is_ai": field.ai_config is not None,
            "is_formula": is_formula,
            "ai_config": field.ai_config,
            "formula_config": field.formula_config,
            "link_config": field.link_config,
            "lookup_config": field.lookup_config,
            "rollup_config": field.rollup_config,
            "description": field.description,
            "id": field.id,
            "sort_order": field.sort_order,
        }

    def read_value(self, record: Any, key: str) -> Any:
        return (getattr(record, "custom_fields", None) or {}).get(key)

    def write_value(self, record: Any, key: str, value: Any) -> None:
        values = dict(getattr(record, "custom_fields", None) or {})
        values[key] = value
        record.custom_fields = values


class PatentAttachmentFieldHandler(FieldHandler):
    """The built-in attachment field is stored alongside other extensible values."""

    definition: FieldMeta = {
        "key": "attachments",
        "name": "关联附件",
        "field_type": "attachment",
        "group_name": "文档",
        "options": None,
        "width": 260,
        "sortable": False,
        "filterable": False,
        "editable": True,
        "frozen": False,
        "visible": True,
        "is_system": False,
        "description": "与专利关联的邮件、演示文稿、专利原文、图片和会议材料",
    }

    def list_fields(self, db=None) -> list[FieldMeta]:
        return [dict(self.definition)]

    def read_value(self, record: Any, key: str) -> Any:
        return (getattr(record, "custom_fields", None) or {}).get(key)

    def write_value(self, record: Any, key: str, value: Any) -> None:
        values = dict(getattr(record, "custom_fields", None) or {})
        values[key] = value
        record.custom_fields = values


class FieldRegistry:
    """可扩展字段处理器注册表。"""

    def __init__(self, handlers: Iterable[FieldHandler] = ()):
        self._handlers: list[FieldHandler] = list(handlers)

    def register(self, handler: FieldHandler) -> FieldHandler:
        self._handlers.append(handler)
        return handler

    def list_fields(self, db=None) -> list[FieldMeta]:
        fields: list[FieldMeta] = []
        for handler in self._handlers:
            fields.extend(handler.list_fields(db))
        return fields

    def get_field(self, key: str, db=None) -> FieldMeta | None:
        for handler in self._handlers:
            field = handler.get_field(key, db)
            if field is not None:
                return field
        return None

    def read_value(self, record: Any, key: str, db=None) -> Any:
        handler = self._handler_for(key, db)
        return handler.read_value(record, key) if handler else None

    def write_value(self, record: Any, key: str, value: Any, db=None) -> None:
        handler = self._handler_for(key, db)
        if handler is None:
            raise KeyError(f"Unknown field: {key}")
        handler.write_value(record, key, value)

    def _handler_for(self, key: str, db=None) -> FieldHandler | None:
        for handler in self._handlers:
            if handler.get_field(key, db) is not None:
                return handler
        return None


SYSTEM_FIELD_DEFINITIONS = [
    {
        "key": "id",
        "name": "ID",
        "field_type": "number",
        "group_name": "系统",
        "options": None,
        "width": 60,
        "sortable": True,
        "filterable": False,
        "editable": False,
        "frozen": True,
        "visible": False,
    },
    {
        "key": "application_number",
        "name": "申请号",
        "field_type": "text",
        "group_name": "著录项目",
        "options": None,
        "width": 150,
        "sortable": True,
        "filterable": True,
        "editable": True,
        "frozen": True,
        "visible": True,
    },
    {
        "key": "publication_number",
        "name": "公开号",
        "field_type": "text",
        "group_name": "著录项目",
        "options": None,
        "width": 140,
        "sortable": True,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "title",
        "name": "标题",
        "field_type": "text",
        "group_name": "著录项目",
        "options": None,
        "width": 320,
        "sortable": True,
        "filterable": True,
        "editable": True,
        "frozen": True,
        "visible": True,
    },
    {
        "key": "abstract",
        "name": "摘要",
        "field_type": "longtext",
        "group_name": "著录项目",
        "options": None,
        "width": 240,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "claims",
        "name": "权利要求",
        "field_type": "longtext",
        "group_name": "著录项目",
        "options": None,
        "width": 280,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "grant_number",
        "name": "授权号",
        "field_type": "text",
        "group_name": "著录项目",
        "options": None,
        "width": 140,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "applicant",
        "name": "申请人",
        "field_type": "text",
        "group_name": "著录项目",
        "options": None,
        "width": 160,
        "sortable": True,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "inventor",
        "name": "发明人",
        "field_type": "text",
        "group_name": "著录项目",
        "options": None,
        "width": 140,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "assignee",
        "name": "专利权人",
        "field_type": "text",
        "group_name": "著录项目",
        "options": None,
        "width": 140,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "agent",
        "name": "代理机构",
        "field_type": "text",
        "group_name": "著录项目",
        "options": None,
        "width": 140,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "country",
        "name": "国家",
        "field_type": "select",
        "group_name": "著录项目",
        "options": ["CN", "US", "EP", "JP", "KR", "WO", "DE", "GB", "FR", "Other"],
        "width": 70,
        "sortable": True,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "patent_type",
        "name": "专利类型",
        "field_type": "select",
        "group_name": "著录项目",
        "options": ["invention", "utility_model", "design", "pct"],
        "option_labels": {"invention": "发明", "utility_model": "实用新型", "design": "外观设计", "pct": "PCT"},
        "width": 90,
        "sortable": True,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "filing_date",
        "name": "申请日",
        "field_type": "date",
        "group_name": "日期",
        "options": None,
        "width": 110,
        "sortable": True,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "publication_date",
        "name": "公开日",
        "field_type": "date",
        "group_name": "日期",
        "options": None,
        "width": 110,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "grant_date",
        "name": "授权日",
        "field_type": "date",
        "group_name": "日期",
        "options": None,
        "width": 110,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "priority_date",
        "name": "优先权日",
        "field_type": "date",
        "group_name": "日期",
        "options": None,
        "width": 110,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "priority_number",
        "name": "优先权号",
        "field_type": "text",
        "group_name": "著录项目",
        "options": None,
        "width": 140,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "priority_country",
        "name": "优先权国家",
        "field_type": "text",
        "group_name": "著录项目",
        "options": None,
        "width": 90,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "legal_status",
        "name": "法律状态",
        "field_type": "select",
        "group_name": "法律",
        "options": ["pending", "published", "examining", "granted", "rejected", "withdrawn", "deemed_withdrawn", "expired", "abandoned", "unknown"],
        "option_labels": {
            "pending": "待审", "published": "公开", "examining": "实审中", "granted": "授权",
            "rejected": "驳回", "withdrawn": "撤回", "deemed_withdrawn": "视撤",
            "expired": "终止", "abandoned": "放弃", "unknown": "未知",
        },
        "width": 90,
        "sortable": True,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "legal_status_date",
        "name": "法律状态日",
        "field_type": "date",
        "group_name": "法律",
        "options": None,
        "width": 110,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "legal_status_details",
        "name": "法律状态详情",
        "field_type": "textarea",
        "group_name": "法律",
        "options": None,
        "width": 200,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "ipc_main",
        "name": "主IPC",
        "field_type": "text",
        "group_name": "分类",
        "options": None,
        "width": 110,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "ipc_all",
        "name": "全部IPC",
        "field_type": "textarea",
        "group_name": "分类",
        "options": None,
        "width": 200,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "cpc_main",
        "name": "主CPC",
        "field_type": "text",
        "group_name": "分类",
        "options": None,
        "width": 110,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "cpc_all",
        "name": "全部CPC",
        "field_type": "textarea",
        "group_name": "分类",
        "options": None,
        "width": 200,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "category",
        "name": "技术分类",
        "field_type": "text",
        "group_name": "业务",
        "options": None,
        "width": 120,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "subcategory",
        "name": "子分类",
        "field_type": "text",
        "group_name": "业务",
        "options": None,
        "width": 120,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "module",
        "name": "功能模块",
        "field_type": "text",
        "group_name": "业务",
        "options": None,
        "width": 120,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "has_risk",
        "name": "有风险",
        "field_type": "boolean",
        "group_name": "风险",
        "options": None,
        "width": 70,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "risk_level",
        "name": "风险等级",
        "field_type": "select",
        "group_name": "风险",
        "options": ["none", "low", "medium", "high", "critical"],
        "option_labels": {"none": "无", "low": "低", "medium": "中", "high": "高", "critical": "极高"},
        "width": 80,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": True,
    },
    {
        "key": "risk_description",
        "name": "风险描述",
        "field_type": "textarea",
        "group_name": "风险",
        "options": None,
        "width": 200,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "technical_problem",
        "name": "技术问题",
        "field_type": "textarea",
        "group_name": "技术信息",
        "options": None,
        "width": 200,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "technical_solution",
        "name": "技术方案",
        "field_type": "textarea",
        "group_name": "技术信息",
        "options": None,
        "width": 240,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "technical_effect",
        "name": "技术效果",
        "field_type": "textarea",
        "group_name": "技术信息",
        "options": None,
        "width": 200,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "application_status",
        "name": "应用状态",
        "field_type": "select",
        "group_name": "业务",
        "options": ["not_applied", "evaluating", "applied", "monitoring", "abandoned"],
        "option_labels": {"not_applied": "未应用", "evaluating": "评估中", "applied": "已应用", "monitoring": "监控中", "abandoned": "已放弃"},
        "width": 90,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "scope_description",
        "name": "保护范围",
        "field_type": "textarea",
        "group_name": "业务",
        "options": None,
        "width": 200,
        "sortable": False,
        "filterable": True,
        "editable": True,
        "visible": False,
    },
    {
        "key": "notes",
        "name": "备注",
        "field_type": "textarea",
        "group_name": "其他",
        "options": None,
        "width": 160,
        "sortable": False,
        "filterable": False,
        "editable": True,
        "visible": False,
    },
    {
        "key": "created_at",
        "name": "录入时间",
        "field_type": "datetime",
        "group_name": "系统",
        "options": None,
        "width": 150,
        "sortable": True,
        "filterable": False,
        "editable": False,
        "visible": False,
    },
    {
        "key": "product_id",
        "name": "产品",
        "field_type": "number",
        "group_name": "关联",
        "options": None,
        "width": 150,
        "sortable": True,
        "filterable": True,
        "editable": True,
        "visible": False,
        "description": "当前专利归属产品；列表显示产品名称，编辑仍通过产品主数据选择。",
    },
    {
        "key": "projects",
        "name": "关联项目",
        "field_type": "longtext",
        "group_name": "关联",
        "options": None,
        "width": 220,
        "sortable": False,
        "filterable": False,
        "editable": False,
        "visible": False,
        "description": "PatentProjectLink 多值关系的只读投影；详情页可维护关系。",
    },
    {
        "key": "family_members",
        "name": "同族专利号",
        "field_type": "longtext",
        "group_name": "关系",
        "options": None,
        "width": 240,
        "sortable": False,
        "filterable": True,
        "editable": False,
        "visible": True,
        "description": "导入表格中的原始同族公开号；同时由系统建立可导航的同族关系。",
    },
    {
        "key": "cited_patents",
        "name": "引用专利号",
        "field_type": "longtext",
        "group_name": "关系",
        "options": None,
        "width": 240,
        "sortable": False,
        "filterable": True,
        "editable": False,
        "visible": True,
        "description": "当前专利引用的原始公开号；同时由系统建立正向引用关系。",
    },
    {
        "key": "citing_patents",
        "name": "被引用专利号",
        "field_type": "longtext",
        "group_name": "关系",
        "options": None,
        "width": 240,
        "sortable": False,
        "filterable": True,
        "editable": False,
        "visible": True,
        "description": "引用当前专利的原始公开号；同时由系统建立反向引用关系。",
    },
]

SYSTEM_FIELD_HANDLERS = tuple(SystemFieldHandler(definition) for definition in SYSTEM_FIELD_DEFINITIONS)
SYSTEM_FIELDS_REGISTRY = [handler.list_fields()[0] for handler in SYSTEM_FIELD_HANDLERS]
SYSTEM_FIELD_KEYS = {field["key"] for field in SYSTEM_FIELDS_REGISTRY}
FIELD_REGISTRY = FieldRegistry((*SYSTEM_FIELD_HANDLERS, PatentAttachmentFieldHandler(), CustomFieldHandler()))


def get_system_field_meta(key: str) -> FieldMeta | None:
    return next((field for field in SYSTEM_FIELDS_REGISTRY if field["key"] == key), None)


def get_all_fields_meta(db) -> list[FieldMeta]:
    return FIELD_REGISTRY.list_fields(db)
