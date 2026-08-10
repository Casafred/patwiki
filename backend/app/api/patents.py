from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime, timezone
import json
from typing import Any

from app.database import get_db
from app.api.deps import get_pagination_params
from app.schemas.schemas import (
    AIValueOverrideRequest, Patent, PatentCreate, PatentUpdate, PatentListResponse, BulkUpdateRequest
)
from app.services.patent_service import PatentService
from app.services.view_service import ViewService
from app.models import AIFieldValue, Citation, CustomField, CustomFieldType, Patent as PatentModel, PatentHistory

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


@router.get("/{patent_id}", response_model=Patent)
def get_patent(patent_id: int, db: Session = Depends(get_db)):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    return patent


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
        raise HTTPException(status_code=404, detail="Patent not found")

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
                family_members = db.query(PatentModel).filter(PatentModel.family_id.in_(family_ids)).all()
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
            ).all() if citation_patent_ids else []
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
        raise HTTPException(status_code=404, detail="Patent not found")
    return _ai_value_response(patent, db)


@router.put("/{patent_id}/ai-values")
def override_ai_value(
    patent_id: int,
    request: AIValueOverrideRequest,
    db: Session = Depends(get_db),
):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    field = db.query(CustomField).filter(CustomField.key == request.field_key).first()
    if not _is_ai_field(field):
        raise HTTPException(status_code=404, detail="AI field not found")

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
        raise HTTPException(status_code=404, detail="Patent not found")
    field = db.query(CustomField).filter(CustomField.key == field_key).first()
    if not _is_ai_field(field):
        raise HTTPException(status_code=404, detail="AI field not found")
    row = db.query(AIFieldValue).filter(
        AIFieldValue.patent_id == patent.id,
        AIFieldValue.field_key == field_key,
    ).first()
    if not row or not row.is_overridden:
        raise HTTPException(status_code=404, detail="AI 字段当前没有人工覆盖")

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
        raise HTTPException(status_code=404, detail="Patent not found")
    return PatentService.update_patent(db, patent, patent_in)


@router.delete("/{patent_id}")
def delete_patent(patent_id: int, db: Session = Depends(get_db)):
    if not PatentService.delete_patent(db, patent_id):
        raise HTTPException(status_code=404, detail="Patent not found")
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


@router.get("/{patent_id}/history")
def get_patent_history(
    patent_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """查询专利的修改历史记录，按时间倒序。"""
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

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
        raise HTTPException(status_code=404, detail="Patent not found")
    return ViewService.get_field_sources(db, patent_id)
