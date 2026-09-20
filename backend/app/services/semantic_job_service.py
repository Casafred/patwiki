"""Background execution for durable semantic-index jobs and outbox events."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import SemanticIndexJob, SemanticIndexOutbox, SemanticSearchProfile
from app.services.semantic_index_service import SemanticIndexService


class SemanticJobService:
    @classmethod
    def run_due(cls, db: Session, limit: int = 1) -> list[dict]:
        """Run bounded work per scheduler tick so CRUD requests remain independent."""
        completed: list[dict] = []
        jobs = db.query(SemanticIndexJob).filter(SemanticIndexJob.status == "pending").order_by(SemanticIndexJob.id).limit(limit).all()
        for job in jobs:
            completed.append(SemanticIndexService.job_dict(SemanticIndexService.run_job(db, job)))
        # Existing SQLite columns store naive UTC timestamps.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        due_outbox = db.query(SemanticIndexOutbox).filter(or_(
            SemanticIndexOutbox.status == "pending",
            (SemanticIndexOutbox.status == "retry_wait") & (SemanticIndexOutbox.next_retry_at <= now),
        )).order_by(SemanticIndexOutbox.id).limit(100).all()
        for item in due_outbox:
            try:
                if SemanticIndexService.apply_outbox(db, item):
                    item.status = "completed"
                    item.completed_at = now
            except Exception as exc:
                item.attempt_count += 1
                item.last_error_code = getattr(exc, "code", "SEMANTIC_INDEX_FAILED")
                if item.attempt_count >= 3:
                    item.status = "failed"
                else:
                    item.status = "retry_wait"
                    item.next_retry_at = now + timedelta(minutes=2 ** (item.attempt_count - 1))
        db.commit()
        return completed
