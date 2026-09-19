"""Attachment storage, metadata and safe file access."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Attachment, Patent, PatentDatabaseMembership
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
        "image/bmp": {".bmp"},
        "image/tiff": {".tif", ".tiff"},
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
            (Patent.database_id == database_id) | db.query(PatentDatabaseMembership.id).filter(
                PatentDatabaseMembership.database_id == database_id,
                PatentDatabaseMembership.patent_id == Patent.id,
            ).exists(),
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
            "source_type": attachment.source_type or "manual_upload",
            "import_batch_id": attachment.import_batch_id,
            "source_sheet": attachment.source_sheet,
            "source_cell": attachment.source_cell,
            "source_row": attachment.source_row,
            "source_column": attachment.source_column,
            "source_url": attachment.source_url,
            "sha256": attachment.sha256,
            "width": attachment.width,
            "height": attachment.height,
            "is_image": attachment.mime_type.startswith("image/"),
            "download_url": f"/api/attachments/{attachment.id}/download",
            "preview_url": f"/api/attachments/{attachment.id}/preview",
        }

    @classmethod
    def create_from_bytes(
        cls,
        db: Session,
        database_id: int,
        patent_id: int,
        field_key: str,
        filename: str,
        content: bytes,
        mime_type: str,
        *,
        uploaded_by: Optional[str] = None,
        source_type: str = "manual_upload",
        import_batch_id: int | None = None,
        source_sheet: str | None = None,
        source_cell: str | None = None,
        source_row: int | None = None,
        source_column: int | None = None,
        source_url: str | None = None,
        width: int | None = None,
        height: int | None = None,
        commit: bool = True,
        update_projection: bool = True,
    ) -> dict:
        """Persist one attachment without putting binary data in SQLite.

        Import callers pass ``commit=False`` so the patent, attachment and
        import batch are committed as one transaction.
        """
        normalized_key = cls._field_key(db, field_key)
        patent = cls._patent(db, database_id, patent_id)
        safe_filename = Path(filename or "attachment").name
        extension = Path(safe_filename).suffix.lower()
        normalized_mime = (mime_type or "").lower()
        expected_mime_type = cls.EXTENSION_MIME_TYPES.get(extension)
        if not expected_mime_type or not normalized_mime.startswith(("image/", "application/", "text/", "message/")):
            raise ValueError("不支持的附件类型")
        if normalized_mime == "application/octet-stream" and expected_mime_type:
            normalized_mime = expected_mime_type
        if len(content) > cls.MAX_FILE_SIZE:
            raise ValueError("附件大小不能超过 50MB")

        relative_dir = Path("attachments") / str(database_id) / str(patent_id)
        target_dir = settings.FILES_DIR / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid4().hex}{extension}"
        target_path = target_dir / stored_name
        try:
            target_path.write_bytes(content)
            relative_path = str(relative_dir / stored_name).replace("\\", "/")
            attachment = Attachment(
                database_id=database_id,
                patent_id=patent_id,
                field_key=normalized_key,
                filename=safe_filename,
                file_path=relative_path,
                file_size=len(content),
                mime_type=normalized_mime,
                uploaded_by=uploaded_by,
                uploaded_at=datetime.now(timezone.utc).replace(tzinfo=None),
                source_type=source_type,
                import_batch_id=import_batch_id,
                source_sheet=source_sheet,
                source_cell=source_cell,
                source_row=source_row,
                source_column=source_column,
                source_url=source_url,
                sha256=sha256(content).hexdigest(),
                width=width,
                height=height,
            )
            db.add(attachment)
            db.flush()
            if update_projection:
                current = list((patent.custom_fields or {}).get(normalized_key) or [])
                current.append(cls._metadata(attachment))
                PatentService.update_patent(
                    db,
                    patent,
                    {"custom_fields": {normalized_key: current}},
                    source="attachment",
                    changed_by=uploaded_by,
                    commit=commit,
                )
            if commit:
                db.refresh(attachment)
            return cls._metadata(attachment)
        except Exception:
            if commit:
                db.rollback()
            if target_path.exists():
                target_path.unlink()
            raise

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

        content = upload.file.read(cls.MAX_FILE_SIZE + 1)
        return cls.create_from_bytes(
            db,
            database_id,
            patent_id,
            field_key,
            filename,
            content,
            mime_type,
            uploaded_by=uploaded_by,
        )

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
