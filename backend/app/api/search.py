"""面向列表搜索框的轻量自动补全。"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Patent

router = APIRouter(tags=["search"])


SUGGESTION_FIELDS = (
    ("title", "标题"),
    ("application_number", "申请号"),
    ("publication_number", "公开号"),
    ("applicant", "申请人"),
    ("inventor", "发明人"),
    ("category", "分类"),
)


@router.get("/search/suggest")
def suggest_search_terms(
    q: str = Query("", max_length=200),
    database_id: Optional[int] = None,
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    term = q.strip()
    if not term:
        return []

    search_term = f"%{term}%"
    query = db.query(Patent).filter(or_(*(
        getattr(Patent, field).ilike(search_term)
        for field, _ in SUGGESTION_FIELDS
    )))
    if database_id is not None:
        query = query.filter(Patent.database_id == database_id)

    patents = query.order_by(Patent.updated_at.desc(), Patent.id.desc()).limit(min(limit * 5, 100)).all()
    folded_term = term.casefold()
    suggestions: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for patent in patents:
        for field, field_label in SUGGESTION_FIELDS:
            raw_value = getattr(patent, field, None)
            if not raw_value:
                continue
            value = str(raw_value).strip()
            folded_value = value.casefold()
            if folded_term not in folded_value:
                continue
            key = (field, folded_value)
            if key in seen:
                continue
            seen.add(key)
            rank = 0 if folded_value == folded_term else (1 if folded_value.startswith(folded_term) else 2)
            suggestions.append({
                "kind": field,
                "kind_label": field_label,
                "value": value,
                "label": value,
                "patent_id": patent.id,
                "patent_title": patent.title,
                "rank": rank,
            })

    suggestions.sort(key=lambda item: (item["rank"], item["kind"], item["value"].casefold()))
    for item in suggestions:
        item.pop("rank", None)
    return suggestions[:limit]
