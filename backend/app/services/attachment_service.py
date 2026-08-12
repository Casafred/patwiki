"""Attachment storage, metadata and safe file access."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Attachment, Patent
from app.services.field_registry import get_all_fields_meta
from app.services.patent_service import PatentService


class AttachmentService:
    MAX_FILE_SIZE = 50 * 1024 * 1024
    ALLOWED_TYPES: dict[str, set[str]] = {
        "application/pdf": {".pdf"},
        "image/png": {".png"},
        "image/jpeg": {".jpg", ".jpeg"},
        "image/gif": {".gif"},
        "image/webp": {".webp"},
        "application/msword": {".doc"},
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
        "application/vnd.ms-powerpoint": {".ppt"},
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": {".pptx"},
        "application/vnd.ms-excel": {".xls"},
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
        "text/csv": {".csv"},
        "message/rfc822": {".eml"},
        "application/vnd.ms-outlook": {".msg"},
    }

    EXTENSION_MIME_TYPES: dict[str, str] = {
        extension: mime_type
        for mime_type, extensions in ALLOWED_TYPES.items()
        for extension in extensions
    }

    @classmethod
    def _field_key(cls, db: Session, field_key: str) -> str:
        normalized = field_key.removeprefix("custom_fields.")
        metadata = next((item for item in get_all_fields_meta(db) if item["key"] == normalized), None)
        if not metadata or metadata.get("field_type") != "attachment":
            raise ValueError("目标字段不是附件字段")
        return normalized

    @staticmethod
    def _patent(db: Session, database_id: int, patent_id: int) -> Patent:
        patent = db.query(Patent).filter(
            Patent.id == patent_id,
            Patent.database_id == database_id,
        ).first()
        if not patent:
            raise ValueError("专利不属于指定数据库")
        return patent

    @staticmethod
    def _metadata(attachment: Attachment) -> dict:
        return {
            "id": f"att_{attachment.id}",
            "attachment_id": attachment.id,
            "filename": attachment.filename,
            "file_path": attachment.file_path,
            "file_size": attachment.file_size,
            "mime_type": attachment.mime_type,
            "uploaded_by": attachment.uploaded_by,
            "uploaded_at": attachment.uploaded_at.isoformat() if attachment.uploaded_at else None,
            "download_url": f"/api/attachments/{attachment.id}/download",
            "preview_url": f"/api/attachments/{attachment.id}/preview",
        }

    @classmethod
    def upload(
        cls,
        db: Session,
        database_id: int,
        patent_id: int,
        field_key: str,
        upload: UploadFile,
        uploaded_by: Optional[str] = None,
    ) -> dict:
        normalized_key = cls._field_key(db, field_key)
        patent = cls._patent(db, database_id, patent_id)
        filename = Path(upload.filename or "attachment").name
        extension = Path(filename).suffix.lower()
        mime_type = (upload.content_type or "").lower()
        expected_mime_type = cls.EXTENSION_MIME_TYPES.get(extension)
        if not expected_mime_type:
            raise ValueError("不支持的附件类型，仅允许 PDF、图片、Word、Excel、PPT 或 Outlook 邮件")
        # Browsers often report Office and Outlook files as application/octet-stream.
        # The extension remains the allow-list boundary and the stored MIME type is normalized.
        if mime_type in {"", "application/octet-stream"} or extension not in cls.ALLOWED_TYPES.get(mime_type, set()):
            mime_type = expected_mime_type

        relative_dir = Path("attachments") / str(database_id) / str(patent_id)
        target_dir = settings.FILES_DIR / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid4().hex}{extension}"
        target_path = target_dir / stored_name
        size = 0
        try:
            with target_path.open("wb") as output:
                while True:
                    chunk = upload.file.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > cls.MAX_FILE_SIZE:
                        raise ValueError("附件大小不能超过 50MB")
                    output.write(chunk)

            relative_path = str(relative_dir / stored_name).replace("\\", "/")
            attachment = Attachment(
                database_id=database_id,
                patent_id=patent_id,
                field_key=normalized_key,
                filename=filename,
                file_path=relative_path,
                file_size=size,
                mime_type=mime_type,
                uploaded_by=uploaded_by,
                uploaded_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.add(attachment)
            db.flush()
            current = list((patent.custom_fields or {}).get(normalized_key) or [])
            current.append(cls._metadata(attachment))
            PatentService.update_patent(
                db,
                patent,
                {"custom_fields": {normalized_key: current}},
                source="attachment",
                changed_by=uploaded_by,
            )
            db.refresh(attachment)
            return cls._metadata(attachment)
        except Exception:
            db.rollback()
            if target_path.exists():
                target_path.unlink()
            raise

    @classmethod
    def list_for_patent(cls, db: Session, patent_id: int, field_key: Optional[str] = None) -> list[dict]:
        query = db.query(Attachment).filter(Attachment.patent_id == patent_id)
        if field_key:
            query = query.filter(Attachment.field_key == field_key.removeprefix("custom_fields."))
        return [cls._metadata(item) for item in query.order_by(Attachment.id).all()]

    @classmethod
    def get(cls, db: Session, attachment_id: int) -> Attachment:
        attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if not attachment:
            raise ValueError("附件不存在")
        return attachment

    @staticmethod
    def path(attachment: Attachment) -> Path:
        base = settings.FILES_DIR.resolve()
        target = (settings.FILES_DIR / attachment.file_path).resolve()
        if os.path.commonpath([str(base), str(target)]) != str(base):
            raise ValueError("附件路径无效")
        return target

    @classmethod
    def delete(cls, db: Session, attachment_id: int) -> bool:
        attachment = cls.get(db, attachment_id)
        patent = db.query(Patent).filter(Patent.id == attachment.patent_id).first()
        if patent:
            current = [
                item for item in (patent.custom_fields or {}).get(attachment.field_key, [])
                if str(item.get("attachment_id", item.get("id", ""))) not in {str(attachment.id), f"att_{attachment.id}"}
            ]
            PatentService.update_patent(
                db,
                patent,
                {"custom_fields": {attachment.field_key: current}},
                source="attachment",
            )
        target = cls.path(attachment)
        db.delete(attachment)
        db.commit()
        if target.exists():
            target.unlink()
        return True
