"""Background execution for durable semantic-index jobs and outbox events."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import SemanticIndexJob, SemanticIndexOutbox
from app.services.semantic_index_service import SemanticIndexService


class SemanticJobService:
    JOB_LEASE_SECONDS = 600
    OUTBOX_LEASE_SECONDS = 120

    @staticmethod
    def _recover_expired_jobs(db: Session, now: datetime) -> None:
        expired = db.query(SemanticIndexJob).filter(
            SemanticIndexJob.status == "running",
            or_(SemanticIndexJob.lease_expires_at.is_(None), SemanticIndexJob.lease_expires_at <= now),
        ).all()
        for job in expired:
            job.lease_owner, job.lease_expires_at = None, None
            job.error_code, job.error_message = "SEMANTIC_JOB_LEASE_EXPIRED", "Worker lease expired before completion"
            if job.attempt_count >= job.max_attempts:
                job.status = "dead_letter"
            else:
                job.status, job.next_retry_at = "retry_wait", now

    @staticmethod
    def _recover_expired_outbox(db: Session, now: datetime) -> None:
        expired = db.query(SemanticIndexOutbox).filter(
            SemanticIndexOutbox.status == "claimed",
            or_(SemanticIndexOutbox.lease_expires_at.is_(None), SemanticIndexOutbox.lease_expires_at <= now),
        ).all()
        for item in expired:
            item.lease_owner, item.lease_expires_at = None, None
            item.last_error_code = "SEMANTIC_OUTBOX_LEASE_EXPIRED"
            item.attempt_count += 1
            if item.attempt_count >= 3:
                item.status = "dead_letter"
            else:
                item.status, item.next_retry_at = "retry_wait", now

    @classmethod
    def _claim_job(cls, db: Session, job: SemanticIndexJob, now: datetime, owner: str) -> bool:
        if job.status not in {"pending", "retry_wait"}:
            return False
        if job.status == "retry_wait" and job.next_retry_at and job.next_retry_at > now:
            return False
        job.status = "running"
        job.lease_owner, job.lease_expires_at = owner, now + timedelta(seconds=cls.JOB_LEASE_SECONDS)
        job.started_at, job.attempt_count = now, job.attempt_count + 1
        db.commit()
        return True

    @classmethod
    def run_due(cls, db: Session, limit: int = 1) -> list[dict]:
        """Run bounded work per scheduler tick so CRUD requests remain independent."""
        completed: list[dict] = []
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cls._recover_expired_jobs(db, now)
        cls._recover_expired_outbox(db, now)
        owner = f"scheduler-{uuid.uuid4().hex[:12]}"
        jobs = db.query(SemanticIndexJob).filter(or_(
            SemanticIndexJob.status == "pending",
            SemanticIndexJob.status == "retry_wait",
        )).order_by(SemanticIndexJob.id).limit(limit).all()
        for job in jobs:
            if cls._claim_job(db, job, now, owner):
                result = SemanticIndexService.run_job(db, job)
                if result.status == "failed":
                    if result.attempt_count >= result.max_attempts:
                        result.status = "dead_letter"
                    else:
                        result.status = "retry_wait"
                        result.next_retry_at = now + timedelta(minutes=2 ** max(0, result.attempt_count - 1))
                    db.commit()
                completed.append(SemanticIndexService.job_dict(result))
        # Existing SQLite columns store naive UTC timestamps.
        due_outbox = db.query(SemanticIndexOutbox).filter(or_(
            SemanticIndexOutbox.status == "pending",
            (SemanticIndexOutbox.status == "retry_wait") & (SemanticIndexOutbox.next_retry_at <= now),
        )).order_by(SemanticIndexOutbox.id).limit(100).all()
        for item in due_outbox:
            item.status = "claimed"
            item.lease_owner, item.lease_expires_at = owner, now + timedelta(seconds=cls.OUTBOX_LEASE_SECONDS)
            db.commit()
            try:
                SemanticIndexService.apply_outbox(db, item)
                item.status = "completed"
                item.completed_at = now
                item.lease_owner, item.lease_expires_at = None, None
            except Exception as exc:
                item.attempt_count += 1
                item.last_error_code = getattr(exc, "code", "SEMANTIC_INDEX_FAILED")
                if item.attempt_count >= 3:
                    item.status = "dead_letter"
                else:
                    item.status = "retry_wait"
                    item.next_retry_at = now + timedelta(minutes=2 ** (item.attempt_count - 1))
                item.lease_owner, item.lease_expires_at = None, None
        db.commit()
        return completed
