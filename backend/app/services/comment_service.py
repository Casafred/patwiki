"""Comment CRUD and mention extraction for collaborative patent review."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Comment, Patent


MENTION_PATTERN = re.compile(r"@([A-Za-z0-9_.-]{1,100})")


class CommentService:
    MAX_CONTENT_LENGTH = 10_000

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @classmethod
    def extract_mentions(cls, content: str) -> list[str]:
        seen: set[str] = set()
        mentions: list[str] = []
        for username in MENTION_PATTERN.findall(content):
            if username.casefold() not in seen:
                seen.add(username.casefold())
                mentions.append(username)
        return mentions

    @staticmethod
    def _patent(db: Session, patent_id: int) -> Patent:
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        if not patent:
            raise ValueError("专利不存在")
        return patent

    @classmethod
    def _comment_dict(cls, comment: Comment) -> dict:
        return {
            "id": comment.id,
            "patent_id": comment.patent_id,
            "parent_id": comment.parent_id,
            "author_id": comment.author_id,
            "author_name": comment.author_name,
            "field_key": comment.field_key,
            "content": comment.content,
            "mentions": comment.mentions or [],
            "is_resolved": bool(comment.is_resolved),
            "resolved_by": comment.resolved_by,
            "resolved_at": comment.resolved_at.isoformat() if comment.resolved_at else None,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
            "updated_at": comment.updated_at.isoformat() if comment.updated_at else None,
            "reply_count": len(comment.replies or []),
        }

    @classmethod
    def list_for_patent(
        cls,
        db: Session,
        patent_id: int,
        include_resolved: bool = True,
        field_key: Optional[str] = None,
        limit: int = 500,
    ) -> list[dict]:
        cls._patent(db, patent_id)
        query = db.query(Comment).filter(Comment.patent_id == patent_id)
        if not include_resolved:
            query = query.filter(Comment.is_resolved == False)
        if field_key:
            query = query.filter(Comment.field_key == field_key)
        comments = query.order_by(Comment.id.asc()).limit(limit).all()
        return [cls._comment_dict(comment) for comment in comments]

    @classmethod
    def create(
        cls,
        db: Session,
        patent_id: int,
        content: str,
        author_name: Optional[str] = None,
        author_id: Optional[int] = None,
        parent_id: Optional[int] = None,
        field_key: Optional[str] = None,
    ) -> dict:
        cls._patent(db, patent_id)
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("评论内容不能为空")
        if len(clean_content) > cls.MAX_CONTENT_LENGTH:
            raise ValueError("评论内容不能超过 10000 个字符")
        if parent_id is not None:
            parent = db.query(Comment).filter(
                Comment.id == parent_id,
                Comment.patent_id == patent_id,
            ).first()
            if not parent:
                raise ValueError("回复目标不存在或不属于当前专利")
        comment = Comment(
            patent_id=patent_id,
            parent_id=parent_id,
            author_id=author_id,
            author_name=(author_name or "当前用户").strip()[:100] or "当前用户",
            field_key=field_key.strip()[:200] if field_key and field_key.strip() else None,
            content=clean_content,
            mentions=cls.extract_mentions(clean_content),
        )
        db.add(comment)
        db.commit()
        db.refresh(comment)
        return cls._comment_dict(comment)

    @classmethod
    def get(cls, db: Session, comment_id: int) -> Comment:
        comment = db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise ValueError("评论不存在")
        return comment

    @classmethod
    def update(cls, db: Session, comment_id: int, content: str) -> dict:
        comment = cls.get(db, comment_id)
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("评论内容不能为空")
        if len(clean_content) > cls.MAX_CONTENT_LENGTH:
            raise ValueError("评论内容不能超过 10000 个字符")
        comment.content = clean_content
        comment.mentions = cls.extract_mentions(clean_content)
        db.add(comment)
        db.commit()
        db.refresh(comment)
        return cls._comment_dict(comment)

    @classmethod
    def resolve(cls, db: Session, comment_id: int, resolved: bool, resolved_by: Optional[str] = None) -> dict:
        comment = cls.get(db, comment_id)
        comment.is_resolved = resolved
        comment.resolved_by = (resolved_by or "当前用户").strip()[:100] if resolved else None
        comment.resolved_at = cls._now() if resolved else None
        db.add(comment)
        db.commit()
        db.refresh(comment)
        return cls._comment_dict(comment)

    @classmethod
    def delete(cls, db: Session, comment_id: int) -> bool:
        comment = cls.get(db, comment_id)
        db.delete(comment)
        db.commit()
        return True
