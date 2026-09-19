"""Provider record reconciliation and legal-event application."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.contracts import ProviderPatentRecord
from app.models import (
    ExternalFactObservation,
    ExternalSnapshot,
    LegalStatus,
    LegalStatusEvent,
    Patent,
    PatentDatabaseMembership,
    PatentHistory,
    SyncRecord,
    SyncRun,
    SyncSubscription,
    WatchEvent,
)
from app.services.patent_identity_service import (
    ensure_patent_identifiers,
    find_patents_by_identifier_specs_bulk,
    find_patents_by_identifiers,
    parse_identifier,
)
from app.services.sync_support import (
    LEGAL_STATUS_MAP,
    SAFE_EXTERNAL_FIELDS,
    date_value,
    hash_payload,
    now,
    serialize_value,
)


def resolve_patent(db: Session, record: ProviderPatentRecord) -> tuple[Patent | None, str, list[int]]:
    specs = [
        spec
        for identifier in record.identifiers
        if (spec := parse_identifier(
            identifier.raw_value,
            identifier.identifier_type,
            identifier.jurisdiction_code,
            identifier_namespace=identifier.identifier_namespace,
        ))
    ]
    matches = find_patents_by_identifiers(db, specs)
    if not matches and specs:
        matches = find_patents_by_identifier_specs_bulk(db, {0: specs}).get(0, [])
    candidate_ids = sorted({patent.id for patent in matches})
    if len(candidate_ids) > 1:
        return None, "identity_conflict", candidate_ids
    if matches:
        return matches[0], "matched", candidate_ids
    return None, "new_candidate", []


def create_patent(db: Session, record: ProviderPatentRecord, database_id: int) -> Patent:
    fields = dict(record.fields)
    patent = Patent(title="待补全", database_id=database_id, country=fields.get("country") or "CN")
    db.add(patent)
    db.flush()
    specs = [
        spec
        for identifier in record.identifiers
        if (spec := parse_identifier(
            identifier.raw_value,
            identifier.identifier_type,
            identifier.jurisdiction_code,
            identifier_namespace=identifier.identifier_namespace,
        ))
    ]
    ensure_patent_identifiers(db, patent, additional_specs=specs, source_system="external")
    if not db.query(PatentDatabaseMembership).filter_by(patent_id=patent.id, database_id=database_id).first():
        db.add(PatentDatabaseMembership(patent_id=patent.id, database_id=database_id))
    return patent


def record_observation(
    db: Session,
    run: SyncRun,
    snapshot: ExternalSnapshot,
    sync_record: SyncRecord,
    patent: Patent | None,
    field_key: str,
    candidate: Any,
    review_policy: str,
) -> ExternalFactObservation:
    current = getattr(patent, field_key, None) if patent else None
    current_serialized = serialize_value(current)
    candidate_serialized = serialize_value(candidate)
    changed = current_serialized != candidate_serialized
    auto_apply = bool(patent and changed and field_key in SAFE_EXTERNAL_FIELDS and review_policy == "safe_auto_apply")
    observation = ExternalFactObservation(
        sync_run_id=run.id,
        external_snapshot_id=snapshot.id,
        sync_record_id=sync_record.id,
        patent_id=patent.id if patent else None,
        canonical_field_key=field_key,
        raw_value=candidate_serialized,
        normalized_value=candidate_serialized,
        current_value=current_serialized,
        candidate_value=candidate_serialized,
        confidence="high" if patent else "medium",
        decision="auto_applied" if auto_apply else ("no_change" if not changed else "pending_review"),
        decision_reason="safe external fact" if auto_apply else None,
        decided_by="sync-engine" if auto_apply else None,
        decided_at=now() if auto_apply else None,
    )
    db.add(observation)
    db.flush()
    if auto_apply:
        setattr(patent, field_key, date_value(candidate) if field_key.endswith("_date") else candidate)
        db.add(PatentHistory(
            patent_id=patent.id,
            field_key=field_key,
            old_value=current_serialized,
            new_value=candidate_serialized,
            source="external_sync",
            changed_by="sync-engine",
        ))
    return observation


def apply_legal_events(
    db: Session,
    run: SyncRun,
    snapshot: ExternalSnapshot,
    patent: Patent,
    record: ProviderPatentRecord,
    database_id: int,
    subscription_id: int | None,
) -> int:
    applied = 0
    for event in record.legal_events:
        event_hash = hash_payload({"id": event.provider_event_id, "status": event.status, "date": event.event_date.isoformat()})
        existing = db.query(LegalStatusEvent).filter(
            LegalStatusEvent.connector_id == run.connector_id,
            LegalStatusEvent.provider_event_id == event.provider_event_id,
        ).first()
        if existing:
            continue
        db.add(LegalStatusEvent(
            patent_id=patent.id,
            connector_id=run.connector_id,
            external_snapshot_id=snapshot.id,
            provider_event_id=event.provider_event_id,
            jurisdiction_code=event.jurisdiction_code,
            event_code=event.event_code,
            event_date=datetime.combine(event.event_date, datetime.min.time()),
            status=LEGAL_STATUS_MAP.get(event.status, "unknown"),
            raw_description=event.raw_description,
            payload_hash=event_hash,
        ))
        db.flush()
        dedupe_key = hash_payload({"patent": patent.id, "type": "legal_status_changed", "event": event.provider_event_id})
        if not db.query(WatchEvent).filter(WatchEvent.dedupe_key == dedupe_key).first():
            db.add(WatchEvent(
                database_id=database_id,
                patent_id=patent.id,
                sync_subscription_id=subscription_id,
                event_type="legal_status_changed",
                severity="important",
                dedupe_key=dedupe_key,
                payload_json={"event_code": event.event_code, "status": event.status, "event_date": event.event_date.isoformat()},
            ))
        applied += 1
    if record.legal_events:
        latest = max(record.legal_events, key=lambda item: item.event_date)
        mapped_status = LEGAL_STATUS_MAP.get(latest.status, "unknown")
        current_status = patent.legal_status.value if hasattr(patent.legal_status, "value") else patent.legal_status
        if current_status != mapped_status:
            db.add(PatentHistory(
                patent_id=patent.id,
                field_key="legal_status",
                old_value=current_status,
                new_value=mapped_status,
                source="external_sync",
                changed_by="sync-engine",
            ))
            patent.legal_status = LegalStatus(mapped_status)
            patent.legal_status_date = latest.event_date
    return applied


def process_record(db: Session, run: SyncRun, subscription: SyncSubscription, record: ProviderPatentRecord) -> None:
    payload = record.as_payload()
    payload_hash = hash_payload(payload)
    snapshot = ExternalSnapshot(
        connector_id=run.connector_id,
        sync_run_id=run.id,
        request_metadata={"external_record_id": record.external_record_id},
        payload_json=payload,
        payload_hash=payload_hash,
        source_version=record.source_version,
    )
    db.add(snapshot)
    db.flush()
    idempotency_key = hash_payload({"connector": run.connector_id, "subscription": subscription.id, "record": record.external_record_id, "payload": payload_hash})
    existing = db.query(SyncRecord).filter(SyncRecord.idempotency_key == idempotency_key).first()
    if existing:
        run.counts_json["duplicates"] += 1
        return
    patent, identity_status, candidate_ids = resolve_patent(db, record)
    sync_record = SyncRecord(
        sync_run_id=run.id,
        external_record_id=record.external_record_id,
        external_snapshot_id=snapshot.id,
        patent_id=patent.id if patent else None,
        identity_status=identity_status,
        identity_candidate_patent_ids=candidate_ids,
        outcome="pending",
        idempotency_key=idempotency_key,
    )
    db.add(sync_record)
    db.flush()
    run.counts_json["records"] += 1
    if identity_status == "identity_conflict":
        sync_record.outcome = "identity_conflict"
        run.counts_json["errors"] += 1
        return
    if patent is None:
        patent = create_patent(db, record, subscription.database_id)
        sync_record.patent_id = patent.id
        sync_record.identity_status = "created"
        run.counts_json["created"] += 1
    else:
        run.counts_json["matched"] += 1
        if not db.query(PatentDatabaseMembership).filter_by(patent_id=patent.id, database_id=subscription.database_id).first():
            db.add(PatentDatabaseMembership(patent_id=patent.id, database_id=subscription.database_id))
        ensure_patent_identifiers(db, patent, source_system="external")
    for field_key, value in record.fields.items():
        if field_key not in SAFE_EXTERNAL_FIELDS or value is None:
            continue
        observation = record_observation(db, run, snapshot, sync_record, patent, field_key, value, subscription.review_policy)
        run.counts_json["observations"] += 1
        if observation.decision == "auto_applied":
            run.counts_json["auto_applied"] += 1
        elif observation.decision == "pending_review":
            run.counts_json["review"] += 1
    run.counts_json["legal_events"] += apply_legal_events(db, run, snapshot, patent, record, subscription.database_id, subscription.id)
    sync_record.outcome = "processed"
