"""公开表单视图 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.schemas import FormSubmitRequest
from app.services.form_service import FormService


router = APIRouter(prefix="/form", tags=["form"])


@router.get("/shared/{token}")
def get_shared_form(token: str, db: Session = Depends(get_db)):
    link = FormService.get_active_share(db, token)
    if not link:
        raise HTTPException(status_code=404, detail="表单分享链接不存在或已过期")
    try:
        return FormService.get_definition(db, link.view, public=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/shared/{token}/submit")
def submit_shared_form(
    token: str,
    body: FormSubmitRequest,
    db: Session = Depends(get_db),
):
    link = FormService.get_active_share(db, token)
    if not link:
        raise HTTPException(status_code=404, detail="表单分享链接不存在或已过期")
    try:
        patent = FormService.submit(db, link.view, body.data, allow_update=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "patent_id": patent.id}
