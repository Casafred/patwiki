"""通用 Link / Lookup / Rollup API。"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.schemas import (
    LinkCreateRequest,
    LinkDeleteRequest,
    LinkRecord,
    RelationBatchRequest,
    RelationResolveRequest,
)
from app.services.link_service import (
    create_link,
    list_links,
    remove_link,
    resolve_lookup,
    resolve_relation_batch,
    resolve_rollup,
    search_targets,
)

router = APIRouter(tags=["links"])


def _relation_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@router.post("/links", response_model=LinkRecord)
def create_cross_table_link(request: LinkCreateRequest, db: Session = Depends(get_db)):
    try:
        link = create_link(
            db,
            field_key=request.field_key,
            source_record_id=request.source_record_id,
            target_record_id=request.target_record_id,
            source_table=request.source_table,
            created_by=request.created_by,
        )
        records = list_links(db, request.field_key, request.source_record_id, request.source_table)
        result = next((record for record in records if record["id"] == link.id), None)
        if not result:
            raise HTTPException(status_code=500, detail="关联创建后无法读取记录")
        return result
    except ValueError as error:
        raise _relation_error(error) from error


@router.delete("/links")
def delete_cross_table_link(request: LinkDeleteRequest, db: Session = Depends(get_db)):
    try:
        removed = remove_link(
            db,
            field_key=request.field_key,
            source_record_id=request.source_record_id,
            target_record_id=request.target_record_id,
            source_table=request.source_table,
        )
    except ValueError as error:
        raise _relation_error(error) from error
    if not removed:
        raise HTTPException(status_code=404, detail="关联不存在")
    return {"success": True}


@router.get("/links/search")
def search_cross_table_links(
    field_key: str,
    search: str = "",
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    try:
        return search_targets(db, field_key, search, limit)
    except ValueError as error:
        raise _relation_error(error) from error


@router.get("/links/{field_key}/{record_id}", response_model=list[LinkRecord])
def get_cross_table_links(
    field_key: str,
    record_id: int,
    source_table: str = "patents",
    db: Session = Depends(get_db),
):
    try:
        return list_links(db, field_key, record_id, source_table)
    except ValueError as error:
        raise _relation_error(error) from error


@router.post("/lookup/resolve")
def resolve_lookup_value(request: RelationResolveRequest, db: Session = Depends(get_db)):
    try:
        return resolve_lookup(db, request.field_key, request.record_id, request.source_table)
    except ValueError as error:
        raise _relation_error(error) from error


@router.post("/rollup/resolve")
def resolve_rollup_value(request: RelationResolveRequest, db: Session = Depends(get_db)):
    try:
        return resolve_rollup(db, request.field_key, request.record_id, request.source_table)
    except ValueError as error:
        raise _relation_error(error) from error


@router.post("/relations/resolve-batch")
def resolve_relations_batch(request: RelationBatchRequest, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if len(request.record_ids) > 200:
        raise HTTPException(status_code=400, detail="单次最多解析 200 条记录")
    try:
        return resolve_relation_batch(db, request.field_key, request.record_ids, request.source_table)
    except ValueError as error:
        raise _relation_error(error) from error
