import hashlib
import re
from datetime import datetime
from typing import Optional, Any
from io import BytesIO

import pandas as pd
from sqlalchemy.orm import Session

from app.models import (
    Patent,
    CustomField, CustomFieldType, LegalStatus, PatentType, RiskLevel
)
from app.services.relation_service import parse_patent_numbers


# 虚拟字段：不直接写入 Patent 主表，由 relation_service 处理
VIRTUAL_FIELDS = {"family_members", "cited_patents", "citing_patents"}

# CustomField 的 key 前缀（与 field_registry 的 system_field 区分）
CUSTOM_FIELD_KEY_PREFIX = "cf_"


STANDARD_FIELD_MAPPINGS = {
    "申请号": "application_number",
    "公开号": "publication_number",
    "专利号": "grant_number",
    "授权号": "grant_number",
    "标题": "title",
    "专利名称": "title",
    "发明名称": "title",
    "摘要": "abstract",
    "权利要求": "claims",
    "权利要求书": "claims",
    "申请人": "applicant",
    "专利权人": "assignee",
    "发明人": "inventor",
    "代理人": "agent",
    "代理机构": "agent",
    "申请日": "filing_date",
    "申请日期": "filing_date",
    "公开日": "publication_date",
    "公开日期": "publication_date",
    "授权公告日": "grant_date",
    "授权日": "grant_date",
    "授权日期": "grant_date",
    "法律状态": "legal_status",
    "当前法律状态": "legal_status",
    "专利类型": "patent_type",
    "国家": "country",
    "申请国家": "country",
    "IPC": "ipc_main",
    "IPC分类号": "ipc_main",
    "主IPC": "ipc_main",
    "IPC主分类号": "ipc_main",
    "CPC": "cpc_main",
    "CPC分类号": "cpc_main",
    "优先权日": "priority_date",
    "优先权号": "priority_number",
    "优先权国家": "priority_country",
    "分类": "category",
    "子分类": "subcategory",
    "技术问题": "technical_problem",
    "技术效果": "technical_effect",
    "技术方案": "technical_solution",
    "是否有风险": "has_risk",
    "风险等级": "risk_level",
    "风险描述": "risk_description",
    "模块": "module",
    "关联模块": "module",
    "应用状态": "application_status",
    "备注": "notes",
    "说明": "notes",
    # P0-10：同族/引用列（虚拟字段，单独处理）
    "同族专利号": "family_members",
    "同族": "family_members",
    "同族公开号": "family_members",
    "同族成员": "family_members",
    "引用专利": "cited_patents",
    "引用专利号": "cited_patents",
    "引用文献": "cited_patents",
    "被引用专利": "citing_patents",
    "被引用专利号": "citing_patents",
}

LEGAL_STATUS_MAP = {
    "授权": LegalStatus.GRANTED,
    "已授权": LegalStatus.GRANTED,
    "有效": LegalStatus.GRANTED,
    "有权": LegalStatus.GRANTED,
    "实质审查": LegalStatus.EXAMINING,
    "实审": LegalStatus.EXAMINING,
    "审中": LegalStatus.EXAMINING,
    "审查中": LegalStatus.EXAMINING,
    "公开": LegalStatus.PUBLISHED,
    "已公开": LegalStatus.PUBLISHED,
    "驳回": LegalStatus.REJECTED,
    "已驳回": LegalStatus.REJECTED,
    "视为撤回": LegalStatus.DEEMED_WITHDRAWN,
    "视撤": LegalStatus.DEEMED_WITHDRAWN,
    "撤回": LegalStatus.WITHDRAWN,
    "已撤回": LegalStatus.WITHDRAWN,
    "终止": LegalStatus.EXPIRED,
    "届满": LegalStatus.EXPIRED,
    "未缴年费": LegalStatus.EXPIRED,
    "放弃": LegalStatus.ABANDONED,
}

PATENT_TYPE_MAP = {
    "发明": PatentType.INVENTION,
    "发明专利": PatentType.INVENTION,
    "实用新型": PatentType.UTILITY_MODEL,
    "外观": PatentType.DESIGN,
    "外观设计": PatentType.DESIGN,
    "PCT": PatentType.PCT,
    "PCT申请": PatentType.PCT,
}

RISK_LEVEL_MAP = {
    "无": RiskLevel.NONE,
    "低": RiskLevel.LOW,
    "中": RiskLevel.MEDIUM,
    "高": RiskLevel.HIGH,
    "极高": RiskLevel.CRITICAL,
}


def _slugify(name: str) -> str:
    """把中文/特殊字符列名转换为 snake_case ascii slug。

    中文按字面保留（去除空白即可），英文转小写下划线。
    """
    name = name.strip().lower()
    # 英文部分转 snake_case
    name = re.sub(r"[\s\-]+", "_", name)
    name = re.sub(r"[^a-z0-9_\u4e00-\u9fa5]", "", name)
    return name or "field"


def _short_hash(text: str, length: int = 6) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:length]


def auto_create_custom_field(db: Session, column_name: str) -> str:
    """未知列自动创建 CustomField，返回 key。

    规则：
    - key = "cf_" + slug(列名)[:20] + "_" + 短哈希（避免冲突）
    - 字段类型默认 text，group_name="导入字段"
    - 已存在同名 CustomField 时直接返回其 key
    """
    column_name = column_name.strip()
    # 优先按 name 找现有 CustomField
    existing = db.query(CustomField).filter(CustomField.name == column_name).first()
    if existing:
        return existing.key

    slug = _slugify(column_name)[:20]
    key = f"{CUSTOM_FIELD_KEY_PREFIX}{slug}_{_short_hash(column_name)}"

    # 极端情况：key 冲突，加后缀
    suffix = 1
    while db.query(CustomField).filter(CustomField.key == key).first():
        key = f"{CUSTOM_FIELD_KEY_PREFIX}{slug}_{_short_hash(column_name + str(suffix))}"
        suffix += 1

    cf = CustomField(
        key=key,
        name=column_name,
        field_type=CustomFieldType.TEXT,
        group_name="导入字段",
        description=f"导入时自动创建，源列名：{column_name}",
        is_active=True,
    )
    db.add(cf)
    db.commit()
    return key


def auto_create_view_local_field(db: Session, view, column_name: str) -> str:
    """P1-15：未知列在指定视图下创建为本地字段（vlf_ 前缀），返回 key。

    与 auto_create_custom_field 不同：vlf_ 字段不污染大表 custom_fields，
    仅在该视图内可见。适用于"导入到小表"的场景。

    规则：
    - key = "vlf_" + slug(列名)[:20] + "_" + 短哈希
    - 字段类型默认 text
    - 已存在同名 vlf_ 字段时直接返回其 key
    """
    from app.services.view_service import ViewService
    column_name = column_name.strip()

    # 查现有同名 vlf_ 字段
    for lf in view.local_fields:
        if lf.name == column_name:
            return lf.key

    slug = _slugify(column_name)[:20]
    raw_key = f"vlf_{slug}_{_short_hash(column_name)}"
    # ViewService.create_local_field 会自动加 vlf_ 前缀（如果没加的话）
    # 此处我们直接传完整 key（以 vlf_ 开头时不会再加前缀）
    try:
        field = ViewService.create_local_field(
            db, view,
            key=raw_key,
            name=column_name,
            field_type="text",
            description=f"导入时自动创建，源列名：{column_name}",
            is_required=False,
        )
        return field.key
    except ValueError:
        # 极小概率冲突：直接返回原 key（后续值会写入失败，但不影响主流程）
        return raw_key


class ImportService:
    @staticmethod
    def parse_excel(file_content: bytes, filename: str) -> tuple[pd.DataFrame, list[str]]:
        if filename.endswith(".xls"):
            df = pd.read_excel(BytesIO(file_content), engine="xlrd", dtype=str)
        else:
            df = pd.read_excel(BytesIO(file_content), engine="openpyxl", dtype=str)

        df = df.fillna("")
        columns = [str(c).strip() for c in df.columns]
        df.columns = columns

        return df, columns

    @staticmethod
    def suggest_mapping(
        columns: list[str],
        db: Session,
        view_id: Optional[int] = None,
    ) -> dict[str, str]:
        """对每列生成映射目标。

        返回结构：
            {
                "列名": "field_key"  # 系统字段 / cf_xxx / vlf_xxx
            }
        - 未传入 view_id：未知列自动创建 CustomField（cf_ 前缀，污染大表）
        - 传入 view_id（P1-15）：未知列自动创建视图本地字段（vlf_ 前缀，不污染大表）
        """
        mapping: dict[str, str] = {}

        custom_fields = db.query(CustomField).all()
        custom_field_by_name = {cf.name: cf.key for cf in custom_fields}

        # P1-15：若指定 view_id，预加载视图与现有本地字段
        view = None
        existing_local_field_names: set[str] = set()
        if view_id is not None:
            from app.models import PatentView
            view = db.query(PatentView).filter(PatentView.id == view_id).first()
            if view:
                existing_local_field_names = {lf.name for lf in view.local_fields}

        for col in columns:
            col_clean = col.strip()
            if not col_clean:
                continue

            # 1. 完全命中标准字段映射
            if col_clean in STANDARD_FIELD_MAPPINGS:
                mapping[col_clean] = STANDARD_FIELD_MAPPINGS[col_clean]
                continue

            # 2. 已有同名自定义字段
            if col_clean in custom_field_by_name:
                mapping[col_clean] = custom_field_by_name[col_clean]
                continue

            # 3. 模糊匹配标准字段（"包含"关系）
            matched = False
            for std_name, field_key in STANDARD_FIELD_MAPPINGS.items():
                if std_name in col_clean or col_clean in std_name:
                    mapping[col_clean] = field_key
                    matched = True
                    break
            if matched:
                continue

            # 4. 未知列处理
            if view is not None:
                # P1-15：导入到视图 → 建为 vlf_ 本地字段
                if col_clean in existing_local_field_names:
                    # 已有同名本地字段，复用
                    for lf in view.local_fields:
                        if lf.name == col_clean:
                            mapping[col_clean] = lf.key
                            break
                else:
                    try:
                        new_key = auto_create_view_local_field(db, view, col_clean)
                        mapping[col_clean] = new_key
                        existing_local_field_names.add(col_clean)
                    except Exception:
                        pass
            else:
                # 未指定视图：维持原有行为，建为 CustomField
                try:
                    new_key = auto_create_custom_field(db, col_clean)
                    mapping[col_clean] = new_key
                    custom_field_by_name[col_clean] = new_key
                except Exception:
                    pass

        return mapping

    @staticmethod
    def _parse_date(value: Any) -> Optional[datetime.date]:
        if not value or str(value).strip() == "":
            return None
        try:
            if isinstance(value, (datetime, pd.Timestamp)):
                return value.date()
            if isinstance(value, str):
                value = value.strip()
                for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日", "%Y%m%d"]:
                    try:
                        return datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        if not value:
            return False
        val = str(value).strip().lower()
        return val in ["是", "有", "yes", "true", "1", "y", "高风险", "风险"]

    @staticmethod
    def _map_legal_status(value: str) -> LegalStatus:
        if not value:
            return LegalStatus.UNKNOWN
        val = value.strip()
        if val in LEGAL_STATUS_MAP:
            return LEGAL_STATUS_MAP[val]
        return LegalStatus.UNKNOWN

    @staticmethod
    def _map_patent_type(value: str) -> PatentType:
        if not value:
            return PatentType.INVENTION
        val = value.strip()
        if val in PATENT_TYPE_MAP:
            return PATENT_TYPE_MAP[val]
        return PatentType.INVENTION

    @staticmethod
    def _map_risk_level(value: str) -> RiskLevel:
        if not value:
            return RiskLevel.NONE
        val = value.strip()
        if val in RISK_LEVEL_MAP:
            return RISK_LEVEL_MAP[val]
        return RiskLevel.NONE

    @staticmethod
    def _row_to_patent_data(
        row: dict,
        mapping: dict,
        db: Session,
        custom_fields_cache: dict | None = None,
    ) -> tuple[dict, dict]:
        """把 Excel 单行 + 列映射 转换为 Patent 字段字典 + 虚拟字段字典。

        返回:
            (patent_data, virtual_data)
            - patent_data: 可直接用于创建/更新 Patent
              * 含 custom_fields 子 dict（cf_xxx 字段）
              * 含 view_local_fields 子 dict（vlf_xxx 字段，P1-15 新增）
            - virtual_data: {"family_numbers": [...], "cited_numbers": [...], "citing_numbers": [...]}
        """
        data: dict[str, Any] = {}
        custom: dict[str, Any] = {}
        view_local: dict[str, Any] = {}  # P1-15：视图本地字段值
        virtual: dict[str, list[str]] = {
            "family_numbers": [],
            "cited_numbers": [],
            "citing_numbers": [],
        }

        if custom_fields_cache is None:
            all_custom_fields = {cf.key: cf for cf in db.query(CustomField).all()}
        else:
            all_custom_fields = custom_fields_cache

        for excel_col, field_key in mapping.items():
            value = row.get(excel_col, "")
            if value is None:
                value = ""
            value = str(value).strip()
            if value == "":
                continue

            # 虚拟字段：解析专利号列表，不写入 Patent 主表
            if field_key == "family_members":
                virtual["family_numbers"] = parse_patent_numbers(value)
                continue
            if field_key == "cited_patents":
                virtual["cited_numbers"] = parse_patent_numbers(value)
                continue
            if field_key == "citing_patents":
                virtual["citing_numbers"] = parse_patent_numbers(value)
                continue

            # P1-15：视图本地字段（vlf_ 前缀）单独收集
            if field_key.startswith("vlf_"):
                view_local[field_key] = value
                continue

            # 自定义字段
            if field_key in all_custom_fields:
                custom[field_key] = value
                continue

            # 系统字段类型转换
            if field_key in ["filing_date", "publication_date", "grant_date",
                           "priority_date", "legal_status_date"]:
                parsed = ImportService._parse_date(value)
                if parsed:
                    data[field_key] = parsed
            elif field_key == "has_risk":
                data[field_key] = ImportService._parse_bool(value)
            elif field_key == "legal_status":
                data[field_key] = ImportService._map_legal_status(value)
            elif field_key == "patent_type":
                data[field_key] = ImportService._map_patent_type(value)
            elif field_key == "risk_level":
                data[field_key] = ImportService._map_risk_level(value)
            elif field_key == "country":
                data[field_key] = value.upper() if value else "CN"
            elif field_key in ["title", "abstract", "claims", "applicant", "inventor",
                              "assignee", "agent", "application_number", "publication_number",
                              "grant_number", "ipc_main", "ipc_all", "cpc_main", "cpc_all",
                              "priority_number", "priority_country", "category", "subcategory",
                              "technical_problem", "technical_effect", "technical_solution",
                              "risk_description", "module", "application_status",
                              "scope_description", "notes", "legal_status_details"]:
                data[field_key] = value

        data["custom_fields"] = custom
        if view_local:
            data["view_local_fields"] = view_local
        return data, virtual
