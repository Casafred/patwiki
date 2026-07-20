from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
import json

from app.database import get_db
from app.api.deps import get_pagination_params
from app.schemas.schemas import (
    Patent, PatentCreate, PatentUpdate, PatentListResponse, BulkUpdateRequest
)
from app.services.patent_service import PatentService
from app.services.view_service import ViewService
from app.models import PatentHistory, AIFieldValue, CustomField
from pydantic import BaseModel

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
    group_by_family: bool = Query(False, description="同族聚拢排序：开启后忽略 sort_by/sort_order，按 family_id 分组排序，同族排在一起"),
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


@router.get("/search/suggest")
def search_suggest(
    q: str = Query(..., min_length=1, max_length=100, description="搜索前缀"),
    limit: int = Query(10, ge=1, le=50),
    database_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """P2-6：搜索自动补全。

    根据用户输入的前缀 q，返回匹配的：
    - 标题（title）含 q 的专利标题片段
    - 申请号（application_number）以 q 开头或含 q
    - 公开号（publication_number）以 q 开头或含 q
    - 申请人（applicant）含 q 的去重值
    - 发明人（inventor）含 q 的去重值

    返回结构：{ suggestions: [{type, value, label, patent_id?}] }
    """
    from sqlalchemy import or_, literal_column, func
    from app.models.patent import Patent as PatentModel
    keyword = f"%{q}%"
    prefix = f"{q}%"

    suggestions: list[dict] = []
    seen_values: set[tuple[str, str]] = set()

    def _add(stype: str, value: str, label: str, patent_id: int | None = None):
        key = (stype, value)
        if key in seen_values or not value:
            return
        seen_values.add(key)
        suggestions.append({
            "type": stype,
            "value": value,
            "label": label,
            "patent_id": patent_id,
        })

    base_q = db.query(PatentModel)
    if database_id is not None:
        base_q = base_q.filter(PatentModel.database_id == database_id)

    # 1) 申请号 / 公开号（前缀匹配优先，limit/2 条）
    id_q = base_q.filter(
        or_(
            PatentModel.application_number.like(prefix),
            PatentModel.publication_number.like(prefix),
            PatentModel.application_number.like(keyword),
            PatentModel.publication_number.like(keyword),
        )
    ).limit(limit)
    for p in id_q.all():
        if p.application_number and q.upper() in p.application_number.upper():
            _add("application_number", p.application_number, f"申请号：{p.application_number}", p.id)
        if p.publication_number and q.upper() in p.publication_number.upper():
            _add("publication_number", p.publication_number, f"公开号：{p.publication_number}", p.id)
        if len(suggestions) >= limit:
            return {"suggestions": suggestions[:limit]}

    # 2) 标题（含 q，limit/2 条）
    title_q = base_q.filter(PatentModel.title.like(keyword)).limit(max(limit // 2, 3))
    for p in title_q.all():
        if p.title:
            label = p.title if len(p.title) <= 60 else p.title[:60] + "..."
            _add("title", p.title, f"标题：{label}", p.id)
        if len(suggestions) >= limit:
            return {"suggestions": suggestions[:limit]}

    # 3) 申请人 / 发明人（去重聚合，含 q）
    applicant_q = base_q.filter(PatentModel.applicant.like(keyword)).with_entities(
        PatentModel.applicant, func.count(PatentModel.id).label("cnt")
    ).group_by(PatentModel.applicant).order_by(literal_column("cnt").desc()).limit(max(limit // 3, 3))
    for row in applicant_q.all():
        if row.applicant:
            _add("applicant", row.applicant, f"申请人：{row.applicant}（{row.cnt}）")

    inventor_q = base_q.filter(PatentModel.inventor.like(keyword)).with_entities(
        PatentModel.inventor, func.count(PatentModel.id).label("cnt")
    ).group_by(PatentModel.inventor).order_by(literal_column("cnt").desc()).limit(max(limit // 3, 3))
    for row in inventor_q.all():
        if row.inventor:
            _add("inventor", row.inventor, f"发明人：{row.inventor}（{row.cnt}）")

    return {"suggestions": suggestions[:limit]}


@router.get("/{patent_id}", response_model=Patent)
def get_patent(patent_id: int, db: Session = Depends(get_db)):
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    return patent


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
    req: BulkUpdateRequest,
    db: Session = Depends(get_db),
):
    updates = req.updates or {}
    count = PatentService.bulk_update(
        db,
        req.patent_ids,
        updates,
        changed_by=req.changed_by,
        source=req.source or "bulk",
    )
    return {"success": True, "updated_count": count}


# ============================================================
# P2-7：专利引用 / 同族关系图谱
# ============================================================

@router.get("/{patent_id}/graph")
def get_patent_graph(
    patent_id: int,
    depth: int = Query(1, ge=1, le=2, description="展开深度（1=直接相邻，2=二度）"),
    db: Session = Depends(get_db),
):
    """P2-7：返回以 patent_id 为中心的关系图谱数据。

    图谱节点：
    - 中心节点：当前专利
    - 同族节点：与中心专利 family_id 相同的其他专利
    - 引用节点（向后 citing_patents）：被本专利引用的专利
    - 引用节点（向前 cited_patents）：引用本专利的专利

    边类型：
    - 'family'：同族关系（无方向，但 source=较小 id, target=较大 id）
    - 'citation'：引用关系，source=citing_patent_id → target=cited_patent_id

    当 depth=2 时，把一度邻居的邻居也展开（避免中心节点爆炸，二度仅取引用，不含 family 横向扩散）。
    """
    from app.models.patent import Patent as PatentModel, Citation, PatentFamily

    center = PatentService.get_patent(db, patent_id)
    if not center:
        raise HTTPException(status_code=404, detail="Patent not found")

    def _node_dict(p: PatentModel, distance: int, relation: str, is_center: bool = False) -> dict:
        return {
            "id": p.id,
            "title": p.title or "",
            "application_number": p.application_number,
            "publication_number": p.publication_number,
            "applicant": p.applicant,
            "filing_date": p.filing_date.isoformat() if p.filing_date else None,
            "country": p.country,
            "patent_type": p.patent_type.value if p.patent_type else None,
            "legal_status": p.legal_status.value if p.legal_status else None,
            "family_id": p.family_id,
            "module": p.module,
            "risk_level": p.risk_level.value if p.risk_level else None,
            "distance": distance,
            "relation": relation,
            "is_center": is_center,
        }

    nodes: dict[int, dict] = {
        center.id: _node_dict(center, 0, "center", is_center=True)
    }
    edges: list[dict] = []
    seen_edge_keys: set[tuple] = set()

    def _add_edge(source: int, target: int, etype: str, citation_type: str | None = None):
        # family 用无向去重 (min,max)；citation 用有向去重 (source,target)
        if etype == "family":
            key = ("family", min(source, target), max(source, target))
        else:
            key = ("citation", source, target)
        if key in seen_edge_keys or source == target:
            return
        seen_edge_keys.add(key)
        edge: dict = {"source": source, "target": target, "type": etype}
        if citation_type:
            edge["citation_type"] = citation_type
        edges.append(edge)

    # 1) 同族节点（family_id 非空时）
    if center.family_id is not None:
        siblings = (
            db.query(PatentModel)
            .filter(
                PatentModel.family_id == center.family_id,
                PatentModel.id != center.id,
            )
            .all()
        )
        for sib in siblings:
            if sib.id not in nodes:
                nodes[sib.id] = _node_dict(sib, 1, "family")
            _add_edge(center.id, sib.id, "family")

    # 2) 中心节点的引用：本专利引用了谁（向后引）
    cited_rows = (
        db.query(Citation, PatentModel)
        .join(PatentModel, PatentModel.id == Citation.cited_patent_id)
        .filter(Citation.citing_patent_id == center.id)
        .all()
    )
    for cit, p in cited_rows:
        if p.id not in nodes:
            nodes[p.id] = _node_dict(p, 1, "cited")
        _add_edge(center.id, p.id, "citation", cit.citation_type)

    # 3) 中心节点被引用：谁引用了本专利（向前引）
    citing_rows = (
        db.query(Citation, PatentModel)
        .join(PatentModel, PatentModel.id == Citation.citing_patent_id)
        .filter(Citation.cited_patent_id == center.id)
        .all()
    )
    for cit, p in citing_rows:
        if p.id not in nodes:
            nodes[p.id] = _node_dict(p, 1, "citing")
        _add_edge(p.id, center.id, "citation", cit.citation_type)

    # 4) 二度展开（depth=2）：仅对一度引用邻居再做一次引用展开（避免 N² 爆炸）
    if depth >= 2:
        first_hop_ids = [
            nid for nid, n in nodes.items()
            if n["distance"] == 1 and n["relation"] in ("cited", "citing")
        ]
        for nid in first_hop_ids:
            # 该节点引用了谁
            rows = (
                db.query(Citation, PatentModel)
                .join(PatentModel, PatentModel.id == Citation.cited_patent_id)
                .filter(Citation.citing_patent_id == nid)
                .all()
            )
            for cit, p in rows:
                if p.id not in nodes:
                    nodes[p.id] = _node_dict(p, 2, "cited")
                _add_edge(nid, p.id, "citation", cit.citation_type)
            # 该节点被谁引用
            rows = (
                db.query(Citation, PatentModel)
                .join(PatentModel, PatentModel.id == Citation.citing_patent_id)
                .filter(Citation.cited_patent_id == nid)
                .all()
            )
            for cit, p in rows:
                if p.id not in nodes:
                    nodes[p.id] = _node_dict(p, 2, "citing")
                _add_edge(p.id, nid, "citation", cit.citation_type)

    return {
        "center_id": center.id,
        "depth": depth,
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "family_count": sum(1 for n in nodes.values() if n["relation"] == "family"),
            "cited_count": sum(1 for n in nodes.values() if n["relation"] == "cited"),
            "citing_count": sum(1 for n in nodes.values() if n["relation"] == "citing"),
        },
    }


class CitationCreateRequest(BaseModel):
    """P2-7：手动添加引用关系。"""
    cited_patent_id: int
    citation_type: str = "citation"


@router.post("/{patent_id}/citations")
def add_citation(
    patent_id: int,
    req: CitationCreateRequest,
    db: Session = Depends(get_db),
):
    """P2-7：为 patent_id 添加一条引用关系（patent_id → cited_patent_id）。"""
    from app.models.patent import Patent as PatentModel, Citation

    if patent_id == req.cited_patent_id:
        raise HTTPException(status_code=400, detail="不能引用自身")
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    cited = PatentService.get_patent(db, req.cited_patent_id)
    if not cited:
        raise HTTPException(status_code=404, detail=f"Cited patent {req.cited_patent_id} not found")

    # 幂等：若已存在则返回已存在
    existing = (
        db.query(Citation)
        .filter(
            Citation.citing_patent_id == patent_id,
            Citation.cited_patent_id == req.cited_patent_id,
        )
        .first()
    )
    if existing:
        return {"success": True, "id": existing.id, "already_exists": True}

    cit = Citation(
        citing_patent_id=patent_id,
        cited_patent_id=req.cited_patent_id,
        citation_type=req.citation_type,
    )
    db.add(cit)
    db.commit()
    db.refresh(cit)
    return {"success": True, "id": cit.id, "already_exists": False}


@router.delete("/{patent_id}/citations/{cited_patent_id}")
def remove_citation(
    patent_id: int,
    cited_patent_id: int,
    db: Session = Depends(get_db),
):
    """P2-7：删除 patent_id → cited_patent_id 的引用关系。"""
    from app.models.patent import Citation

    cit = (
        db.query(Citation)
        .filter(
            Citation.citing_patent_id == patent_id,
            Citation.cited_patent_id == cited_patent_id,
        )
        .first()
    )
    if not cit:
        raise HTTPException(status_code=404, detail="Citation not found")
    db.delete(cit)
    db.commit()
    return {"success": True}


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


# ============================================================
# P2-3：AI 字段值人工覆盖
# ============================================================

class AIValueOverrideRequest(BaseModel):
    """人工覆盖 AI 字段值。"""
    value: Optional[str] = None  # None 表示取消覆盖
    changed_by: Optional[str] = None


@router.get("/{patent_id}/ai-values")
def get_ai_values(patent_id: int, db: Session = Depends(get_db)):
    """P2-3：列出该专利所有 AI 字段的当前值与覆盖状态。"""
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

    rows = (
        db.query(AIFieldValue)
        .filter(AIFieldValue.patent_id == patent_id)
        .all()
    )
    # 字段名映射
    field_name_map: dict[str, str] = {}
    for cf in db.query(CustomField).all():
        field_name_map[cf.key] = cf.name

    return [
        {
            "id": r.id,
            "field_key": r.field_key,
            "field_name": field_name_map.get(r.field_key, r.field_key),
            "ai_value": r.value,
            "model_name": r.model_name,
            "is_overridden": bool(r.is_overridden),
            "display_value": r.overridden_value if r.is_overridden else r.value,
            "overridden_value": r.overridden_value if r.is_overridden else None,
            "overridden_at": r.overridden_at.isoformat() if r.overridden_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.put("/{patent_id}/ai-values/{field_key}")
def override_ai_value(
    patent_id: int,
    field_key: str,
    req: AIValueOverrideRequest,
    db: Session = Depends(get_db),
):
    """P2-3：人工覆盖某个 AI 字段值（写入 overridden_value，is_overridden=True）。

    若 req.value 为 None，则取消覆盖，恢复显示 AI 原值。
    同时把覆盖写回 Patent.ai_fields（与显示保持一致）并记一条历史。
    """
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

    row = (
        db.query(AIFieldValue)
        .filter(
            AIFieldValue.patent_id == patent_id,
            AIFieldValue.field_key == field_key,
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"AI 字段值不存在：patent_id={patent_id}, field_key={field_key}（请先运行 AI 提取）",
        )

    ai_value = row.value
    old_display = row.overridden_value if row.is_overridden else row.value

    if req.value is None:
        # 取消覆盖
        row.is_overridden = False
        row.overridden_value = None
        row.overridden_at = None
        new_display = ai_value
    else:
        row.is_overridden = True
        row.overridden_value = req.value
        row.overridden_at = datetime.utcnow()
        new_display = req.value

    # 同步写回 patent.ai_fields（便于在列表/筛选中看到覆盖后的值）
    current_ai = dict(patent.ai_fields or {})
    current_ai[field_key] = new_display
    patent.ai_fields = current_ai

    # 记录历史
    field_display_name = field_key
    cf = db.query(CustomField).filter(CustomField.key == field_key).first()
    if cf:
        field_display_name = cf.name

    hist = PatentHistory(
        patent_id=patent_id,
        field_key=f"ai_fields.{field_key}",
        field_display_name=field_display_name,
        old_value=old_display or "",
        new_value=new_display or "",
        source="manual",
        changed_by=req.changed_by or "manual",
    )
    db.add(hist)
    db.add(row)
    db.add(patent)
    db.commit()
    db.refresh(row)

    return {
        "id": row.id,
        "field_key": row.field_key,
        "ai_value": row.value,
        "is_overridden": bool(row.is_overridden),
        "display_value": row.overridden_value if row.is_overridden else row.value,
        "overridden_value": row.overridden_value if row.is_overridden else None,
        "overridden_at": row.overridden_at.isoformat() if row.overridden_at else None,
    }


@router.delete("/{patent_id}/ai-values/{field_key}/override")
def clear_ai_override(
    patent_id: int,
    field_key: str,
    db: Session = Depends(get_db),
):
    """P2-3：取消 AI 字段的人工覆盖，恢复显示 AI 原值。"""
    patent = PatentService.get_patent(db, patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

    row = (
        db.query(AIFieldValue)
        .filter(
            AIFieldValue.patent_id == patent_id,
            AIFieldValue.field_key == field_key,
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"AI 字段值不存在：patent_id={patent_id}, field_key={field_key}",
        )

    old_display = row.overridden_value if row.is_overridden else row.value
    row.is_overridden = False
    row.overridden_value = None
    row.overridden_at = None

    # 同步回 patent.ai_fields
    current_ai = dict(patent.ai_fields or {})
    current_ai[field_key] = row.value
    patent.ai_fields = current_ai

    field_display_name = field_key
    cf = db.query(CustomField).filter(CustomField.key == field_key).first()
    if cf:
        field_display_name = cf.name

    hist = PatentHistory(
        patent_id=patent_id,
        field_key=f"ai_fields.{field_key}",
        field_display_name=field_display_name,
        old_value=old_display or "",
        new_value=row.value or "",
        source="manual",
        changed_by="manual",
    )
    db.add(hist)
    db.add(row)
    db.add(patent)
    db.commit()

    return {
        "id": row.id,
        "field_key": row.field_key,
        "ai_value": row.value,
        "is_overridden": False,
        "display_value": row.value,
    }
