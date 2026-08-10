"""Collaborative comments API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Comment
from app.schemas.schemas import CommentCreate, CommentResolveRequest, CommentUpdate
from app.services.comment_service import CommentService


router = APIRouter(tags=["comments"])


def _handle_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    status = 404 if message in {"专利不存在", "评论不存在"} else 400
    return HTTPException(status_code=status, detail=message)


@router.get("/patents/{patent_id}/comments")
def list_comments(
    patent_id: int,
    include_resolved: bool = True,
    field_key: Optional[str] = None,
    limit: int = Query(500, ge=1, le=500),
    db: Session = Depends(get_db),
):
    try:
        return CommentService.list_for_patent(db, patent_id, include_resolved, field_key, limit)
    except ValueError as exc:
        raise _handle_error(exc) from exc


@router.post("/patents/{patent_id}/comments")
def create_comment(patent_id: int, body: CommentCreate, db: Session = Depends(get_db)):
    try:
        return CommentService.create(
            db,
            patent_id,
            body.content,
            body.author_name,
            body.author_id,
            body.parent_id,
            body.field_key,
        )
    except ValueError as exc:
        raise _handle_error(exc) from exc


@router.get("/comments/{comment_id}")
def get_comment(comment_id: int, db: Session = Depends(get_db)):
    try:
        return CommentService._comment_dict(CommentService.get(db, comment_id))
    except ValueError as exc:
        raise _handle_error(exc) from exc


@router.get("/comments/{comment_id}/thread")
def get_comment_thread(comment_id: int, db: Session = Depends(get_db)):
    try:
        comment = CommentService.get(db, comment_id)
        return CommentService.list_for_patent(db, comment.patent_id)
    except ValueError as exc:
        raise _handle_error(exc) from exc


@router.put("/comments/{comment_id}")
def update_comment(comment_id: int, body: CommentUpdate, db: Session = Depends(get_db)):
    try:
        return CommentService.update(db, comment_id, body.content)
    except ValueError as exc:
        raise _handle_error(exc) from exc


@router.post("/comments/{comment_id}/resolve")
def resolve_comment(comment_id: int, body: CommentResolveRequest, db: Session = Depends(get_db)):
    try:
        return CommentService.resolve(db, comment_id, body.resolved, body.resolved_by)
    except ValueError as exc:
        raise _handle_error(exc) from exc


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, db: Session = Depends(get_db)):
    try:
        CommentService.delete(db, comment_id)
    except ValueError as exc:
        raise _handle_error(exc) from exc
    return {"success": True}
