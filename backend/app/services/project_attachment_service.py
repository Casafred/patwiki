"""Project-owned attachments stored beside patent attachment files."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Patent, Project, ProjectAttachment
from app.services.attachment_service import AttachmentService


class ProjectAttachmentService:
    @staticmethod
    def _metadata(item: ProjectAttachment) -> dict:
        prefix = f"/api/attachments/project/{item.id}"
        return {
            "id": f"project_att_{item.id}",
            "attachment_id": item.id,
            "attachment_type": "project",
            "project_id": item.project_id,
            "patent_id": item.patent_id,
            "scope": item.scope,
            "filename": item.filename,
            "file_path": item.file_path,
            "file_size": item.file_size,
            "mime_type": item.mime_type,
            "note": item.note,
            "uploaded_by": item.uploaded_by,
            "uploaded_at": item.uploaded_at.isoformat() if item.uploaded_at else None,
            "download_url": f"{prefix}/download",
            "preview_url": f"{prefix}/preview",
            "is_image": item.mime_type.startswith("image/"),
        }

    @classmethod
    def upload(
        cls,
        db: Session,
        project_id: int,
        upload: UploadFile,
        *,
        scope: str,
        patent_id: int | None = None,
        note: str | None = None,
        uploaded_by: str | None = None,
    ) -> dict:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError("项目不存在")
        if scope not in {"project", "project_patent"}:
            raise ValueError("附件用途无效")
        if scope == "project" and patent_id is not None:
            raise ValueError("项目资料附件不能指定专利")
        if scope == "project_patent":
            if patent_id is None:
                raise ValueError("项目与专利关系说明必须选择专利")
            patent = db.query(Patent).filter(Patent.id == patent_id).first()
            if not patent or project not in patent.projects:
                raise ValueError("该专利尚未关联此项目")

        filename = Path(upload.filename or "attachment").name
        extension = Path(filename).suffix.lower()
        mime_type = (upload.content_type or "").lower()
        expected_type = AttachmentService.EXTENSION_MIME_TYPES.get(extension)
        if not expected_type:
            raise ValueError("不支持的附件类型，仅允许 PDF、图片、Office 文档或 Outlook 邮件")
        if mime_type in {"", "application/octet-stream"} or extension not in AttachmentService.ALLOWED_TYPES.get(mime_type, set()):
            mime_type = expected_type
        content = upload.file.read(AttachmentService.MAX_FILE_SIZE + 1)
        if len(content) > AttachmentService.MAX_FILE_SIZE:
            raise ValueError("附件大小不能超过 50MB")

        relative_dir = Path("attachments") / "projects" / str(project_id)
        target_dir = settings.FILES_DIR / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{uuid4().hex}{extension}"
        target_path.write_bytes(content)
        item = ProjectAttachment(
            project_id=project_id,
            patent_id=patent_id,
            scope=scope,
            filename=filename,
            file_path=str(relative_dir / target_path.name).replace("\\", "/"),
            file_size=len(content),
            mime_type=mime_type,
            note=note.strip() if note and note.strip() else None,
            uploaded_by=uploaded_by,
            uploaded_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        try:
            db.add(item)
            db.commit()
            db.refresh(item)
            return cls._metadata(item)
        except Exception:
            db.rollback()
            if target_path.exists():
                target_path.unlink()
            raise

    @classmethod
    def list_for_project(cls, db: Session, project_id: int) -> list[dict]:
        if not db.query(Project.id).filter(Project.id == project_id).first():
            raise ValueError("项目不存在")
        return [cls._metadata(item) for item in db.query(ProjectAttachment).filter(
            ProjectAttachment.project_id == project_id,
            ProjectAttachment.deleted_at.is_(None),
        ).order_by(ProjectAttachment.id.desc()).all()]

    @classmethod
    def get(cls, db: Session, attachment_id: int) -> ProjectAttachment:
        item = db.query(ProjectAttachment).filter(ProjectAttachment.id == attachment_id).first()
        if not item:
            raise ValueError("项目附件不存在")
        return item

    @classmethod
    def update_note(cls, db: Session, attachment_id: int, note: str | None) -> dict:
        item = cls.get(db, attachment_id)
        item.note = note.strip() if note and note.strip() else None
        db.commit()
        db.refresh(item)
        return cls._metadata(item)

    @classmethod
    def delete(cls, db: Session, attachment_id: int) -> None:
        item = cls.get(db, attachment_id)
        item.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
