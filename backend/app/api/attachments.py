"""Attachment upload and safe file access API."""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Attachment, Patent, Project, ProjectAttachment
from app.services.attachment_service import AttachmentService
from app.services.project_attachment_service import ProjectAttachmentService
from app.core.exceptions import BadRequestException, NotFoundException


router = APIRouter(prefix="/attachments", tags=["attachments"])


class AttachmentNoteUpdate(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


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


@router.get("/library")
def list_attachment_library(db: Session = Depends(get_db)):
    items = []
    for attachment in db.query(Attachment).order_by(Attachment.uploaded_at.desc(), Attachment.id.desc()).all():
        item = AttachmentService._metadata(attachment)
        patent = db.query(Patent).filter(Patent.id == attachment.patent_id).first()
        item["owner_label"] = f"专利 · {patent.publication_number if patent and patent.publication_number else '无公开号'} · {patent.title if patent else '已删除专利'}"
        items.append(item)
    for attachment in db.query(ProjectAttachment).order_by(ProjectAttachment.uploaded_at.desc(), ProjectAttachment.id.desc()).all():
        item = ProjectAttachmentService._metadata(attachment)
        project = db.query(Project).filter(Project.id == attachment.project_id).first()
        patent = db.query(Patent).filter(Patent.id == attachment.patent_id).first() if attachment.patent_id else None
        item["owner_label"] = f"项目 · {project.name if project else '已删除项目'}"
        if patent:
            item["owner_label"] += f" · 关联专利：{patent.publication_number if patent.publication_number else '无公开号'} · {patent.title}"
        items.append(item)
    return sorted(items, key=lambda item: item.get("uploaded_at") or "", reverse=True)


@router.get("/projects/{project_id}")
def list_project_attachments(project_id: int, db: Session = Depends(get_db)):
    try:
        return ProjectAttachmentService.list_for_project(db, project_id)
    except ValueError as exc:
        raise NotFoundException(str(exc)) from exc


@router.post("/projects/{project_id}")
def upload_project_attachment(
    project_id: int,
    scope: str = Form("project"),
    patent_id: int | None = Form(None),
    note: str | None = Form(None),
    uploaded_by: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        return ProjectAttachmentService.upload(
            db, project_id, file, scope=scope, patent_id=patent_id,
            note=note, uploaded_by=uploaded_by,
        )
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc


@router.get("/project/{attachment_id}/download")
def download_project_attachment(attachment_id: int, db: Session = Depends(get_db)):
    try:
        return _file_response(ProjectAttachmentService.get(db, attachment_id), inline=False)
    except ValueError as exc:
        raise NotFoundException(str(exc)) from exc


@router.get("/project/{attachment_id}/preview")
def preview_project_attachment(attachment_id: int, db: Session = Depends(get_db)):
    try:
        return _file_response(ProjectAttachmentService.get(db, attachment_id), inline=True)
    except ValueError as exc:
        raise NotFoundException(str(exc)) from exc


@router.patch("/project/{attachment_id}")
def update_project_attachment(attachment_id: int, body: AttachmentNoteUpdate, db: Session = Depends(get_db)):
    try:
        return ProjectAttachmentService.update_note(db, attachment_id, body.note)
    except ValueError as exc:
        raise NotFoundException(str(exc)) from exc


@router.delete("/project/{attachment_id}")
def delete_project_attachment(attachment_id: int, db: Session = Depends(get_db)):
    try:
        ProjectAttachmentService.delete(db, attachment_id)
    except ValueError as exc:
        raise NotFoundException(str(exc)) from exc
    return {"success": True}


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


@router.patch("/{attachment_id}")
def update_attachment(attachment_id: int, body: AttachmentNoteUpdate, db: Session = Depends(get_db)):
    try:
        return AttachmentService.update_note(db, attachment_id, body.note)
    except ValueError as exc:
        raise NotFoundException(str(exc)) from exc


@router.delete("/{attachment_id}")
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    try:
        AttachmentService.delete(db, attachment_id)
    except ValueError as exc:
        raise NotFoundException(str(exc)) from exc
    return {"success": True}
