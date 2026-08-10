"""Attachment upload and safe file access API."""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Attachment, Patent
from app.services.attachment_service import AttachmentService
from app.core.exceptions import BadRequestException, NotFoundException


router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("/upload")
def upload_attachment(
    database_id: int = Form(...),
    patent_id: int = Form(...),
    field_key: str = Form(...),
    uploaded_by: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        return AttachmentService.upload(db, database_id, patent_id, field_key, file, uploaded_by)
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc


@router.get("/patent/{patent_id}")
def list_patent_attachments(
    patent_id: int,
    field_key: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if not db.query(Patent).filter(Patent.id == patent_id).first():
        raise NotFoundException("Patent not found")
    return AttachmentService.list_for_patent(db, patent_id, field_key)


def _file_response(attachment: Attachment, inline: bool) -> FileResponse:
    try:
        path = AttachmentService.path(attachment)
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    if not path.exists():
        raise NotFoundException("附件文件不存在")
    disposition = "inline" if inline else "attachment"
    return FileResponse(
        path,
        media_type=attachment.mime_type,
        filename=attachment.filename,
    headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(attachment.filename)}"},
    )


@router.get("/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
    try:
        return _file_response(AttachmentService.get(db, attachment_id), inline=False)
    except ValueError as exc:
        raise NotFoundException(str(exc)) from exc


@router.get("/{attachment_id}/preview")
def preview_attachment(attachment_id: int, db: Session = Depends(get_db)):
    try:
        return _file_response(AttachmentService.get(db, attachment_id), inline=True)
    except ValueError as exc:
        raise NotFoundException(str(exc)) from exc


@router.delete("/{attachment_id}")
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    try:
        AttachmentService.delete(db, attachment_id)
    except ValueError as exc:
        raise NotFoundException(str(exc)) from exc
    return {"success": True}
