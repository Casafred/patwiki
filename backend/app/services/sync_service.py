"""Synchronization orchestration and public application service."""
from __future__ import annotations

from datetime import datetime, timedelta
import uuid
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.integrations.contracts import CanonicalPatentQuery, ConnectorError, ProviderIdentifier
from app.integrations.registry import get_connector
from app.models import (
    ConnectorDefinition,
    ExternalFactObservation,
    Patent,
    PatentHistory,
    SavedPatentQuery,
    SyncCursor,
    SyncLease,
    SyncRecord,
    SyncRun,
    SyncSubscription,
    WatchEvent,
)
from app.services.sync_reconciliation import process_record
from app.services.sync_support import date_value, hash_payload, now, serialize_value

_hash_payload = hash_payload


class SyncService:
    """Own the provider-independent run lifecycle and transaction boundaries."""

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        return bool(getattr(exc, "retryable", False)) or isinstance(exc, (TimeoutError, ConnectionError))

    @staticmethod
    def _close_connector(connector: Any) -> None:
        close = getattr(connector, "close", None)
        if callable(close):
            close()

    @staticmethod
    def connector_dict(connector: ConnectorDefinition) -> dict[str, Any]:
        return {
            "id": connector.id,
            "code": connector.code,
            "name": connector.name,
            "transport": connector.transport,
            "provider_type": connector.provider_type,
            "endpoint": connector.endpoint,
            "capabilities": connector.capabilities_json or {},
            "mcp_catalog": connector.mcp_catalog_json or {},
            "mcp_catalog_updated_at": connector.mcp_catalog_updated_at.isoformat() if connector.mcp_catalog_updated_at else None,
            "enabled": connector.enabled,
            "created_at": connector.created_at.isoformat() if connector.created_at else None,
            "updated_at": connector.updated_at.isoformat() if connector.updated_at else None,
        }

    @staticmethod
    def query_dict(query: SavedPatentQuery) -> dict[str, Any]:
        return {
            "id": query.id,
            "database_id": query.database_id,
            "name": query.name,
            "query": query.query_json or {},
            "query_version": query.query_version,
            "query_hash": query.query_hash,
            "enabled": query.enabled,
            "created_at": query.created_at.isoformat() if query.created_at else None,
            "updated_at": query.updated_at.isoformat() if query.updated_at else None,
        }

    @staticmethod
    def subscription_dict(subscription: SyncSubscription) -> dict[str, Any]:
        return {
            "id": subscription.id,
            "database_id": subscription.database_id,
            "connector_id": subscription.connector_id,
            "saved_query_id": subscription.saved_query_id,
            "name": subscription.name,
            "mode": subscription.mode,
            "scope": subscription.scope_json or {},
            "schedule": subscription.schedule_json or {},
            "review_policy": subscription.review_policy,
            "enabled": subscription.enabled,
            "next_run_at": subscription.next_run_at.isoformat() if subscription.next_run_at else None,
            "last_run_at": subscription.last_run_at.isoformat() if subscription.last_run_at else None,
            "last_status": subscription.last_status,
        }

    @staticmethod
    def run_dict(run: SyncRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "subscription_id": run.subscription_id,
            "connector_id": run.connector_id,
            "database_id": run.database_id,
            "trigger": run.trigger,
            "status": run.status,
            "cursor_before": run.cursor_before,
            "cursor_after": run.cursor_after,
            "counts": run.counts_json or {},
            "error_code": run.error_code,
            "error_message": run.error_message,
            "retry_count": run.retry_count,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }

    @staticmethod
    def record_dict(record: SyncRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "sync_run_id": record.sync_run_id,
            "external_record_id": record.external_record_id,
            "record_kind": record.record_kind,
            "patent_id": record.patent_id,
            "external_snapshot_id": record.external_snapshot_id,
            "identity_status": record.identity_status,
            "identity_candidate_patent_ids": record.identity_candidate_patent_ids or [],
            "outcome": record.outcome,
            "idempotency_key": record.idempotency_key,
            "error_code": record.error_code,
            "error_message": record.error_message,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    @staticmethod
    def observation_dict(observation: ExternalFactObservation) -> dict[str, Any]:
        return {
            "id": observation.id,
            "sync_run_id": observation.sync_run_id,
            "sync_record_id": observation.sync_record_id,
            "patent_id": observation.patent_id,
            "canonical_field_key": observation.canonical_field_key,
            "raw_value": observation.raw_value,
            "normalized_value": observation.normalized_value,
            "current_value": observation.current_value,
            "candidate_value": observation.candidate_value,
            "confidence": observation.confidence,
            "decision": observation.decision,
            "decision_reason": observation.decision_reason,
            "decided_by": observation.decided_by,
            "decided_at": observation.decided_at.isoformat() if observation.decided_at else None,
            "created_at": observation.created_at.isoformat() if observation.created_at else None,
        }

    @staticmethod
    def watch_event_dict(event: WatchEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "database_id": event.database_id,
            "patent_id": event.patent_id,
            "sync_subscription_id": event.sync_subscription_id,
            "event_type": event.event_type,
            "severity": event.severity,
            "dedupe_key": event.dedupe_key,
            "payload": event.payload_json or {},
            "status": event.status,
            "acknowledged_by": event.acknowledged_by,
            "acknowledged_at": event.acknowledged_at.isoformat() if event.acknowledged_at else None,
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        }

    @staticmethod
    def create_or_update_connector(db: Session, values: dict[str, Any], connector: ConnectorDefinition | None = None) -> ConnectorDefinition:
        connector = connector or ConnectorDefinition(code=values["code"])
        for key, value in values.items():
            if key != "code" and value is not None:
                setattr(connector, key, value)
        db.add(connector)
        db.commit()
        db.refresh(connector)
        return connector

    @staticmethod
    def create_query(db: Session, values: dict[str, Any]) -> SavedPatentQuery:
        payload = values.get("query_json") or {}
        query = SavedPatentQuery(
            database_id=values["database_id"],
            name=values["name"],
            query_json=payload,
            query_hash=hash_payload(payload),
            enabled=values.get("enabled", True),
        )
        db.add(query)
        db.commit()
        db.refresh(query)
        return query

    @staticmethod
    def create_subscription(db: Session, values: dict[str, Any]) -> SyncSubscription:
        subscription = SyncSubscription(**values)
        db.add(subscription)
        db.flush()
        db.add(SyncCursor(subscription_id=subscription.id, overlap_seconds=86400))
        db.commit()
        db.refresh(subscription)
        return subscription

    @staticmethod
    def _acquire_lease(db: Session, subscription_id: int, owner_id: str, current: datetime) -> bool:
        lease = db.query(SyncLease).filter(SyncLease.subscription_id == subscription_id).first()
        expiry = current + timedelta(minutes=15)
        if lease and lease.expires_at > current and lease.owner_id != owner_id:
            return False
        if not lease:
            db.add(SyncLease(subscription_id=subscription_id, owner_id=owner_id, expires_at=expiry))
        else:
            lease.owner_id = owner_id
            lease.expires_at = expiry
        db.flush()
        return True

    @staticmethod
    def _release_lease(db: Session, subscription_id: int, owner_id: str) -> None:
        lease = db.query(SyncLease).filter(
            SyncLease.subscription_id == subscription_id,
            SyncLease.owner_id == owner_id,
        ).first()
        if lease:
            db.delete(lease)

    @classmethod
    def run_subscription(cls, db: Session, subscription: SyncSubscription, *, trigger: str = "manual", max_pages: int = 100, owner_id: str | None = None) -> SyncRun:
        owner_id = owner_id or f"local-{uuid.uuid4().hex[:12]}"
        started_at = now()
        if not cls._acquire_lease(db, subscription.id, owner_id, started_at):
            raise ValueError("该同步订阅正在运行")
        cursor = subscription.cursor or SyncCursor(subscription_id=subscription.id, overlap_seconds=86400)
        if not cursor.id:
            db.add(cursor)
            db.flush()
        run = SyncRun(
            subscription_id=subscription.id,
            connector_id=subscription.connector_id,
            database_id=subscription.database_id,
            trigger=trigger,
            status="running",
            cursor_before=cursor.cursor,
            started_at=started_at,
            counts_json={"pages": 0, "records": 0, "created": 0, "matched": 0, "observations": 0, "auto_applied": 0, "review": 0, "legal_events": 0, "duplicates": 0, "errors": 0},
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        try:
            connector = get_connector(subscription.connector)
            payload = subscription.saved_query.query_json if subscription.saved_query else subscription.scope_json
            query = CanonicalPatentQuery.from_dict(payload)
            next_cursor = cursor.cursor
            for _ in range(max_pages):
                page = connector.search(query, next_cursor, limit=100)
                run.counts_json["pages"] += 1
                if not page.records:
                    next_cursor = page.next_cursor
                    break
                for record in page.records:
                    process_record(db, run, subscription, record)
                next_cursor = page.next_cursor
                cursor.cursor = next_cursor
                cursor.watermark = page.watermark
                cursor.provider_snapshot_version = page.source_version
                run.cursor_after = next_cursor
                flag_modified(run, "counts_json")
                db.flush()
                db.commit()
                db.refresh(run)
                if not next_cursor:
                    break
            flag_modified(run, "counts_json")
            run.status = "succeeded"
            run.finished_at = now()
            subscription.last_run_at = run.finished_at
            subscription.last_status = run.status
            interval = (subscription.schedule_json or {}).get("interval_minutes")
            subscription.next_run_at = run.finished_at + timedelta(minutes=int(interval)) if interval else None
            cls._release_lease(db, subscription.id, owner_id)
            db.commit()
            db.refresh(run)
            cls._close_connector(connector)
            return run
        except Exception as exc:
            if "connector" in locals():
                cls._close_connector(connector)
            db.rollback()
            run = db.query(SyncRun).filter(SyncRun.id == run.id).one()
            run.status = "failed_retryable" if cls._is_retryable(exc) else "failed_permanent"
            run.error_code = getattr(exc, "error_code", type(exc).__name__)
            run.error_message = str(exc)
            run.finished_at = now()
            subscription.last_run_at = run.finished_at
            subscription.last_status = run.status
            cls._release_lease(db, subscription.id, owner_id)
            db.add(run)
            db.commit()
            raise

    @classmethod
    def run_due_subscriptions(cls, db: Session, *, owner_id: str = "local-scheduler", limit: int = 10) -> list[dict[str, Any]]:
        current = now()
        subscriptions = db.query(SyncSubscription).filter(
            SyncSubscription.enabled == True,
            SyncSubscription.next_run_at.isnot(None),
            SyncSubscription.next_run_at <= current,
        ).order_by(SyncSubscription.next_run_at, SyncSubscription.id).limit(limit).all()
        results = []
        for subscription in subscriptions:
            try:
                results.append(cls.run_dict(cls.run_subscription(db, subscription, trigger="schedule", owner_id=owner_id)))
            except Exception as exc:
                results.append({"subscription_id": subscription.id, "status": "failed", "error": str(exc)})
        return results

    @classmethod
    def refresh_patent(cls, db: Session, connector: ConnectorDefinition, identifier: ProviderIdentifier, database_id: int, review_policy: str = "safe_auto_apply") -> SyncRun:
        run = SyncRun(
            connector_id=connector.id,
            database_id=database_id,
            trigger="manual",
            status="running",
            started_at=now(),
            counts_json={"pages": 1, "records": 0, "created": 0, "matched": 0, "observations": 0, "auto_applied": 0, "review": 0, "legal_events": 0, "duplicates": 0, "errors": 0},
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        try:
            runtime_connector = get_connector(connector)
            record = runtime_connector.fetch_patent(identifier)
            transient = SyncSubscription(database_id=database_id, connector_id=connector.id, name="manual-refresh", review_policy=review_policy)
            process_record(db, run, transient, record)
            flag_modified(run, "counts_json")
            run.status = "succeeded"
            run.finished_at = now()
            db.commit()
            db.refresh(run)
            cls._close_connector(runtime_connector)
            return run
        except Exception as exc:
            if "runtime_connector" in locals():
                cls._close_connector(runtime_connector)
            db.rollback()
            run = db.query(SyncRun).filter(SyncRun.id == run.id).one()
            run.status = "failed_retryable" if cls._is_retryable(exc) else "failed_permanent"
            run.error_code = getattr(exc, "error_code", type(exc).__name__)
            run.error_message = str(exc)
            run.finished_at = now()
            db.add(run)
            db.commit()
            raise

    @staticmethod
    def decide_observation(db: Session, observation: ExternalFactObservation, decision: str, decided_by: str, reason: str | None = None) -> ExternalFactObservation:
        from app.services.sync_support import SAFE_EXTERNAL_FIELDS
        if decision not in {"accepted", "rejected"}:
            raise ValueError("decision must be accepted or rejected")
        if decision == "accepted":
            if not observation.patent_id:
                raise ValueError("没有关联专利的观察不能直接接受")
            patent = db.query(Patent).filter(Patent.id == observation.patent_id).one()
            if observation.canonical_field_key not in SAFE_EXTERNAL_FIELDS:
                raise ValueError("该字段不允许外部同步直接写入")
            before = serialize_value(getattr(patent, observation.canonical_field_key, None))
            value = date_value(observation.candidate_value) if observation.canonical_field_key.endswith("_date") else observation.candidate_value
            setattr(patent, observation.canonical_field_key, value)
            db.add(PatentHistory(
                patent_id=patent.id,
                field_key=observation.canonical_field_key,
                old_value=before,
                new_value=observation.candidate_value,
                source="external_sync_review",
                changed_by=decided_by,
            ))
            observation.current_value = before
        observation.decision = decision
        observation.decision_reason = reason
        observation.decided_by = decided_by
        observation.decided_at = now()
        db.commit()
        db.refresh(observation)
        return observation
