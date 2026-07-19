import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from io import BytesIO

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models import (
    Patent, ImportBatch, FieldMapping, ImportBatchStatus,
    CustomField, CustomFieldType, Product, LegalStatus, PatentType, RiskLevel
)
from app.schemas.schemas import FieldMappingConfig, ImportRequest
from app.services.patent_service import PatentService
from app.services.merge_service import merge_patent_data
from app.services.relation_service import (
    parse_patent_numbers,
    process_family_members,
    process_citations,
    process_citing_patents,
)


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
    def suggest_mapping(columns: list[str], db: Session) -> dict[str, str]:
        """对每列生成映射目标。

        返回结构：
            {
                "列名": "field_key"  # 系统字段或 cf_xxx 自定义字段
            }
        未匹配列自动创建 CustomField，按设计文档 3.3。
        """
        mapping: dict[str, str] = {}

        custom_fields = db.query(CustomField).all()
        custom_field_by_name = {cf.name: cf.key for cf in custom_fields}

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

            # 4. 未知列：自动创建 CustomField
            try:
                new_key = auto_create_custom_field(db, col_clean)
                mapping[col_clean] = new_key
                # 刷新缓存，避免同一次导入重复创建
                custom_field_by_name[col_clean] = new_key
            except Exception:
                # 创建失败则忽略该列
                pass

        return mapping

    @staticmethod
    def preview_import(file_content: bytes, filename: str, db: Session) -> dict:
        df, columns = ImportService.parse_excel(file_content, filename)
        suggested_mapping = ImportService.suggest_mapping(columns, db)

        sample_rows = df.head(10).to_dict("records")
        sample_rows = [{str(k): str(v) for k, v in row.items()} for row in sample_rows]

        return {
            "columns": columns,
            "sample_rows": sample_rows,
            "total_rows": len(df),
            "suggested_mapping": suggested_mapping,
        }

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
    ) -> tuple[dict, dict]:
        """把 Excel 单行 + 列映射 转换为 Patent 字段字典 + 虚拟字段字典。

        返回:
            (patent_data, virtual_data)
            - patent_data: 可直接传给 PatentService.create_patent / merge_patent_data
            - virtual_data: {"family_numbers": [...], "cited_numbers": [...], "citing_numbers": [...]}
        """
        data: dict[str, Any] = {}
        custom: dict[str, Any] = {}
        virtual: dict[str, list[str]] = {
            "family_numbers": [],
            "cited_numbers": [],
            "citing_numbers": [],
        }

        all_custom_fields = {cf.key: cf for cf in db.query(CustomField).all()}

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
        return data, virtual

    @staticmethod
    def process_import(
        batch_id: int,
        file_content: bytes,
        filename: str,
        mapping: dict,
        options: dict,
        db: Session,
        product_id: Optional[int] = None,
    ):
        batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
        if not batch:
            return

        batch.status = ImportBatchStatus.PROCESSING
        batch.started_at = datetime.now()
        db.commit()

        errors = []
        inserted = 0
        updated = 0
        duplicates = 0
        skipped = 0

        try:
            df, _ = ImportService.parse_excel(file_content, filename)
            batch.total_rows = len(df)
            db.commit()

            update_on_duplicate = options.get("update_on_duplicate", True)
            skip_duplicate = options.get("skip_duplicate", False)

            for idx, (_, row) in enumerate(df.iterrows()):
                try:
                    row_dict = row.to_dict()
                    patent_data, virtual = ImportService._row_to_patent_data(row_dict, mapping, db)

                    if not patent_data.get("title"):
                        skipped += 1
                        continue

                    if product_id:
                        patent_data["product_id"] = product_id

                    country = patent_data.get("country", "CN")
                    app_num = patent_data.get("application_number", "")
                    pub_num = patent_data.get("publication_number", "")

                    existing = PatentService.find_duplicate(
                        db,
                        application_number=app_num,
                        publication_number=pub_num,
                        country=country,
                        title=patent_data.get("title"),
                    )

                    if existing:
                        duplicates += 1
                        if skip_duplicate:
                            skipped += 1
                        elif update_on_duplicate:
                            # Wiki 式增量合并：仅更新非空新值，标注类字段保留
                            merged = merge_patent_data(existing, patent_data)
                            PatentService.update_patent(db, existing, merged)
                            updated += 1
                            current_patent = existing
                        else:
                            skipped += 1
                            current_patent = None
                    else:
                        patent = Patent(**patent_data)
                        patent.source_batch_id = batch_id
                        patent.source_row = idx + 1
                        db.add(patent)
                        db.flush()
                        inserted += 1
                        current_patent = patent

                    # P0-10：同族/引用关系入库
                    if current_patent is not None:
                        try:
                            if virtual["family_numbers"]:
                                process_family_members(db, current_patent, virtual["family_numbers"])
                            if virtual["cited_numbers"]:
                                process_citations(db, current_patent, virtual["cited_numbers"])
                            if virtual["citing_numbers"]:
                                process_citing_patents(db, current_patent, virtual["citing_numbers"])
                        except Exception:
                            # 关系入库失败不影响主表导入
                            pass

                    batch.processed_rows = idx + 1
                    batch.inserted_count = inserted
                    batch.updated_count = updated
                    batch.duplicate_count = duplicates
                    batch.skipped_count = skipped

                    if (idx + 1) % 100 == 0:
                        db.commit()

                except Exception as e:
                    errors.append({
                        "row": idx + 1,
                        "error": str(e),
                        "data": {k: str(v) for k, v in row_dict.items()},
                    })
                    batch.error_count += 1

            db.commit()

            batch.status = ImportBatchStatus.COMPLETED
            batch.completed_at = datetime.now()
            batch.errors = errors if errors else None

        except Exception as e:
            batch.status = ImportBatchStatus.FAILED
            batch.completed_at = datetime.now()
            errors.append({"error": str(e)})
            batch.errors = errors

        db.commit()

    @staticmethod
    def create_import_batch(db: Session, filename: str, mapping: dict, options: dict,
                            total_rows: int) -> ImportBatch:
        batch = ImportBatch(
            filename=filename,
            status=ImportBatchStatus.PENDING,
            total_rows=total_rows,
            mapping_config=mapping,
            errors=[],
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)
        return batch

    @staticmethod
    def list_import_batches(db: Session, page: int = 1, page_size: int = 20) -> tuple[list[ImportBatch], int]:
        query = db.query(ImportBatch).order_by(ImportBatch.created_at.desc())
        total = query.count()
        batches = query.offset((page - 1) * page_size).limit(page_size).all()
        return batches, total

    @staticmethod
    def get_import_batch(db: Session, batch_id: int) -> Optional[ImportBatch]:
        return db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
