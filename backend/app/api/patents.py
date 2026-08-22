from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime, timezone
import json
from typing import Any
from pydantic import BaseModel, Field

from app.database import get_db
from app.api.deps import get_pagination_params
from app.schemas.schemas import (
    AIValueOverrideRequest, Patent, PatentCreate, PatentUpdate, PatentListResponse, BulkUpdateRequest
)
from app.services.patent_service import PatentService
from app.services.view_service import ViewService
from app.models import (
    AIFieldValue,
    Citation,
    CustomField,
    CustomFieldType,
    FieldObservation,
    ImportBatch,
    ImportSourceRow,
    PatentProjectLink,
    Patent as PatentModel,
    PatentFamily,
    PatentHistory,
    PatentIdentifier,
)
from app.core.exceptions import NotFoundException
from app.services.patent_identity_service import list_patent_identifiers
from app.services.relation_service import find_existing_patent_by_number, parse_patent_numbers

router = APIRouter(prefix="/patents", tags=["patents"])


@router.get("", response_model=PatentListResponse)
def list_patents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    search: Optional[str] = None,
    database_id: Optional[int] = None,
    product_id: Optional[int] = None,
    project_id: Optional[int] = None,
    tag_id: Optional[int] = None,
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
    custom_filters: Optional[str] = Query(None, description="JSON string of custom field filters"),
    filters: Optional[str] = Query(None, description="JSON string of unified field filters, supports {field: {contains: 'xxx'}, field2: {eq: 'yyy'}}"),
    group_by_family: bool = Query(False, description="同族聚拢模式：同族专利排在一起，附加 family_size"),
    db: Session = Depends(get_db),
):
    tag_ids = [tag_id] if tag_id else None
    cf = None
    if custom_filters:
        try:
            cf = json.loads(custom_filters)
        except (json.JSONDecodeError, TypeError):
            cf = None
    uf = None
    if filters:
        try:
            uf = json.loads(filters)
        except (json.JSONDecodeError, TypeError):
            uf = None
    patents, total = PatentService.list_patents(
        db,
        page=page,
        page_size=page_size,
        search=search,
        database_id=database_id,
        product_id=product_id,
        project_id=project_id,
        tag_ids=tag_ids,
        legal_status=legal_status,
        category=category,
        has_risk=has_risk,
        risk_level=risk_level,
        patent_type=patent_type,
        country=country,
        filing_date_from=filing_date_from,
        filing_date_to=filing_date_to,
        sort_by=sort_by,
        sort_order=sort_order,
        custom_filters=cf,
        filters=uf,
        group_by_family=group_by_family,
    )
    return {
        "total": total,
        "items": patents,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{patent_id}/identifiers")
def get_patent_identifiers(patent_id: int, db: Session = Depends(get_db)):
    """返回专利身份链，供详情页展示号码类型、规范化值和来源。"""
    patent = db.query(PatentModel).filter(PatentModel.id == patent_id).first()
    if not patent:
        raise NotFoundException("Patent not found")
    return [
        {
            "id": identifier.id,
            "patent_id": identifier.patent_id,
            "identifier_namespace": identifier.identifier_namespace,
            "identifier_type": identifier.identifier_type,
            "raw_value": identifier.raw_value,
            "raw_values": identifier.raw_values or [identifier.raw_value],
            "normalized_value": identifier.normalized_value,
            "jurisdiction_code": identifier.jurisdiction_code,
            "kind_code": identifier.kind_code,
            "source_system": identifier.source_system,
            "source_timestamp": identifier.source_timestamp.isoformat() if identifier.source_timestamp else None,
            "is_primary": identifier.is_primary,
            "valid_from": identifier.valid_from.isoformat() if identifier.valid_from else None,
            "valid_to": identifier.valid_to.isoformat() if identifier.valid_to else None,
        }
        for identifier in list_patent_identifiers(db, patent_id)
    ]


@router.get("/{patent_id}/identity-conflicts")
def get_patent_identity_conflicts(patent_id: int, db: Session = Depends(get_db)):
    """Return quarantined import rows whose identity match included this patent."""
    patent = db.query(PatentModel).filter(PatentModel.id == patent_id).first()
    if not patent:
        raise NotFoundException("Patent not found")

    rows = db.query(ImportSourceRow, ImportBatch).join(
        ImportBatch, ImportBatch.id == ImportSourceRow.import_batch_id,
    ).filter(
        ImportSourceRow.resolution_status == "quarantined",
    ).order_by(ImportSourceRow.id.desc()).all()
    result = []
    for source_row, batch in rows:
        candidates = source_row.candidate_patent_ids or []
        if patent_id not in candidates:
            continue
        observations = db.query(FieldObservation).filter(
            FieldObservation.source_row_id == source_row.id,
        ).order_by(FieldObservation.source_column_index.asc(), FieldObservation.id.asc()).all()
        result.append({
            "source_row_id": source_row.id,
            "batch_id": batch.id,
            "filename": batch.filename,
            "source_table_title": batch.source_table_title,
            "worksheet_name": batch.worksheet_name,
            "source_row": source_row.source_row,
            "resolution_reason": source_row.resolution_reason,
            "candidate_patent_ids": candidates,
            "source_row_values": source_row.raw_row,
            "observations": [
                {
                    "id": item.id,
                    "source_field_name": item.source_field_name,
                    "raw_value": item.raw_value,
                    "candidate_value": item.candidate_value,
                    "difference_type": item.difference_type,
                }
                for item in observations
            ],
            "created_at": source_row.created_at.isoformat() if source_row.created_at else None,
        })
    return result


class PatentProjectLinksRequest(BaseModel):
    project_ids: list[int] = Field(default_factory=list)
    links: Optional[list[dict[str, Any]]] = None


@router.get("/{patent_id}/projects", response_model=list[dict[str, Any]])
def list_patent_projects(patent_id: int, db: Session = Depends(get_db)):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise NotFoundException("Patent not found")
    links = db.query(PatentProjectLink).filter(
        PatentProjectLink.patent_id == patent.id,
    ).all()
    projects_by_id = {project.id: project for project in patent.projects}
    return [
        {
            "id": project.id,
            "project_id": project.id,
            "relationship_id": link.id,
            "name": project.name,
            "code": project.code,
            "module": project.module,
            "status": project.status,
            "role": link.role.value if link.role else None,
            "relation_type": link.relation_type.value if link.relation_type else None,
            "risk_level": link.risk_level.value if link.risk_level else None,
            "document_role": link.document_role.value if link.document_role else None,
            "relevance_score": link.relevance_score,
            "importance": link.importance,
            "notes": link.notes,
            "assigned_to_id": link.assigned_to_id,
        }
        for link in links
        if (project := projects_by_id.get(link.project_id)) is not None
    ]


@router.put("/{patent_id}/projects", response_model=Patent)
def replace_patent_projects(
    patent_id: int,
    request: PatentProjectLinksRequest,
    db: Session = Depends(get_db),
):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise NotFoundException("Patent not found")
    return PatentService.set_patent_projects(
        db,
        patent,
        request.project_ids,
        link_specs=request.links,
    )


@router.get("/{patent_id}", response_model=Patent)
def get_patent(patent_id: int, db: Session = Depends(get_db)):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise NotFoundException("Patent not found")
    return patent


@router.get("/{patent_id}/family")
def get_patent_family(patent_id: int, db: Session = Depends(get_db)):
    """返回当前专利所在库中的同族成员。

    同族成员是独立 Patent 记录，详情页需要用其 id 进行真实导航；
    database_id 限制保证历史数据中跨库复用 family_id 时不会串库。
    """
    root = db.query(PatentModel).filter(PatentModel.id == patent_id).first()
    if not root:
        raise NotFoundException("Patent not found")

    members = [root]
    if root.family_id is not None:
        members = db.query(PatentModel).filter(
            PatentModel.family_id == root.family_id,
            PatentModel.database_id == root.database_id,
        ).order_by(
            (PatentModel.id == root.id).desc(),
            PatentModel.filing_date.desc(),
            PatentModel.id.asc(),
        ).all()

    family = db.query(PatentFamily).filter(PatentFamily.id == root.family_id).first() if root.family_id else None

    def serialize(member: PatentModel, status: str | None = None) -> dict[str, Any]:
        return {
            "id": member.id,
            "publication_number": member.publication_number,
            "application_number": member.application_number,
            "grant_number": member.grant_number,
            "title": member.title,
            "country": member.country,
            "legal_status": member.legal_status.value if member.legal_status else None,
            "filing_date": member.filing_date.isoformat() if member.filing_date else None,
            "publication_date": member.publication_date.isoformat() if member.publication_date else None,
            "grant_date": member.grant_date.isoformat() if member.grant_date else None,
            "is_current": member.id == root.id,
            "database_id": member.database_id,
            "in_current_database": member.database_id == root.database_id,
            "status": status or ("in_database" if member.database_id == root.database_id else "other_database"),
        }

    external_members: list[dict[str, Any]] = []
    if root.family_id is not None:
        external = db.query(PatentModel).filter(
            PatentModel.family_id == root.family_id,
            PatentModel.database_id != root.database_id,
        ).order_by(PatentModel.id.asc()).all()
        external_members = [serialize(member, "other_database") for member in external]

    raw_family_numbers = parse_patent_numbers(
        str((root.custom_fields or {}).get("family_members") or "")
    )
    missing_members: list[dict[str, Any]] = []
    observed_current_members: list[dict[str, Any]] = []
    current_member_ids = {member.id for member in members}
    external_member_ids = {member["id"] for member in external_members}
    for number in raw_family_numbers:
        existing = find_existing_patent_by_number(db, number)
        if existing is None:
            missing_members.append({
                "id": None,
                "publication_number": number,
                "application_number": None,
                "grant_number": None,
                "title": None,
                "country": number[:2] if number[:2].isalpha() else None,
                "is_current": False,
                "database_id": None,
                "in_current_database": False,
                "status": "missing_record",
            })
        elif existing.database_id == root.database_id and existing.id not in current_member_ids:
            observed_current_members.append(serialize(existing))
            current_member_ids.add(existing.id)
        elif existing.database_id != root.database_id and existing.id not in external_member_ids:
            external_members.append(serialize(existing, "other_database"))
            external_member_ids.add(existing.id)

    return {
        "root_id": root.id,
        "family_id": root.family_id,
        "family_key": family.family_id if family else None,
        "family_type": family.family_type if family else None,
        "members": [serialize(member) for member in members] + observed_current_members,
        "external_members": external_members,
        "missing_members": missing_members,
    }


def _serialize_relation_patent(root: PatentModel, patent: PatentModel | None, number: str, relation_id: int | None, direction: str) -> dict[str, Any]:
    if patent is None:
        return {
            "relation_id": relation_id,
            "patent_id": None,
            "publication_number": number,
            "application_number": None,
            "grant_number": None,
            "title": None,
            "country": number[:2] if number[:2].isalpha() else None,
            "database_id": None,
            "in_current_database": False,
            "status": "missing_record",
            "direction": direction,
        }
    return {
        "relation_id": relation_id,
        "patent_id": patent.id,
        "publication_number": patent.publication_number,
        "application_number": patent.application_number,
        "grant_number": patent.grant_number,
        "title": patent.title,
        "country": patent.country,
        "database_id": patent.database_id,
        "in_current_database": patent.database_id == root.database_id,
        "status": "in_database" if patent.database_id == root.database_id else "other_database",
        "direction": direction,
    }


@router.get("/{patent_id}/citations")
def get_patent_citations(patent_id: int, db: Session = Depends(get_db)):
    """返回正向/反向引用，并明确目标是否属于当前数据库。

    该读取接口不创建占位 Patent；仅在原始关系列中出现的号码返回
    `missing_record`，使来源文本和结构化关系的差异对用户可见。
    """
    root = db.query(PatentModel).filter(PatentModel.id == patent_id).first()
    if not root:
        raise NotFoundException("Patent not found")

    citing = aliased(PatentModel)
    cited = aliased(PatentModel)
    rows = db.query(Citation, citing, cited).join(
        citing, citing.id == Citation.citing_patent_id,
    ).join(
        cited, cited.id == Citation.cited_patent_id,
    ).filter(
        or_(Citation.citing_patent_id == root.id, Citation.cited_patent_id == root.id),
    ).order_by(Citation.id.asc()).all()

    cited_items: list[dict[str, Any]] = []
    citing_items: list[dict[str, Any]] = []
    seen_cited: set[tuple[int | None, str]] = set()
    seen_citing: set[tuple[int | None, str]] = set()
    for citation, citing_patent, cited_patent in rows:
        if citation.citing_patent_id == root.id:
            item = _serialize_relation_patent(root, cited_patent, cited_patent.publication_number or cited_patent.application_number or "", citation.id, "cited")
            key = (item["patent_id"], item["publication_number"] or "")
            if key not in seen_cited:
                cited_items.append(item)
                seen_cited.add(key)
        if citation.cited_patent_id == root.id:
            item = _serialize_relation_patent(root, citing_patent, citing_patent.publication_number or citing_patent.application_number or "", citation.id, "citing")
            key = (item["patent_id"], item["publication_number"] or "")
            if key not in seen_citing:
                citing_items.append(item)
                seen_citing.add(key)

    def append_missing(raw_key: str, target: list[dict[str, Any]], seen: set[tuple[int | None, str]], direction: str):
        for number in parse_patent_numbers(str((root.custom_fields or {}).get(raw_key) or "")):
            existing = find_existing_patent_by_number(db, number)
            if existing is not None:
                key = (existing.id, existing.publication_number or existing.application_number or number)
            else:
                key = (None, number)
            if key in seen:
                continue
            if existing is not None:
                # A raw column can exist before the Citation entity is created.
                target.append(_serialize_relation_patent(root, existing, number, None, direction))
            else:
                target.append(_serialize_relation_patent(root, None, number, None, direction))
            seen.add(key)

    append_missing("cited_patents", cited_items, seen_cited, "cited")
    append_missing("citing_patents", citing_items, seen_citing, "citing")
    return {
        "root_id": root.id,
        "database_id": root.database_id,
        "cited": cited_items,
        "citing": citing_items,
    }


@router.get("/{patent_id}/graph")
def get_patent_graph(
    patent_id: int,
    depth: int = Query(1, ge=1, le=2),
    include_family: bool = Query(True),
    include_citations: bool = Query(True),
    db: Session = Depends(get_db),
):
    """返回专利同族与引用关系图数据，供前端图谱组件直接渲染。"""
    root = db.query(PatentModel).filter(PatentModel.id == patent_id).first()
    if not root:
        raise NotFoundException("Patent not found")

    patents_by_id: dict[int, PatentModel] = {root.id: root}
    edges: list[dict[str, str]] = []
    edge_ids: set[str] = set()
    frontier = {root.id}
    visited_ids = {root.id}

    def add_edge(edge_id: str, source: int, target: int, relation: str, label: str):
        if edge_id in edge_ids or source == target:
            return
        edge_ids.add(edge_id)
        edges.append({
            "id": edge_id,
            "source": f"patent:{source}",
            "target": f"patent:{target}",
            "relation": relation,
            "label": label,
        })

    for _ in range(depth):
        if not frontier:
            break
        next_frontier: set[int] = set()

        if include_family:
            frontier_patents = db.query(PatentModel).filter(PatentModel.id.in_(frontier)).all()
            family_ids = {patent.family_id for patent in frontier_patents if patent.family_id is not None}
            if family_ids:
                family_members = db.query(PatentModel).filter(
                    PatentModel.family_id.in_(family_ids),
                    PatentModel.database_id == root.database_id,
                ).all()
                for member in family_members:
                    patents_by_id[member.id] = member
                for family_id in family_ids:
                    members = [item for item in family_members if item.family_id == family_id]
                    if not members:
                        continue
                    anchor = min(members, key=lambda item: item.id)
                    for member in members:
                        if member.id != anchor.id:
                            add_edge(
                                f"family:{family_id}:{anchor.id}:{member.id}",
                                anchor.id,
                                member.id,
                                "family",
                                "同族",
                            )
                    next_frontier.update(member.id for member in members if member.id not in frontier)

        if include_citations:
            citation_rows = db.query(Citation).filter(or_(
                Citation.citing_patent_id.in_(frontier),
                Citation.cited_patent_id.in_(frontier),
            )).all()
            citation_patent_ids = {
                patent_id
                for citation in citation_rows
                for patent_id in (citation.citing_patent_id, citation.cited_patent_id)
            }
            citation_patents = db.query(PatentModel).filter(
                PatentModel.id.in_(citation_patent_ids)
            ).filter(PatentModel.database_id == root.database_id).all() if citation_patent_ids else []
            citation_patents_by_id = {patent.id: patent for patent in citation_patents}
            for citation in citation_rows:
                citing = citation_patents_by_id.get(citation.citing_patent_id)
                cited = citation_patents_by_id.get(citation.cited_patent_id)
                if not citing or not cited:
                    continue
                patents_by_id[citing.id] = citing
                patents_by_id[cited.id] = cited
                add_edge(
                    f"citation:{citation.id}",
                    citation.citing_patent_id,
                    citation.cited_patent_id,
                    "citation",
                    "引用",
                )
                if citing.id not in frontier:
                    next_frontier.add(citing.id)
                if cited.id not in frontier:
                    next_frontier.add(cited.id)

        frontier = next_frontier - visited_ids
        visited_ids.update(frontier)

    root_family_id = root.family_id
    nodes = []
    for patent in patents_by_id.values():
        number = patent.publication_number or patent.application_number or f"专利 #{patent.id}"
        title = patent.title or number
        kind = "root" if patent.id == root.id else (
            "family" if root_family_id is not None and patent.family_id == root_family_id else "citation"
        )
        nodes.append({
            "id": f"patent:{patent.id}",
            "patent_id": patent.id,
            "kind": kind,
            "label": title[:26] + ("..." if len(title) > 26 else ""),
            "title": title,
            "number": number,
            "is_placeholder": title == "待补全",
        })

    return {
        "root_id": root.id,
        "depth": depth,
        "nodes": nodes,
        "edges": edges,
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "family_edges": sum(edge["relation"] == "family" for edge in edges),
            "citation_edges": sum(edge["relation"] == "citation" for edge in edges),
        },
    }


def _serialize_ai_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _serialize_generated_value(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _decode_generated_value(value: str | None) -> Any:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
        if isinstance(parsed, (dict, list, int, float, bool)):
            return parsed
    except (TypeError, ValueError):
        pass
    return value


def _decode_override_value(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _is_ai_field(field: CustomField | None) -> bool:
    if not field:
        return False
    actual_type = field.field_type.value if hasattr(field.field_type, "value") else str(field.field_type)
    return actual_type == CustomFieldType.AI_FIELD.value


def _ai_value_response(patent: Patent, db: Session) -> list[dict[str, Any]]:
    rows = db.query(AIFieldValue).filter(AIFieldValue.patent_id == patent.id).all()
    row_by_key = {row.field_key: row for row in rows}
    ai_data = patent.ai_fields or {}
    keys = list(dict.fromkeys([*ai_data.keys(), *(row.field_key for row in rows)]))
    result = []
    for field_key in keys:
        row = row_by_key.get(field_key)
        generated = _decode_generated_value(row.value) if row else ai_data.get(field_key)
        overridden = bool(row and row.is_overridden)
        effective = _decode_override_value(row.overridden_value) if overridden else generated
        result.append({
            "field_key": field_key,
            "value": effective,
            "generated_value": generated,
            "is_overridden": overridden,
            "overridden_at": row.overridden_at if row else None,
            "updated_at": row.updated_at if row else None,
        })
    return result


@router.get("/{patent_id}/ai-values")
def list_ai_values(patent_id: int, db: Session = Depends(get_db)):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise NotFoundException("Patent not found")
    return _ai_value_response(patent, db)


@router.put("/{patent_id}/ai-values")
def override_ai_value(
    patent_id: int,
    request: AIValueOverrideRequest,
    db: Session = Depends(get_db),
):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise NotFoundException("Patent not found")
    field = db.query(CustomField).filter(CustomField.key == request.field_key).first()
    if not _is_ai_field(field):
        raise NotFoundException("AI field not found")

    current = dict(patent.ai_fields or {})
    old_value = current.get(request.field_key)
    row = db.query(AIFieldValue).filter(
        AIFieldValue.patent_id == patent.id,
        AIFieldValue.field_key == request.field_key,
    ).first()
    if not row:
        row = AIFieldValue(
            patent_id=patent.id,
            field_key=request.field_key,
            value=_serialize_generated_value(old_value),
        )
        db.add(row)
    row.is_overridden = True
    row.overridden_value = _serialize_ai_value(request.value)
    row.overridden_at = datetime.now(timezone.utc).replace(tzinfo=None)
    current[request.field_key] = request.value
    patent.ai_fields = current
    db.add(PatentHistory(
        patent_id=patent.id,
        field_key=f"ai_fields.{request.field_key}",
        field_display_name=field.name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(request.value) if request.value is not None else None,
        source="manual",
    ))
    db.add(patent)
    db.commit()
    return next(item for item in _ai_value_response(patent, db) if item["field_key"] == request.field_key)


@router.delete("/{patent_id}/ai-values")
def clear_ai_value_override(
    patent_id: int,
    field_key: str = Query(...),
    db: Session = Depends(get_db),
):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise NotFoundException("Patent not found")
    field = db.query(CustomField).filter(CustomField.key == field_key).first()
    if not _is_ai_field(field):
        raise NotFoundException("AI field not found")
    row = db.query(AIFieldValue).filter(
        AIFieldValue.patent_id == patent.id,
        AIFieldValue.field_key == field_key,
    ).first()
    if not row or not row.is_overridden:
        raise NotFoundException("AI 字段当前没有人工覆盖")

    current = dict(patent.ai_fields or {})
    old_value = _decode_override_value(row.overridden_value)
    generated = _decode_generated_value(row.value)
    row.is_overridden = False
    row.overridden_value = None
    row.overridden_at = None
    if generated is None:
        current.pop(field_key, None)
    else:
        current[field_key] = generated
    patent.ai_fields = current
    db.add(PatentHistory(
        patent_id=patent.id,
        field_key=f"ai_fields.{field_key}",
        field_display_name=field.name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(generated) if generated is not None else None,
        source="manual",
    ))
    db.add(patent)
    db.commit()
    return {"success": True, "field_key": field_key, "value": generated}


@router.post("", response_model=Patent)
def create_patent(patent_in: PatentCreate, db: Session = Depends(get_db)):
    return PatentService.create_patent(db, patent_in)


@router.put("/{patent_id}", response_model=Patent)
def update_patent(patent_id: int, patent_in: PatentUpdate, db: Session = Depends(get_db)):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise NotFoundException("Patent not found")
    return PatentService.update_patent(db, patent, patent_in)


@router.delete("/{patent_id}")
def delete_patent(patent_id: int, db: Session = Depends(get_db)):
    if not PatentService.delete_patent(db, patent_id):
        raise NotFoundException("Patent not found")
    return {"success": True}


@router.post("/bulk-update")
def bulk_update_patents(
    payload: BulkUpdateRequest,
    db: Session = Depends(get_db),
):
    count = PatentService.bulk_update(db, payload.patent_ids, payload.updates)
    return {"success": True, "updated_count": count}


@router.post("/bulk-delete")
def bulk_delete_patents(
    patent_ids: list[int],
    db: Session = Depends(get_db),
):
    """批量删除专利。请求体直接为 [id1, id2, ...] 数组。"""
    if not patent_ids:
        return {"success": True, "deleted_count": 0}
    from app.models.patent import Patent as PatentModel
    patents = db.query(PatentModel).filter(PatentModel.id.in_(patent_ids)).all()
    for p in patents:
        db.delete(p)
    db.commit()
    return {"success": True, "deleted_count": len(patents)}


class BulkTagRequest(BaseModel):
    patent_ids: list[int]
    tag_ids: list[int]
    mode: str = "add"  # add / remove / replace


class BulkMoveDatabaseRequest(BaseModel):
    patent_ids: list[int]
    target_database_id: int


class BulkMoveViewRequest(BaseModel):
    patent_ids: list[int]
    target_view_id: Optional[int] = None


class BulkDuplicateRequest(BaseModel):
    patent_ids: list[int]
    target_database_id: Optional[int] = None
    target_view_id: Optional[int] = None


@router.post("/bulk-tag")
def bulk_tag_patents(
    payload: BulkTagRequest,
    db: Session = Depends(get_db),
):
    """批量打标签 / 移除标签 / 替换标签。

    mode:
        - add:     追加标签（保留原有）
        - remove:  移除指定标签
        - replace: 用指定标签替换全部标签
    """
    if not payload.patent_ids:
        return {"success": True, "updated_count": 0}
    count = PatentService.bulk_tag(
        db, payload.patent_ids, payload.tag_ids, mode=payload.mode
    )
    return {"success": True, "updated_count": count}


@router.post("/bulk-move-database")
def bulk_move_database(
    payload: BulkMoveDatabaseRequest,
    db: Session = Depends(get_db),
):
    """Move selected master patents into another library as one atomic command."""
    count = PatentService.bulk_move_database(
        db, payload.patent_ids, payload.target_database_id,
    )
    return {
        "success": True,
        "moved_count": count,
        "target_database_id": payload.target_database_id,
    }


@router.post("/bulk-move-view")
def bulk_move_view(
    payload: BulkMoveViewRequest,
    db: Session = Depends(get_db),
):
    """Move selected patents into a view in the same library, or clear their explicit view."""
    count = PatentService.bulk_move_view(db, payload.patent_ids, payload.target_view_id)
    return {
        "success": True,
        "moved_count": count,
        "target_view_id": payload.target_view_id,
    }


@router.post("/bulk-duplicate")
def bulk_duplicate_patents(
    payload: BulkDuplicateRequest,
    db: Session = Depends(get_db),
):
    """Create editable working copies while preserving the one-official-identity rule."""
    copies = PatentService.bulk_duplicate(
        db,
        payload.patent_ids,
        target_database_id=payload.target_database_id,
        target_view_id=payload.target_view_id,
    )
    return {
        "success": True,
        "created_count": len(copies),
        "created_ids": [patent.id for patent in copies],
    }


@router.delete("/by-database/{database_id}")
def delete_all_patents_in_database(
    database_id: int,
    db: Session = Depends(get_db),
):
    """清空指定库下的所有专利（整库清空，不删库本身）。"""
    from app.models.patent import Patent as PatentModel
    count = db.query(PatentModel).filter(PatentModel.database_id == database_id).count()
    if count == 0:
        return {"success": True, "deleted_count": 0}
    # 批量删除（SQLite 单条 delete 较慢，用 delete 语句）
    db.query(PatentModel).filter(PatentModel.database_id == database_id).delete(
        synchronize_session=False
    )
    db.commit()
    return {"success": True, "deleted_count": count}


@router.post("/cleanup/invalid-placeholders")
def cleanup_invalid_placeholders(
    dry_run: bool = Query(True, description="dry_run=True 仅返回将被删除的列表，不真正删除"),
    db: Session = Depends(get_db),
):
    """清理无效的占位专利（title="待补全" 且申请号/公开号格式不合法的记录）。

    这些占位专利通常由同族/引用列解析时，因分隔符识别错误或日期+专利号合并乱码导致。
    修复 relation_service 后，历史残留的无效占位可用本端点清理。
    """
    from app.services.relation_service import _PATENT_NUM_RE, _DATE_PREFIX_RE
    from app.models.patent import Patent as PatentModel

    candidates = db.query(PatentModel).filter(PatentModel.title == "待补全").all()

    def _is_invalid(num) -> bool:
        """判断单个号是否不合法（应被清理）。"""
        if not num:
            return False
        num = num.strip() if isinstance(num, str) else num
        if not num:
            return False
        if len(num) < 5 or len(num) > 30:
            return True
        if not _PATENT_NUM_RE.match(num):
            return True
        # 日期前缀乱码（如 20061102AU2005201606A1）
        if _DATE_PREFIX_RE.match(num):
            return True
        return False

    to_delete = []
    for p in candidates:
        app_invalid = _is_invalid(p.application_number)
        pub_invalid = _is_invalid(p.publication_number)
        # 申请号和公开号都不合法 → 删除
        if app_invalid and pub_invalid:
            to_delete.append(p)
        # 申请号不合法且无公开号 → 删除
        elif app_invalid and not p.publication_number:
            to_delete.append(p)
        # 公开号不合法且无申请号 → 删除
        elif pub_invalid and not p.application_number:
            to_delete.append(p)

    items = [
        {
            "id": p.id,
            "application_number": p.application_number,
            "publication_number": p.publication_number,
            "notes": p.notes,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in to_delete
    ]

    if not dry_run:
        for p in to_delete:
            db.delete(p)
        db.commit()

    return {"deleted_count": len(items), "deleted_items": items, "dry_run": dry_run}


@router.post("/maintenance/rebuild-family-relations")
def rebuild_family_relations(
    database_id: Optional[int] = Query(None, description="仅重建指定库，不传则全库重建"),
    db: Session = Depends(get_db),
):
    """重建同族关系。

    修复 relation_service 的 family hash 算法后（从号字符串改为 patent ID），
    历史导入产生的旧 family_id 可能不一致。本端点：

    1. 遍历所有已有 PatentFamily，用新算法（成员 ID 哈希）重新计算 family_id
    2. 同一组专利始终得到相同的 family_id_str，合并重复族
    3. 清理无成员的空族

    注意：本端点只能合并已有同族关系的专利。如果两篇专利本应同族但导入时
    从未建立关系（如导入失败导致），需要重新导入才能修复。
    """
    from app.services.relation_service import _get_or_create_family_by_ids
    from app.models.patent import PatentFamily

    query = db.query(PatentFamily)
    families = query.all()

    merged = 0
    consolidated = 0
    removed_empty = 0
    errors = []

    for family in families:
        try:
            members = db.query(PatentModel).filter(
                PatentModel.family_id == family.id
            ).all()
            if not members:
                db.delete(family)
                removed_empty += 1
                continue

            member_ids = [m.id for m in members if m.id is not None]
            if len(member_ids) < 2:
                # 单成员族，保留但用新算法重算
                new_family = _get_or_create_family_by_ids(
                    db, member_ids,
                    [m.publication_number or m.application_number or "" for m in members],
                )
                for m in members:
                    m.family_id = new_family.id
                if new_family.id != family.id:
                    # 旧族已无成员，删除
                    remaining = db.query(PatentModel).filter(
                        PatentModel.family_id == family.id
                    ).count()
                    if remaining == 0:
                        db.delete(family)
                consolidated += 1
                continue

            new_family = _get_or_create_family_by_ids(
                db, member_ids,
                [m.publication_number or m.application_number or "" for m in members],
            )
            if new_family.id != family.id:
                # 新族与旧族不同，迁移成员
                for m in members:
                    m.family_id = new_family.id
                # 删除空族
                db.delete(family)
                merged += 1
            else:
                consolidated += 1
        except Exception as exc:
            errors.append({"family_id": family.id, "error": str(exc)})
            db.rollback()

    db.commit()

    return {
        "total_families_scanned": len(families),
        "consolidated": consolidated,
        "merged": merged,
        "removed_empty": removed_empty,
        "errors": errors[:20],
        "error_count": len(errors),
    }


@router.get("/{patent_id}/history")
def get_patent_history(
    patent_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """查询专利的修改历史记录，按时间倒序。"""
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise NotFoundException("Patent not found")

    records = (
        db.query(PatentHistory)
        .filter(PatentHistory.patent_id == patent_id)
        .order_by(PatentHistory.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": h.id,
            "patent_id": h.patent_id,
            "field_key": h.field_key,
            "field_display_name": h.field_display_name,
            "old_value": h.old_value,
            "new_value": h.new_value,
            "source": h.source,
            "changed_by": h.changed_by,
            "source_view_id": h.source_view_id,
            "source_view_name": h.source_view_name,
            "import_batch_id": h.import_batch_id,
            "source_table_title": h.source_table_title,
            "source_row": h.source_row,
            "source_field_name": h.source_field_name,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in records
    ]


@router.get("/{patent_id}/field-sources")
def get_field_sources(patent_id: int, db: Session = Depends(get_db)):
    """字段来源追溯：返回该专利每个字段的最后一次修改来源信息。

    用于详情页展示"这个值是从哪个小表/导入/AI 来的"。
    """
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise NotFoundException("Patent not found")
    return ViewService.get_field_sources(db, patent_id)
