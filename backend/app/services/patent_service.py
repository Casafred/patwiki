from typing import Optional, Any
from datetime import datetime, date
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_, desc, text, String

from app.models import (
    Patent, Product, Project, Tag, CustomField,
    patent_tag, patent_project, LegalStatus, PatentType,
    PatentHistory, PatentProjectLink,
    ProjectRole, RiskLevel, RelationType, DocumentRole,
)
from app.schemas.schemas import PatentCreate, PatentUpdate
from app.services.field_registry import SYSTEM_FIELD_KEYS, get_all_fields_meta
from app.core.exceptions import BadRequestException


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
    "created_at", "updated_at", "tags", "projects",
    "view_id",
}

# These fields remain readable for legacy views, but structured RiskCase and
# RiskAssessmentVersion are now the only supported write path.
RISK_PROJECTION_FIELDS = {"has_risk", "risk_level", "risk_description"}


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
        group_by_family: bool = False,
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

        # P2-8：同族聚拢模式 —— 把同族专利排在一起（family_id 非空的在前，按 family_id 分组，组内按申请日倒序）
        if group_by_family:
            query = query.order_by(
                Patent.family_id.is_(None),
                Patent.family_id.asc(),
                desc(Patent.filing_date),
                Patent.id.asc(),
            )
        elif sort_by:
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

        # P2-8：同族聚拢模式下，附加 family_size（该族成员数，含自身）
        # 用单次 GROUP BY 查询避免 N+1
        if group_by_family and patents:
            family_ids = list({p.family_id for p in patents if p.family_id is not None})
            if family_ids:
                size_rows = db.query(
                    Patent.family_id.label("fid"),
                    func.count(Patent.id).label("cnt"),
                ).filter(Patent.family_id.in_(family_ids)).group_by(Patent.family_id).all()
                size_map = {row.fid: row.cnt for row in size_rows}
            else:
                size_map = {}
            for p in patents:
                p.family_size = size_map.get(p.family_id) if p.family_id is not None else None

        return patents, total

    @staticmethod
    def create_patent(db: Session, patent_in: PatentCreate) -> Patent:
        data = patent_in.model_dump(exclude_unset=True)
        custom_fields = data.pop("custom_fields", {}) or {}

        legacy_risk_values = {
            "has_risk": data.pop("has_risk", None),
            "risk_level": data.pop("risk_level", None),
            "risk_description": data.pop("risk_description", None),
        }
        if (
            legacy_risk_values["has_risk"] is True
            or legacy_risk_values["risk_level"] not in (None, "none")
            or legacy_risk_values["risk_description"] not in (None, "")
        ):
            raise BadRequestException(
                "风险兼容投影不可直接写入，请先创建专利，再通过风险案例追加结构化评估"
            )

        patent = Patent(**data)
        patent.custom_fields = custom_fields

        db.add(patent)
        db.flush()
        from app.services.patent_identity_service import ensure_patent_identifiers
        ensure_patent_identifiers(db, patent, source_system="manual")
        db.commit()
        db.refresh(patent)
        from app.services.formula_service import FormulaService
        FormulaService.recalculate_patent(db, patent)
        from app.services.automation_service import AutomationEngine
        AutomationEngine.on_event(db, "record_created", patent_id=patent.id)
        return patent

    @staticmethod
    def update_patent(
        db: Session,
        patent: Patent,
        patent_in: PatentUpdate | dict,
        source: str = "manual",
        changed_by: Optional[str] = None,
        source_view_id: Optional[int] = None,
        source_view_name: Optional[str] = None,
    ) -> Patent:
        """更新专利字段并写入历史记录。

        参数:
            source: 修改来源（manual/import/ai/bulk/api/promote）
            changed_by: 修改人用户名
            source_view_id: 来源小表视图 ID（P0-13）：在某个视图中编辑时传入，
                            用于追溯"这个值是从哪个小表改的"
            source_view_name: 来源视图名（冗余存储，视图删除后仍可读）
        """
        if isinstance(patent_in, dict):
            update_data = dict(patent_in)
        else:
            update_data = patent_in.model_dump(exclude_unset=True)

        tag_ids = update_data.pop("tag_ids", None)
        project_ids = update_data.pop("project_ids", None)
        custom_fields_data = update_data.pop("custom_fields", None)

        forbidden_projection_fields = RISK_PROJECTION_FIELDS.intersection(update_data)
        if forbidden_projection_fields:
            raise BadRequestException(
                "风险兼容投影不可直接编辑，请通过风险案例追加结构化评估："
                + ", ".join(sorted(forbidden_projection_fields))
            )

        # 字段名 → 显示名映射（用于历史记录的可读性）
        field_display_map: dict[str, str] = {}
        try:
            for fm in get_all_fields_meta(db):
                field_display_map[fm["key"]] = fm.get("name") or fm["key"]
        except Exception:
            pass

        history_entries: list[PatentHistory] = []
        changed_fields: set[str] = set()

        def _make_history(field: str, old_value, new_value) -> PatentHistory:
            """构造历史记录（自动注入来源视图信息）。"""
            return PatentHistory(
                patent_id=patent.id,
                field_key=field,
                field_display_name=field_display_map.get(
                    field.replace("custom_fields.", "") if field.startswith("custom_fields.") else field,
                    field,
                ),
                old_value=_stringify_value(old_value),
                new_value=_stringify_value(new_value),
                source=source,
                changed_by=changed_by,
                source_view_id=source_view_id,
                source_view_name=source_view_name,
            )

        # 系统字段修改
        for field, value in update_data.items():
            if field in SYSTEM_FIELDS and hasattr(patent, field):
                old_value = getattr(patent, field)
                # 比较旧值/新值（标准化处理）
                if not _is_value_changed(old_value, value):
                    continue
                setattr(patent, field, value)
                history_entries.append(_make_history(field, old_value, value))
                changed_fields.add(field)

        # 自定义字段修改
        if custom_fields_data is not None:
            # JSON 列没有 MutableDict 追踪，先复制再赋值才能稳定触发 SQLAlchemy 更新。
            current = dict(patent.custom_fields or {})
            for k, v in custom_fields_data.items():
                old_v = current.get(k)
                if not _is_value_changed(old_v, v):
                    continue
                history_entries.append(_make_history(f"custom_fields.{k}", old_v, v))
                changed_fields.add(k)
            current.update(custom_fields_data)
            patent.custom_fields = current

        if tag_ids is not None:
            tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all()
            patent.tags = tags

        if project_ids is not None:
            PatentService.set_patent_projects(db, patent, project_ids, commit=False)

        from app.services.patent_identity_service import ensure_patent_identifiers
        ensure_patent_identifiers(db, patent, source_system=source)
        db.add(patent)
        # 批量插入历史记录
        for h in history_entries:
            db.add(h)
        db.commit()
        db.refresh(patent)
        if changed_fields:
            from app.services.formula_service import FormulaService
            FormulaService.on_field_changed(db, patent, changed_fields)
            from app.services.automation_service import AutomationEngine
            AutomationEngine.on_event(db, "field_changed", patent_id=patent.id, field_changes=changed_fields)
        return patent

    @staticmethod
    def set_patent_projects(
        db: Session,
        patent: Patent,
        project_ids: list[int] | None = None,
        link_specs: list[dict[str, Any]] | None = None,
        commit: bool = True,
    ) -> Patent:
        """以专利为中心维护项目关系，校验后整体替换并立即提交。

        关系维护有独立 API，详情页不必先进入整篇专利编辑态；不存在的项目
        会明确报错，不能静默丢失用户选择。
        """
        if link_specs is not None:
            requested_links = link_specs
        else:
            # Keep the legacy project_ids API compatible without discarding
            # metadata on relationships that remain attached.
            existing_links = {
                link.project_id: link
                for link in db.query(PatentProjectLink).filter(
                    PatentProjectLink.patent_id == patent.id,
                ).all()
            }
            requested_links = []
            for project_id in (project_ids or []):
                existing = existing_links.get(project_id)
                if existing is None:
                    requested_links.append({"project_id": project_id})
                else:
                    requested_links.append({
                        "project_id": project_id,
                        "role": existing.role.value if existing.role else None,
                        "relation_type": existing.relation_type.value if existing.relation_type else None,
                        "risk_level": existing.risk_level.value if existing.risk_level else None,
                        "document_role": existing.document_role.value if existing.document_role else None,
                        "relevance_score": existing.relevance_score,
                        "importance": existing.importance,
                        "notes": existing.notes,
                        "assigned_to_id": existing.assigned_to_id,
                    })

        normalized_links: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        try:
            for spec in requested_links:
                project_id = int(spec.get("project_id"))
                if project_id in seen_ids:
                    continue
                seen_ids.add(project_id)
                normalized_links.append({**spec, "project_id": project_id})
        except (AttributeError, TypeError, ValueError) as exc:
            raise BadRequestException("项目关联中的 project_id 无效，未更新关联") from exc

        projects = []
        normalized_ids = [spec["project_id"] for spec in normalized_links]
        if normalized_ids:
            projects = db.query(Project).filter(Project.id.in_(normalized_ids)).all()
            found_ids = {project.id for project in projects}
            missing_ids = [project_id for project_id in normalized_ids if project_id not in found_ids]
            if missing_ids:
                raise BadRequestException(f"项目不存在，未更新关联：{missing_ids}")

        def enum_value(spec: dict[str, Any], key: str, enum_type, default):
            raw = spec.get(key)
            if raw in (None, ""):
                return default
            try:
                return enum_type(raw)
            except ValueError as exc:
                raise BadRequestException(f"项目关联字段 {key} 值无效：{raw}") from exc

        normalized_rows: list[dict[str, Any]] = []
        for spec in normalized_links:
            relevance_score = spec.get("relevance_score")
            if relevance_score is not None:
                try:
                    relevance_score = int(relevance_score)
                except (TypeError, ValueError) as exc:
                    raise BadRequestException("项目关联 relevance_score 必须是数字") from exc
                if not 0 <= relevance_score <= 100:
                    raise BadRequestException("项目关联 relevance_score 必须在 0-100 之间")
            # Validate and normalize every value before touching existing rows.
            normalized_rows.append({
                "project_id": spec["project_id"],
                "role": enum_value(spec, "role", ProjectRole, ProjectRole.REFERENCE),
                "relation_type": enum_value(spec, "relation_type", RelationType, RelationType.REFERENCE),
                "risk_level": enum_value(spec, "risk_level", RiskLevel, RiskLevel.NONE),
                "document_role": enum_value(spec, "document_role", DocumentRole, DocumentRole.OTHER),
                "relevance_score": relevance_score,
                "importance": spec.get("importance"),
                "notes": spec.get("notes"),
                "assigned_to_id": spec.get("assigned_to_id"),
            })

        # Replace relationship rows explicitly so relation metadata is not lost
        # when the detail page adds or removes a project.
        existing_rows = db.query(PatentProjectLink).filter(
            PatentProjectLink.patent_id == patent.id,
        ).all()
        for existing_row in existing_rows:
            db.delete(existing_row)
        # SQLite checks the unique (patent_id, project_id) constraint during
        # INSERT; flush deletions before recreating retained project links.
        db.flush()
        for spec in normalized_rows:
            db.add(PatentProjectLink(
                patent_id=patent.id,
                project_id=spec["project_id"],
                role=spec["role"],
                relation_type=spec["relation_type"],
                risk_level=spec["risk_level"],
                document_role=spec["document_role"],
                relevance_score=spec["relevance_score"],
                importance=spec.get("importance"),
                notes=spec.get("notes"),
                assigned_to_id=spec.get("assigned_to_id"),
            ))
        db.expire(patent, ["projects"])
        db.add(patent)
        if commit:
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
    def bulk_tag(
        db: Session,
        patent_ids: list[int],
        tag_ids: list[int],
        mode: str = "add",
    ) -> int:
        """批量打标签/移除标签。

        mode:
            - add:    把指定标签追加到所选专利（保留原有标签）
            - remove: 从所选专利移除指定标签
            - replace: 用指定标签替换所选专利的全部标签
        """
        from app.models import Tag
        tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all() if tag_ids else []
        tag_set = set(tags)
        patents = db.query(Patent).filter(Patent.id.in_(patent_ids)).all()
        count = 0
        for patent in patents:
            current = set(patent.tags or [])
            if mode == "add":
                new_tags = current | tag_set
            elif mode == "remove":
                new_tags = current - tag_set
            elif mode == "replace":
                new_tags = tag_set
            else:
                continue
            patent.tags = list(new_tags)
            db.add(patent)
            count += 1
        db.commit()
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
