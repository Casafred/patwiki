from datetime import datetime
from typing import Optional, Any
from io import BytesIO

import pandas as pd
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException
from app.models import (
    CustomField, CustomFieldType, LegalStatus, PatentType, RiskLevel
)
from app.services.field_registry import SYSTEM_FIELD_KEYS
from app.services.relation_service import parse_patent_numbers


# 虚拟字段：不直接写入 Patent 主表，由 relation_service 处理
VIRTUAL_FIELDS = {"family_members", "cited_patents", "citing_patents"}
IMPORT_BLOCKED_FIELDS = {"attachments"}
IMPORT_SKIP_FIELD = "__skip__"

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
    "同族列": "family_members",
    "同族关系": "family_members",
    "同族号码": "family_members",
    "同族公开号": "family_members",
    "同族成员": "family_members",
    "family": "family_members",
    "family members": "family_members",
    "引用专利": "cited_patents",
    "引用专利号": "cited_patents",
    "引用文献": "cited_patents",
    "被引用专利": "citing_patents",
    "被引用专利号": "citing_patents",
    "cited patents": "cited_patents",
    "cited patent numbers": "cited_patents",
    "citing patents": "citing_patents",
    "citing patent numbers": "citing_patents",
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


class ImportService:
    @staticmethod
    def list_sheets(file_content: bytes, filename: str) -> list[str]:
        suffix = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
        if suffix == 'csv':
            return []
        try:
            engine = 'xlrd' if suffix == 'xls' else 'openpyxl'
            workbook = pd.ExcelFile(BytesIO(file_content), engine=engine)
            return [str(name) for name in workbook.sheet_names]
        except Exception as exc:
            raise BadRequestException(f"无法读取 Excel Sheet：{exc}") from exc

    @staticmethod
    def parse_excel(file_content: bytes, filename: str, sheet_name: str | int | None = None) -> tuple[pd.DataFrame, list[str]]:
        suffix = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
        if not file_content:
            raise BadRequestException("上传文件为空")
        if suffix not in {"csv", "xls", "xlsx"}:
            raise BadRequestException("仅支持 .xlsx、.xls 或 .csv 文件")
        try:
            if suffix == "csv":
                try:
                    df = pd.read_csv(BytesIO(file_content), dtype=str, encoding="utf-8-sig")
                except UnicodeDecodeError:
                    df = pd.read_csv(BytesIO(file_content), dtype=str, encoding="gb18030")
            elif suffix == "xls":
                df = pd.read_excel(BytesIO(file_content), engine="xlrd", dtype=str, sheet_name=0 if sheet_name is None else sheet_name)
            else:
                df = pd.read_excel(BytesIO(file_content), engine="openpyxl", dtype=str, sheet_name=0 if sheet_name is None else sheet_name)
        except BadRequestException:
            raise
        except Exception as exc:
            raise BadRequestException(f"无法读取文件，请确认文件未损坏且扩展名正确：{exc}") from exc

        df = df.fillna("")
        columns = [str(c).strip() for c in df.columns]
        df.columns = columns

        return df, columns

    @staticmethod
    def suggest_mapping(columns: list[str], db: Session) -> tuple[dict[str, str], list[dict[str, str]]]:
        """对每列生成映射目标。

        返回结构：
            {
                "列名": "field_key"  # 已注册的系统、虚拟或自定义字段
            }
        未匹配列返回空目标。导入时原始值会作为待治理观察记录保留，
        只有用户在字段治理中显式创建并映射正式字段后才会写入 Patent。
        """
        mapping: dict[str, str] = {}
        mapping_issues: list[dict[str, str]] = []

        custom_fields = db.query(CustomField).all()
        custom_field_by_name = {cf.name: cf.key for cf in custom_fields}

        for col in columns:
            col_clean = col.strip()
            if not col_clean:
                continue

            # 1. 完全命中标准字段映射（含虚拟字段：同族/引用）
            if col_clean in STANDARD_FIELD_MAPPINGS:
                mapping[col_clean] = STANDARD_FIELD_MAPPINGS[col_clean]
                continue

            # 2. 已有同名自定义字段
            if col_clean in custom_field_by_name:
                mapping[col_clean] = custom_field_by_name[col_clean]
                continue

            # 3. 模糊匹配标准字段（"包含"关系）
            #    - 虚拟字段（family_members/cited_patents/citing_patents）必须精确命中
            #    - 含"同族/引用/被引用/family"等关系关键词的列，若未精确命中虚拟字段，
            #      一律作为自定义字段呈现，避免"同族备注"被误配到 notes、
            #      "同族申请日"被误配到 filing_date 等情况。
            RELATION_KEYWORDS = ("同族", "引用", "被引用", "family")
            is_relation_like = any(kw in col_clean.lower() for kw in RELATION_KEYWORDS)
            matched = False
            if not is_relation_like:
                for std_name, field_key in STANDARD_FIELD_MAPPINGS.items():
                    if field_key in VIRTUAL_FIELDS:
                        continue
                    if std_name in col_clean or col_clean in std_name:
                        mapping[col_clean] = field_key
                        matched = True
                        break
            if matched:
                continue

            # 4. 未知列：保留为未映射属性，等待用户后续治理。
            mapping[col_clean] = ""

        return mapping, mapping_issues

    @staticmethod
    def validate_mapping(columns: list[str], mapping: dict[str, str], db: Session) -> list[dict[str, str]]:
        """Return every *blocking* mapping problem before any row can be written.

        空目标允许导入继续进行；其原始单元格值仍会留存在导入证据中。
        ``__skip__`` 是用户明确的跳过标记：原始整行保留，但该列不进入
        待治理观察清单。
        任何未注册的字段都必须被阻止，避免未经治理进入正式数据模型。
        """
        custom_fields = {field.key: field for field in db.query(CustomField).all()}
        issues: list[dict[str, str]] = []
        for column in columns:
            target = (mapping.get(column) or "").strip()
            if not target:
                # 未知字段保留为导入证据。
                continue
            if target == IMPORT_SKIP_FIELD:
                # 用户明确跳过本列。
                continue
            if target in IMPORT_BLOCKED_FIELDS:
                issues.append({"column": column, "target_field": target, "reason": "附件字段需要上传实际文件，不能从 Excel 单元格写入"})
                continue
            if target in VIRTUAL_FIELDS or target in SYSTEM_FIELD_KEYS:
                continue
            custom_field = custom_fields.get(target)
            if not custom_field:
                issues.append({"column": column, "target_field": target, "reason": "目标字段不存在"})
            elif custom_field.field_type == CustomFieldType.FORMULA:
                issues.append({"column": column, "target_field": target, "reason": "公式字段由系统计算，不能导入"})
            elif custom_field.field_type == CustomFieldType.ATTACHMENT:
                issues.append({"column": column, "target_field": target, "reason": "附件字段需要上传实际文件，不能从 Excel 单元格写入"})
        return issues

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
            - virtual_data: {"family_numbers": [...], "cited_numbers": [...], "citing_numbers": [...]}
        """
        data: dict[str, Any] = {}
        custom: dict[str, Any] = {}
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
            if not field_key or field_key == IMPORT_SKIP_FIELD:
                continue
            value = row.get(excel_col, "")
            if value is None:
                value = ""
            raw_value = str(value)
            value = raw_value.strip()
            if value == "":
                continue

            # 虚拟字段：解析专利号列表，不写入 Patent 主表
            if field_key == "family_members":
                virtual["family_numbers"] = list(dict.fromkeys([
                    *virtual["family_numbers"], *parse_patent_numbers(value),
                ]))
                custom[field_key] = _append_relation_raw_value(custom.get(field_key), raw_value)
                continue
            if field_key == "cited_patents":
                virtual["cited_numbers"] = list(dict.fromkeys([
                    *virtual["cited_numbers"], *parse_patent_numbers(value),
                ]))
                custom[field_key] = _append_relation_raw_value(custom.get(field_key), raw_value)
                continue
            if field_key == "citing_patents":
                virtual["citing_numbers"] = list(dict.fromkeys([
                    *virtual["citing_numbers"], *parse_patent_numbers(value),
                ]))
                custom[field_key] = _append_relation_raw_value(custom.get(field_key), raw_value)
                continue

            # 自定义字段
            if field_key in all_custom_fields:
                if all_custom_fields[field_key].field_type in (CustomFieldType.FORMULA, CustomFieldType.ATTACHMENT):
                    raise ValueError(f"字段 '{field_key}' 不支持从 Excel 写入")
                custom[field_key] = value
                continue

            # 系统字段类型转换
            if field_key in ["filing_date", "publication_date", "grant_date",
                           "priority_date", "legal_status_date"]:
                parsed = ImportService._parse_date(value)
                if not parsed:
                    raise ValueError(f"字段 '{excel_col}' 的日期值无法识别：{value}")
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
            else:
                raise ValueError(f"未知的导入目标字段：{field_key}")

        data["custom_fields"] = custom
        return data, virtual


def _append_relation_raw_value(existing: Any, value: str) -> str:
    """保留关系列原始文本；同一规范字段映射多个来源列时不覆盖。"""
    if not existing:
        return value
    if str(existing) == value:
        return str(existing)
    return f"{existing}\n{value}"
