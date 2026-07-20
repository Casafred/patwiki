from typing import Optional, Any
from datetime import datetime, date
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_, desc, text, String

from app.models import (
    Patent, Product, Project, Tag, CustomField,
    patent_tag, patent_project, LegalStatus, PatentType,
    PatentHistory,
)
from app.schemas.schemas import PatentCreate, PatentUpdate
from app.services.field_registry import SYSTEM_FIELD_KEYS, get_all_fields_meta


SYSTEM_FIELDS = {
    "id", "application_number", "publication_number", "grant_number",
    "title", "abstract", "claims", "description_full",
    "applicant", "inventor", "assignee", "agent",
    "filing_date", "publication_date", "grant_date",
    "priority_date", "priority_number", "priority_country",
    "country", "patent_type", "legal_status", "legal_status_date", "legal_status_details",
    "ipc_main", "ipc_all", "cpc_main", "cpc_all",
    "product_id", "category", "subcategory",
    "technical_problem", "technical_effect", "technical_solution",
    "has_risk", "risk_level", "risk_description",
    "module", "application_status", "scope_description", "notes",
    "created_at", "updated_at", "tags", "projects"
}


def _normalize_value(v: Any) -> Any:
    """标准化值用于比较：date/datetime 转 ISO 字符串；None/空串 视为空。"""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bool):
        return v
    return v


def _is_value_changed(old: Any, new: Any) -> bool:
    """判断值是否真正发生变化（空串/None 视为相等）。"""
    return _normalize_value(old) != _normalize_value(new)


def _stringify_value(v: Any) -> Optional[str]:
    """把任意值转为字符串存储到历史记录；None 返回 None。"""
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        import json
        try:
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return str(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


class PatentService:
    @staticmethod
    def get_patent(db: Session, patent_id: int) -> Optional[Patent]:
        return db.query(Patent).options(
            joinedload(Patent.tags),
            joinedload(Patent.projects),
        ).filter(Patent.id == patent_id).first()

    @staticmethod
    def get_patent_by_application_number(db: Session, app_num: str, country: str = "CN") -> Optional[Patent]:
        return db.query(Patent).filter(
            Patent.application_number == app_num,
            Patent.country == country,
        ).first()

    @staticmethod
    def get_patent_by_publication_number(db: Session, pub_num: str, country: str = "CN") -> Optional[Patent]:
        return db.query(Patent).filter(
            Patent.publication_number == pub_num,
            Patent.country == country,
        ).first()

    @staticmethod
    def list_patents(
        db: Session,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        database_id: Optional[int] = None,
        product_id: Optional[int] = None,
        project_id: Optional[int] = None,
        tag_ids: Optional[list[int]] = None,
        legal_status: Optional[str] = None,
        category: Optional[str] = None,
        has_risk: Optional[bool] = None,
        risk_level: Optional[str] = None,
        patent_type: Optional[str] = None,
        country: Optional[str] = None,
        filing_date_from: Optional[date] = None,
        filing_date_to: Optional[date] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = "asc",
        custom_filters: Optional[dict[str, Any]] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> tuple[list[Patent], int]:
        query = db.query(Patent).options(
            joinedload(Patent.tags),
            joinedload(Patent.projects),
        )

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Patent.title.ilike(search_term),
                    Patent.abstract.ilike(search_term),
                    Patent.application_number.ilike(search_term),
                    Patent.publication_number.ilike(search_term),
                    Patent.applicant.ilike(search_term),
                    Patent.inventor.ilike(search_term),
                )
            )

        # 库筛选：P0-11 新增，限定查询范围到某个库
        if database_id is not None:
            query = query.filter(Patent.database_id == database_id)

        if product_id:
            query = query.filter(Patent.product_id == product_id)

        if project_id:
            query = query.join(patent_project).filter(patent_project.c.project_id == project_id)

        if tag_ids:
            for tag_id in tag_ids:
                query = query.join(patent_tag).filter(patent_tag.c.tag_id == tag_id)

        if legal_status:
            query = query.filter(Patent.legal_status == legal_status)

        if category:
            query = query.filter(Patent.category == category)

        if has_risk is not None:
            query = query.filter(Patent.has_risk == has_risk)

        if risk_level:
            query = query.filter(Patent.risk_level == risk_level)

        if patent_type:
            query = query.filter(Patent.patent_type == patent_type)

        if country:
            query = query.filter(Patent.country == country)

        if filing_date_from:
            query = query.filter(Patent.filing_date >= filing_date_from)

        if filing_date_to:
            query = query.filter(Patent.filing_date <= filing_date_to)

        # 统一filters处理：支持系统字段和自定义字段
        if filters:
            for key, filter_val in filters.items():
                if filter_val is None or filter_val == "":
                    continue
                if key in SYSTEM_FIELDS and hasattr(Patent, key):
                    column = getattr(Patent, key)
                    if isinstance(filter_val, dict):
                        if "contains" in filter_val and filter_val["contains"]:
                            query = query.filter(column.cast(String).ilike(f"%{filter_val['contains']}%"))
                        elif "eq" in filter_val and filter_val["eq"] is not None:
                            query = query.filter(column == filter_val["eq"])
                    else:
                        query = query.filter(column.cast(String).ilike(f"%{filter_val}%"))
                else:
                    # 自定义字段
                    if isinstance(filter_val, dict):
                        if "contains" in filter_val and filter_val["contains"]:
                            query = query.filter(
                                func.json_extract(Patent.custom_fields, f'$.{key}').cast(String).ilike(f"%{filter_val['contains']}%")
                            )
                        elif "eq" in filter_val and filter_val["eq"] is not None:
                            query = query.filter(
                                func.json_extract(Patent.custom_fields, f'$.{key}') == str(filter_val["eq"])
                            )
                    else:
                        query = query.filter(
                            func.json_extract(Patent.custom_fields, f'$.{key}').cast(String).ilike(f"%{filter_val}%")
                        )

        # 兼容旧custom_filters
        if custom_filters:
            for key, value in custom_filters.items():
                if value is None or value == "":
                    continue
                if isinstance(value, dict):
                    if "contains" in value and value["contains"]:
                        query = query.filter(
                            func.json_extract(Patent.custom_fields, f'$.{key}').cast(String).ilike(f"%{value['contains']}%")
                        )
                    elif "eq" in value and value["eq"] is not None:
                        query = query.filter(
                            func.json_extract(Patent.custom_fields, f'$.{key}') == str(value["eq"])
                        )
                else:
                    query = query.filter(
                        func.json_extract(Patent.custom_fields, f'$.{key}').cast(String).ilike(f"%{value}%")
                    )

        total = query.count()

        if sort_by:
            if sort_by in SYSTEM_FIELDS:
                column = getattr(Patent, sort_by, None)
                if column is not None:
                    if sort_order == "desc":
                        query = query.order_by(desc(column))
                    else:
                        query = query.order_by(column)
            else:
                json_path = f'$.{sort_by}'
                if sort_order == "desc":
                    query = query.order_by(desc(func.json_extract(Patent.custom_fields, json_path)))
                else:
                    query = query.order_by(func.json_extract(Patent.custom_fields, json_path))
        else:
            query = query.order_by(desc(Patent.created_at))

        query = query.offset((page - 1) * page_size).limit(page_size)
        patents = query.all()

        return patents, total

    @staticmethod
    def create_patent(db: Session, patent_in: PatentCreate) -> Patent:
        data = patent_in.model_dump(exclude_unset=True)
        custom_fields = data.pop("custom_fields", {}) or {}

        patent = Patent(**data)
        patent.custom_fields = custom_fields

        db.add(patent)
        db.commit()
        db.refresh(patent)
        return patent

    @staticmethod
    def update_patent(db: Session, patent: Patent, patent_in: PatentUpdate | dict, source: str = "manual", changed_by: Optional[str] = None) -> Patent:
        if isinstance(patent_in, dict):
            update_data = patent_in
        else:
            update_data = patent_in.model_dump(exclude_unset=True)

        tag_ids = update_data.pop("tag_ids", None)
        project_ids = update_data.pop("project_ids", None)
        custom_fields_data = update_data.pop("custom_fields", None)

        # 字段名 → 显示名映射（用于历史记录的可读性）
        field_display_map: dict[str, str] = {}
        try:
            for fm in get_all_fields_meta(db):
                field_display_map[fm["key"]] = fm.get("name") or fm["key"]
        except Exception:
            pass

        history_entries: list[PatentHistory] = []

        # 系统字段修改
        for field, value in update_data.items():
            if field in SYSTEM_FIELDS and hasattr(patent, field):
                old_value = getattr(patent, field)
                # 比较旧值/新值（标准化处理）
                if not _is_value_changed(old_value, value):
                    continue
                setattr(patent, field, value)
                history_entries.append(PatentHistory(
                    patent_id=patent.id,
                    field_key=field,
                    field_display_name=field_display_map.get(field, field),
                    old_value=_stringify_value(old_value),
                    new_value=_stringify_value(value),
                    source=source,
                    changed_by=changed_by,
                ))

        # 自定义字段修改
        if custom_fields_data is not None:
            current = patent.custom_fields or {}
            for k, v in custom_fields_data.items():
                old_v = current.get(k)
                if not _is_value_changed(old_v, v):
                    continue
                history_entries.append(PatentHistory(
                    patent_id=patent.id,
                    field_key=f"custom_fields.{k}",
                    field_display_name=field_display_map.get(k, k),
                    old_value=_stringify_value(old_v),
                    new_value=_stringify_value(v),
                    source=source,
                    changed_by=changed_by,
                ))
            current.update(custom_fields_data)
            patent.custom_fields = current

        if tag_ids is not None:
            tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all()
            patent.tags = tags

        if project_ids is not None:
            projects = db.query(Project).filter(Project.id.in_(project_ids)).all()
            patent.projects = projects

        db.add(patent)
        # 批量插入历史记录
        for h in history_entries:
            db.add(h)
        db.commit()
        db.refresh(patent)
        return patent

    @staticmethod
    def bulk_update(db: Session, patent_ids: list[int], updates: dict) -> int:
        count = 0
        patents = db.query(Patent).filter(Patent.id.in_(patent_ids)).all()
        for patent in patents:
            PatentService.update_patent(db, patent, updates, source="bulk")
            count += 1
        return count

    @staticmethod
    def delete_patent(db: Session, patent_id: int) -> bool:
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        if not patent:
            return False
        db.delete(patent)
        db.commit()
        return True

    @staticmethod
    def get_stats(db: Session, database_id: Optional[int] = None, product_id: Optional[int] = None) -> dict:
        # 基础过滤条件：按库 / 产品过滤
        def _apply_filter(q):
            if database_id is not None:
                q = q.filter(Patent.database_id == database_id)
            if product_id is not None:
                q = q.filter(Patent.product_id == product_id)
            return q

        total = _apply_filter(db.query(func.count(Patent.id))).scalar()

        status_counts = dict(
            _apply_filter(
                db.query(Patent.legal_status, func.count(Patent.id))
            ).group_by(Patent.legal_status).all()
        )

        type_counts = dict(
            _apply_filter(
                db.query(Patent.patent_type, func.count(Patent.id))
            ).group_by(Patent.patent_type).all()
        )

        # 按产品分布：需要 join Product，但产品过滤时不需要重复
        if product_id is None:
            products_q = db.query(
                Product.id,
                Product.name,
                func.count(Patent.id).label("count"),
            ).outerjoin(Patent, Patent.product_id == Product.id)
            if database_id is not None:
                products_q = products_q.filter((Patent.database_id == database_id) | (Patent.id.is_(None)))
            products = products_q.group_by(Product.id, Product.name).order_by(desc("count")).limit(20).all()
            product_counts = [{"id": p.id, "name": p.name, "count": p.count} for p in products]
        else:
            # 单产品时无需分组
            product_counts = [{"id": product_id, "name": "", "count": total}]

        category_counts = dict(
            _apply_filter(
                db.query(Patent.category, func.count(Patent.id))
            ).filter(Patent.category.isnot(None)).group_by(Patent.category).all()
        )

        risk_counts = dict(
            _apply_filter(
                db.query(Patent.risk_level, func.count(Patent.id))
            ).group_by(Patent.risk_level).all()
        )

        inventors_q = db.query(
            Patent.inventor,
            func.count(Patent.id).label("count"),
        ).filter(Patent.inventor.isnot(None))
        inventors_q = _apply_filter(inventors_q)
        inventors = inventors_q.group_by(Patent.inventor).order_by(desc("count")).limit(20).all()
        top_inventors = [{"name": i.inventor, "count": i.count} for i in inventors]

        applicants_q = db.query(
            Patent.applicant,
            func.count(Patent.id).label("count"),
        ).filter(Patent.applicant.isnot(None))
        applicants_q = _apply_filter(applicants_q)
        applicants = applicants_q.group_by(Patent.applicant).order_by(desc("count")).limit(20).all()
        top_applicants = [{"name": a.applicant, "count": a.count} for a in applicants]

        # 按 IPC 主分类分布（新增）
        ipc_q = db.query(
            Patent.ipc_main,
            func.count(Patent.id).label("count"),
        ).filter(Patent.ipc_main.isnot(None))
        ipc_q = _apply_filter(ipc_q)
        ipcs = ipc_q.group_by(Patent.ipc_main).order_by(desc("count")).limit(15).all()
        top_ipcs = [{"code": r.ipc_main, "count": r.count} for r in ipcs]

        # 按国别分布（新增）
        country_q = db.query(
            Patent.country,
            func.count(Patent.id).label("count"),
        )
        country_q = _apply_filter(country_q)
        countries = country_q.group_by(Patent.country).order_by(desc("count")).all()
        by_country = {str(c.country or '未知'): c.count for c in countries}

        filing_trend_raw = db.query(
            func.strftime("%Y", Patent.filing_date).label("year"),
            func.count(Patent.id).label("count"),
        ).filter(Patent.filing_date.isnot(None))
        filing_trend_raw = _apply_filter(filing_trend_raw)
        filing_trend_raw = filing_trend_raw.group_by("year").order_by("year").all()
        filing_trend = [{"year": r.year, "count": r.count} for r in filing_trend_raw]

        return {
            "total_patents": total,
            "by_legal_status": {str(k): v for k, v in status_counts.items()},
            "by_patent_type": {str(k): v for k, v in type_counts.items()},
            "by_product": product_counts,
            "by_category": {str(k): v for k, v in category_counts.items() if k},
            "by_risk_level": {str(k): v for k, v in risk_counts.items()},
            "top_inventors": top_inventors,
            "top_applicants": top_applicants,
            "top_ipcs": top_ipcs,
            "by_country": by_country,
            "filing_trend": filing_trend,
        }

    @staticmethod
    def find_duplicate(
        db: Session,
        application_number: Optional[str] = None,
        publication_number: Optional[str] = None,
        country: str = "CN",
        title: Optional[str] = None,
    ) -> Optional[Patent]:
        if application_number:
            existing = PatentService.get_patent_by_application_number(db, application_number.strip(), country)
            if existing:
                return existing

        if publication_number:
            existing = PatentService.get_patent_by_publication_number(db, publication_number.strip(), country)
            if existing:
                return existing

        return None
