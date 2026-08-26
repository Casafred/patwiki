from typing import Optional, Any
from copy import deepcopy
from datetime import datetime, date
import json
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy import func, or_, and_, desc, text, String

from app.models import (
    Patent, Product, Project, Tag, CustomField,
    patent_tag, patent_project, LegalStatus, PatentType,
    PatentHistory, PatentProjectLink,
    FieldObservation,
    ProjectRole, RiskLevel, RelationType, DocumentRole,
)
from app.schemas.schemas import PatentCreate, PatentUpdate
from app.services.field_registry import (
    RELATION_FIELD_KEYS,
    SYSTEM_FIELD_KEYS,
    get_pending_import_fields,
    temporary_import_field_key,
    get_all_fields_meta,
)
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

SEARCH_TEXT_FIELDS = (
    "application_number", "publication_number", "grant_number", "title",
    "abstract", "claims", "description_full", "applicant", "inventor",
    "assignee", "agent", "priority_number", "priority_country", "country",
    "patent_type", "legal_status", "legal_status_details", "ipc_main",
    "ipc_all", "cpc_main", "cpc_all", "category", "subcategory",
    "technical_problem", "technical_effect", "technical_solution",
    "risk_description", "risk_level", "module", "application_status",
    "scope_description", "notes", "search_vector",
)
FILTER_OPERATORS = {"contains", "eq", "starts_with", "ends_with", "is_empty", "is_not_empty"}

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


def _parse_filter_condition(filter_value: Any) -> tuple[str, Any] | None:
    """Accept both the current {operator: value} and the legacy string form."""
    if isinstance(filter_value, dict):
        operator = str(filter_value.get("operator") or "").strip()
        if operator in FILTER_OPERATORS:
            return operator, filter_value.get("value")
        for candidate in FILTER_OPERATORS:
            if candidate in filter_value:
                return candidate, filter_value.get(candidate)
        return None
    if filter_value is None or filter_value == "":
        return None
    return "contains", filter_value


def _apply_filter_expression(expression, operator: str, value: Any):
    """Build one Excel-style predicate for a SQL column or JSON expression."""
    text_expression = expression.cast(String)
    if operator == "is_empty":
        return or_(expression.is_(None), text_expression == "")
    if operator == "is_not_empty":
        return and_(expression.isnot(None), text_expression != "")
    if value is None:
        return None
    value_text = str(value)
    if operator == "contains":
        return text_expression.ilike(f"%{value_text}%")
    if operator == "starts_with":
        return text_expression.ilike(f"{value_text}%")
    if operator == "ends_with":
        return text_expression.ilike(f"%{value_text}")
    if operator == "eq":
        return func.lower(text_expression) == value_text.strip().lower()
    return None


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
        patent_ids: Optional[list[int]] = None,
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
            joinedload(Patent.family),
        )

        # The top search is intentionally broad: it is the database-level
        # retrieval path, while column filters provide precise constraints.
        # JSON casts cover custom and AI fields, including fields added after
        # this service was released.
        if search:
            search_term = f"%{search}%"
            # SQLAlchemy's SQLite JSON serializer stores non-ASCII characters
            # as \uXXXX escapes. Search both the JSON text and its serialized
            # representation so arbitrary custom/AI field values remain
            # searchable without a fixed field registry.
            serialized_search = json.dumps(search, ensure_ascii=True)[1:-1]
            json_search_term = f"%{serialized_search}%"
            search_expressions = [
                getattr(Patent, field).cast(String).ilike(search_term)
                for field in SEARCH_TEXT_FIELDS
                if hasattr(Patent, field)
            ]
            search_expressions.extend([
                Patent.custom_fields.cast(String).ilike(search_term),
                Patent.custom_fields.cast(String).ilike(json_search_term),
                Patent.ai_fields.cast(String).ilike(search_term),
                Patent.ai_fields.cast(String).ilike(json_search_term),
                Patent.projects.any(Project.name.ilike(search_term)),
                Patent.tags.any(Tag.name.ilike(search_term)),
            ])
            query = query.filter(or_(*search_expressions))

        # Placeholder identities are relation-resolution evidence, not user
        # facing rows.  They remain queryable from family/citation detail APIs.
        query = query.filter(Patent.title != "待补全")

        # 库筛选：P0-11 新增，限定查询范围到某个库
        if database_id is not None:
            query = query.filter(Patent.database_id == database_id)

        if patent_ids is not None:
            normalized_ids = list(dict.fromkeys(int(item) for item in patent_ids))
            # An explicitly empty selection must export zero rows, never the
            # entire database. This is also the guard against a UI selection
            # bug silently becoming a full-library export.
            query = query.filter(Patent.id.in_(normalized_ids)) if normalized_ids else query.filter(False)

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

        # 统一 filters 处理：每个字段叠加为 AND；一个字段的 custom/AI
        # 投影为 OR。 This keeps Excel-style filters consistent for all fields.
        if filters:
            for key, filter_val in filters.items():
                condition = _parse_filter_condition(filter_val)
                if condition is None:
                    continue
                operator, value = condition
                if key in SYSTEM_FIELDS and hasattr(Patent, key):
                    predicate = _apply_filter_expression(getattr(Patent, key), operator, value)
                    if predicate is not None:
                        query = query.filter(predicate)
                else:
                    custom_expression = func.json_extract(Patent.custom_fields, f'$.{key}')
                    ai_expression = func.json_extract(Patent.ai_fields, f'$.{key}')
                    custom_predicate = _apply_filter_expression(custom_expression, operator, value)
                    ai_predicate = _apply_filter_expression(ai_expression, operator, value)
                    if custom_predicate is not None and ai_predicate is not None:
                        query = query.filter(
                            and_(custom_predicate, ai_predicate)
                            if operator == "is_empty"
                            else or_(custom_predicate, ai_predicate)
                        )

        # 兼容旧 custom_filters
        if custom_filters:
            for key, value in custom_filters.items():
                condition = _parse_filter_condition(value)
                if condition is None:
                    continue
                operator, filter_value = condition
                custom_expression = func.json_extract(Patent.custom_fields, f'$.{key}')
                predicate = _apply_filter_expression(custom_expression, operator, filter_value)
                if predicate is not None:
                    query = query.filter(predicate)

        total = query.count()

        family_size_map: dict[int, int] = {}
        if group_by_family:
            family_size_rows = query.order_by(None).with_entities(
                Patent.family_id.label("fid"),
                func.count(func.distinct(Patent.id)).label("cnt"),
            ).filter(
                Patent.family_id.isnot(None),
            ).group_by(Patent.family_id).all()
            family_size_map = {row.fid: row.cnt for row in family_size_rows}

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

        # Unknown imported columns are a visible, read-only projection. Keep
        # them out of the canonical Patent JSON and inject only the latest
        # retained observation into the response payload.
        pending_fields = get_pending_import_fields(db)
        if patents and pending_fields:
            patent_ids = [patent.id for patent in patents]
            pending_rows = db.query(FieldObservation).filter(
                FieldObservation.patent_id.in_(patent_ids),
                FieldObservation.field_resolution == "unmapped_retained",
                FieldObservation.canonical_field_key.is_(None),
            ).order_by(FieldObservation.id.desc()).all()
            values_by_patent: dict[int, dict[str, str]] = {}
            known_pending_keys = {
                field["source_field_name"]: temporary_import_field_key(field["source_field_name"])
                for field in pending_fields
            }
            for observation in pending_rows:
                if observation.patent_id not in values_by_patent:
                    values_by_patent[observation.patent_id] = {}
                source_name = observation.source_field_name
                if source_name in known_pending_keys and known_pending_keys[source_name] not in values_by_patent[observation.patent_id]:
                    values_by_patent[observation.patent_id][known_pending_keys[source_name]] = observation.raw_value or ""
            for patent in patents:
                pending_values = values_by_patent.get(patent.id)
                if pending_values:
                    # This is a read-only projection. Marking the merged
                    # value as committed prevents a list request from
                    # flushing temporary import evidence back into the
                    # canonical Patent JSON.
                    set_committed_value(
                        patent,
                        "custom_fields",
                        {**(patent.custom_fields or {}), **pending_values},
                    )

        # P2-8：同族聚拢模式下，附加 family_size（当前查询范围内的族成员数，含自身）
        if group_by_family and patents:
            for p in patents:
                p.family_size = family_size_map.get(p.family_id) if p.family_id is not None else None
                # family_key 是稳定的来源族标识，family_id 仍只作为内部外键。
                p.family_key = p.family.family_id if p.family is not None else None

        return patents, total

    @staticmethod
    def create_patent(db: Session, patent_in: PatentCreate) -> Patent:
        data = patent_in.model_dump(exclude_unset=True)
        if data.get("publication_number"):
            from app.services.patent_identity_service import normalize_publication_number
            normalized_publication = normalize_publication_number(data["publication_number"])
            if not normalized_publication:
                raise BadRequestException("公开号格式无法识别，应为国别字母+数字+文献类型代码")
            data["publication_number"] = normalized_publication
        custom_fields = data.pop("custom_fields", {}) or {}
        relation_fields = RELATION_FIELD_KEYS.intersection(custom_fields)
        if relation_fields:
            raise BadRequestException(
                "同族/引用原始列只能通过导入来源维护，请使用关系列导入或关系服务"
            )

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
        commit: bool = True,
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

        if update_data.get("publication_number"):
            from app.services.patent_identity_service import normalize_publication_number
            normalized_publication = normalize_publication_number(update_data["publication_number"])
            if not normalized_publication:
                raise BadRequestException("公开号格式无法识别，应为国别字母+数字+文献类型代码")
            update_data["publication_number"] = normalized_publication

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
            relation_fields = RELATION_FIELD_KEYS.intersection(custom_fields_data)
            if relation_fields:
                raise BadRequestException(
                    "同族/引用原始列是导入来源投影，不能通过普通专利编辑修改："
                    + ", ".join(sorted(relation_fields))
                )
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
        if commit:
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
        patents = PatentService._load_bulk_patents(db, patent_ids)
        if RISK_PROJECTION_FIELDS.intersection(updates):
            raise BadRequestException("风险兼容投影不可通过批量编辑修改，请使用风险案例")
        custom_fields = updates.get("custom_fields") or {}
        relation_fields = RELATION_FIELD_KEYS.intersection(custom_fields)
        if relation_fields:
            raise BadRequestException(
                "同族/引用原始列不能通过批量编辑修改：" + ", ".join(sorted(relation_fields))
            )
        try:
            for patent in patents:
                PatentService.update_patent(
                    db, patent, updates, source="bulk", commit=False,
                )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return len(patents)

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
        if mode not in {"add", "remove", "replace"}:
            raise BadRequestException("标签批量操作模式无效")
        patents = PatentService._load_bulk_patents(db, patent_ids)
        tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all() if tag_ids else []
        missing_tags = [tag_id for tag_id in tag_ids if tag_id not in {tag.id for tag in tags}]
        if missing_tags:
            raise BadRequestException(f"标签不存在，整批未执行：{missing_tags}")
        tag_set = set(tags)
        count = 0
        for patent in patents:
            current = set(patent.tags or [])
            if mode == "add":
                new_tags = current | tag_set
            elif mode == "remove":
                new_tags = current - tag_set
            elif mode == "replace":
                new_tags = tag_set
            old_tag_ids = sorted(tag.id for tag in current)
            new_tag_ids = sorted(tag.id for tag in new_tags)
            if old_tag_ids == new_tag_ids:
                continue
            patent.tags = list(new_tags)
            db.add(patent)
            db.add(PatentHistory(
                patent_id=patent.id,
                field_key="tags",
                field_display_name="标签",
                old_value=_stringify_value(old_tag_ids),
                new_value=_stringify_value(new_tag_ids),
                source="bulk",
                changed_by="local-user",
            ))
            count += 1
        db.commit()
        return count

    @staticmethod
    def _load_bulk_patents(
        db: Session,
        patent_ids: list[int],
        *,
        source_database_id: int | None = None,
        source_view_id: int | None = None,
        require_nonempty: bool = False,
    ) -> list[Patent]:
        """Load a complete selection and validate its declared UI scope.

        Legacy bulk edits keep their empty-selection no-op behavior. Transfer
        commands opt into ``require_nonempty`` so an omitted selection can
        never be interpreted as "all records".
        """
        ids = list(dict.fromkeys(int(item) for item in patent_ids))
        if not ids:
            if require_nonempty:
                raise BadRequestException("未选择任何专利，批量移动未执行")
            return []
        patents = db.query(Patent).filter(Patent.id.in_(ids)).all()
        found = {patent.id for patent in patents}
        missing = [patent_id for patent_id in ids if patent_id not in found]
        if missing:
            raise BadRequestException(f"选中的专利不存在，整批未执行：{missing}")
        by_id = {patent.id: patent for patent in patents}
        if source_database_id is not None:
            mismatched = [
                patent_id for patent_id in ids
                if by_id[patent_id].database_id != source_database_id
            ]
            if mismatched:
                raise BadRequestException(
                    f"所选专利不属于当前数据库，整批未执行：{mismatched}"
                )
        # The main table intentionally spans the whole source library, while
        # a saved view is a narrower explicit scope.
        if source_view_id is not None:
            mismatched = [
                patent_id for patent_id in ids
                if by_id[patent_id].view_id != source_view_id
            ]
            if mismatched:
                raise BadRequestException(
                    f"所选专利不属于当前视图，整批未执行：{mismatched}"
                )
        return [by_id[patent_id] for patent_id in ids]

    @staticmethod
    def bulk_move_database(
        db: Session,
        patent_ids: list[int],
        target_database_id: int,
        *,
        source_database_id: int,
        source_view_id: int | None = None,
    ) -> int:
        """Move master records to another library, retaining all patent data and audit history."""
        from app.models import PatentDatabase

        target = db.query(PatentDatabase).filter(
            PatentDatabase.id == target_database_id,
            PatentDatabase.is_archived == False,
        ).first()
        if not target:
            raise BadRequestException("目标数据库不存在或已归档")
        patents = PatentService._load_bulk_patents(
            db,
            patent_ids,
            source_database_id=source_database_id,
            source_view_id=source_view_id,
            require_nonempty=True,
        )
        moved_count = 0
        for patent in patents:
            old_database_id = patent.database_id
            if old_database_id == target_database_id:
                continue
            moved_count += 1
            old_view_id = patent.view_id
            patent.database_id = target_database_id
            # A view belongs to one database; do not leave a cross-library view reference.
            if patent.view is not None and patent.view.database_id != target_database_id:
                patent.view_id = None
            db.add(PatentHistory(
                patent_id=patent.id,
                field_key="database_id",
                field_display_name="数据库",
                old_value=_stringify_value(old_database_id),
                new_value=_stringify_value(target_database_id),
                source="bulk",
                changed_by="local-user",
            ))
            if old_view_id != patent.view_id:
                db.add(PatentHistory(
                    patent_id=patent.id,
                    field_key="view_id",
                    field_display_name="视图",
                    old_value=_stringify_value(old_view_id),
                    new_value=_stringify_value(patent.view_id),
                    source="bulk",
                    changed_by="local-user",
                ))
        db.commit()
        return moved_count

    @staticmethod
    def bulk_move_view(
        db: Session,
        patent_ids: list[int],
        target_view_id: int | None,
        *,
        source_database_id: int,
        source_view_id: int | None = None,
    ) -> int:
        """Move records to a view in their current library, or clear the view with null."""
        from app.models import PatentView

        patents = PatentService._load_bulk_patents(
            db,
            patent_ids,
            source_database_id=source_database_id,
            source_view_id=source_view_id,
            require_nonempty=True,
        )
        target_view = None
        if target_view_id is not None:
            target_view = db.query(PatentView).filter(
                PatentView.id == target_view_id,
                PatentView.is_archived == False,
            ).first()
            if not target_view:
                raise BadRequestException("目标视图不存在或已归档")
            mismatched = [
                patent.id for patent in patents
                if patent.database_id != target_view.database_id
            ]
            if mismatched:
                raise BadRequestException(
                    f"目标视图不属于所选专利所在数据库，整批未执行：{mismatched}"
                )

        moved_count = 0
        for patent in patents:
            old_view_id = patent.view_id
            if old_view_id == target_view_id:
                continue
            moved_count += 1
            patent.view_id = target_view_id
            db.add(PatentHistory(
                patent_id=patent.id,
                field_key="view_id",
                field_display_name="视图",
                old_value=_stringify_value(old_view_id),
                new_value=_stringify_value(target_view_id),
                source="bulk",
                changed_by="local-user",
                source_view_id=target_view_id,
                source_view_name=target_view.name if target_view else None,
            ))
        db.commit()
        return moved_count

    @staticmethod
    def bulk_duplicate(db: Session, patent_ids: list[int], target_database_id: int | None = None, target_view_id: int | None = None) -> list[Patent]:
        """Create editable working copies without pretending they are official patents.

        Official identifiers are intentionally cleared because they are globally unique
        and must never be duplicated. The copy retains research content and provenance,
        and is explicitly marked as a draft in notes.
        """
        from app.models import PatentDatabase, PatentView, RiskLevel

        sources = PatentService._load_bulk_patents(db, patent_ids)
        if target_database_id is not None:
            target = db.query(PatentDatabase).filter(
                PatentDatabase.id == target_database_id,
                PatentDatabase.is_archived == False,
            ).first()
            if not target:
                raise BadRequestException("目标数据库不存在或已归档")
        target_view = None
        if target_view_id is not None:
            target_view = db.query(PatentView).filter(
                PatentView.id == target_view_id,
                PatentView.is_archived == False,
            ).first()
            if not target_view:
                raise BadRequestException("目标视图不存在或已归档")
            if target_database_id is not None and target_view.database_id != target_database_id:
                raise BadRequestException("目标视图不属于目标数据库")
            if target_database_id is None:
                mismatched = [
                    source.id for source in sources
                    if source.database_id != target_view.database_id
                ]
                if mismatched:
                    raise BadRequestException(
                        f"目标视图不属于来源专利所在数据库，整批未执行：{mismatched}"
                    )

        created: list[Patent] = []
        for source in sources:
            source_notes = f"来源专利 ID={source.id}"
            if source.publication_number:
                source_notes += f"，公开号={source.publication_number}"
            existing_notes = source.notes.strip() if source.notes else ""
            clone = Patent(
                application_number=None,
                publication_number=None,
                grant_number=None,
                title=f"副本：{source.title or '未命名专利'}",
                abstract=source.abstract,
                claims=source.claims,
                description_full=source.description_full,
                applicant=source.applicant,
                inventor=source.inventor,
                assignee=source.assignee,
                agent=source.agent,
                filing_date=source.filing_date,
                publication_date=source.publication_date,
                grant_date=source.grant_date,
                priority_date=source.priority_date,
                priority_number=source.priority_number,
                priority_country=source.priority_country,
                country=source.country,
                patent_type=source.patent_type,
                legal_status=source.legal_status,
                legal_status_date=source.legal_status_date,
                legal_status_details=source.legal_status_details,
                ipc_main=source.ipc_main,
                ipc_all=source.ipc_all,
                cpc_main=source.cpc_main,
                cpc_all=source.cpc_all,
                database_id=target_database_id if target_database_id is not None else source.database_id,
                product_id=source.product_id,
                view_id=target_view_id if target_view_id is not None else source.view_id,
                category=source.category,
                subcategory=source.subcategory,
                technical_problem=source.technical_problem,
                technical_effect=source.technical_effect,
                technical_solution=source.technical_solution,
                has_risk=False,
                risk_level=RiskLevel.NONE,
                risk_description=None,
                module=source.module,
                application_status=source.application_status,
                scope_description=source.scope_description,
                notes=f"{existing_notes + '；' if existing_notes else ''}{source_notes}；工作副本，待补充正式专利身份。",
                custom_fields=deepcopy(source.custom_fields or {}),
                ai_fields=deepcopy(source.ai_fields or {}),
                duplicate_of=source.id,
            )
            db.add(clone)
            db.flush()
            clone.tags = list(source.tags or [])
            # Copy project links as context, while keeping the copy's formal risk state clear.
            PatentService.set_patent_projects(db, clone, [project.id for project in source.projects], commit=False)
            db.add(PatentHistory(
                patent_id=clone.id,
                field_key="duplicate_of",
                field_display_name="来源专利",
                old_value=None,
                new_value=_stringify_value(source.id),
                source="bulk",
                changed_by="local-user",
            ))
            created.append(clone)
        db.commit()
        for clone in created:
            db.refresh(clone)
        return created

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
