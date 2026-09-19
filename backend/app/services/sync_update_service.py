"""Explicit, reviewable external overwrites for existing patents.

Subscription reconciliation is allowed to create records.  This service has
the opposite contract: it only works with caller-selected Patent rows and
never creates a Patent during preview or confirmation.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import BadRequestException
from app.integrations.contracts import ProviderIdentifier, ProviderPatentRecord
from app.integrations.registry import get_connector
from app.models import (
    ConnectorDefinition,
    ExternalFactObservation,
    ExternalSnapshot,
    Patent,
    PatentDatabaseMembership,
    SyncRecord,
    SyncRun,
    SyncUpdateBatch,
    SyncUpdateItem,
)
from app.services.patent_service import PatentService
from app.services.sync_reconciliation import apply_legal_events, resolve_patent
from app.services.sync_support import LEGAL_STATUS_MAP, SAFE_EXTERNAL_FIELDS, date_value, hash_payload, now, serialize_value


EXPLICIT_UPDATE_FIELDS = frozenset(SAFE_EXTERNAL_FIELDS) | {"legal_status"}
DEFAULT_UPDATE_FIELDS = tuple(sorted(EXPLICIT_UPDATE_FIELDS))
UPDATE_BATCH_TTL_MINUTES = 30


class SyncUpdateService:
    @staticmethod
    def _validate_fields(fields: list[str] | None) -> list[str]:
        requested = list(dict.fromkeys(fields or DEFAULT_UPDATE_FIELDS))
        invalid = sorted(set(requested) - EXPLICIT_UPDATE_FIELDS)
        if invalid:
            raise BadRequestException("外部更新不允许覆盖字段：" + ", ".join(invalid))
        return requested

    @staticmethod
    def _patent_in_database(db: Session, patent: Patent, database_id: int) -> bool:
        if patent.database_id == database_id:
            return True
        return bool(db.query(PatentDatabaseMembership).filter_by(
            patent_id=patent.id,
            database_id=database_id,
        ).first())

    @staticmethod
    def _identifiers(patent: Patent) -> list[ProviderIdentifier]:
        result = [
            ProviderIdentifier(
                identifier_type=item.identifier_type,
                raw_value=item.raw_value,
                jurisdiction_code=item.jurisdiction_code or patent.country,
                kind_code=item.kind_code,
                identifier_namespace=item.identifier_namespace,
            )
            for item in patent.identifiers
            if item.raw_value
        ]
        if result:
            return result
        for identifier_type, value in (
            ("publication", patent.publication_number),
            ("application", patent.application_number),
            ("grant", patent.grant_number),
        ):
            if value:
                result.append(ProviderIdentifier(identifier_type, str(value), patent.country))
        return result

    @staticmethod
    def _normalized_candidate(field_key: str, value: Any) -> Any:
        if field_key == "legal_status":
            mapped = LEGAL_STATUS_MAP.get(str(value).strip().lower(), "unknown")
            return None if mapped == "unknown" and str(value).strip().lower() not in {"unknown", ""} else mapped
        if field_key.endswith("_date"):
            parsed = date_value(value)
            return parsed.isoformat() if parsed else None
        return serialize_value(value)

    @staticmethod
    def _current_value(patent: Patent, field_key: str) -> str | None:
        value = getattr(patent, field_key, None)
        return serialize_value(value)

    @staticmethod
    def _record_candidates(record: ProviderPatentRecord, fields: list[str]) -> dict[str, Any]:
        candidates: dict[str, Any] = {}
        for field_key in fields:
            raw_value = record.fields.get(field_key)
            if field_key == "legal_status" and raw_value is None and record.legal_events:
                raw_value = max(record.legal_events, key=lambda item: item.event_date).status
            if raw_value is None:
                continue
            candidate = SyncUpdateService._normalized_candidate(field_key, raw_value)
            if candidate is not None:
                candidates[field_key] = candidate
        return candidates

    @staticmethod
    @staticmethod
    def _fetch_record(connector: Any, patent: Patent) -> ProviderPatentRecord:
        identifiers = SyncUpdateService._identifiers(patent)
        if not identifiers:
            raise ValueError("专利没有可用于外部检索的申请号、公开号或授权号")
        last_error: Exception | None = None
        for identifier in identifiers:
            try:
                return connector.fetch_patent(identifier)
            except Exception as exc:  # Providers differ in which identifier types they accept.
                last_error = exc
        raise last_error or LookupError("外部数据未找到")

    @staticmethod
    def _record_from_snapshot(payload: dict[str, Any]) -> ProviderPatentRecord:
        """Rebuild the provider-neutral record without importing a connector."""
        identifiers = tuple(
            ProviderIdentifier(
                identifier_type=str(item["identifier_type"]),
                raw_value=str(item["raw_value"]),
                jurisdiction_code=item.get("jurisdiction_code"),
                kind_code=item.get("kind_code"),
                identifier_namespace=item.get("identifier_namespace", "official"),
            )
            for item in payload.get("identifiers", [])
        )
        from app.integrations.contracts import ProviderLegalEvent
        events = tuple(
            ProviderLegalEvent(
                provider_event_id=str(item["provider_event_id"]),
                event_code=str(item["event_code"]),
                event_date=date.fromisoformat(str(item["event_date"])[:10]),
                status=str(item.get("status", "unknown")),
                jurisdiction_code=item.get("jurisdiction_code"),
                raw_description=item.get("raw_description"),
                payload=item.get("payload", {}),
            )
            for item in payload.get("legal_events", [])
        )
        source_updated_at = payload.get("source_updated_at")
        return ProviderPatentRecord(
            external_record_id=str(payload["external_record_id"]),
            identifiers=identifiers,
            fields=dict(payload.get("fields", {})),
            legal_events=events,
            source_updated_at=datetime.fromisoformat(source_updated_at) if source_updated_at else None,
            source_version=payload.get("source_version"),
            raw_payload=dict(payload.get("raw_payload") or payload),
        )

    @staticmethod
    def _batch_dict(batch: SyncUpdateBatch) -> dict[str, Any]:
        return {
            "id": batch.id,
            "connector_id": batch.connector_id,
            "database_id": batch.database_id,
            "sync_run_id": batch.sync_run_id,
            "status": batch.status,
            "requested_patent_ids": batch.requested_patent_ids or [],
            "selected_fields": batch.selected_fields or [],
            "expires_at": batch.expires_at.isoformat() if batch.expires_at else None,
            "confirmed_at": batch.confirmed_at.isoformat() if batch.confirmed_at else None,
            "confirmed_by": batch.confirmed_by,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "items": [SyncUpdateService._item_dict(item) for item in batch.items],
        }

    @staticmethod
    def _item_dict(item: SyncUpdateItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "batch_id": item.batch_id,
            "patent_id": item.patent_id,
            "external_record_id": item.external_record_id,
            "sync_record_id": item.sync_record_id,
            "external_snapshot_id": item.external_snapshot_id,
            "status": item.status,
            "current_fields": item.current_fields or {},
            "candidate_fields": item.candidate_fields or {},
            "changed_fields": item.changed_fields or [],
            "selected_fields": item.selected_fields or [],
            "error_code": item.error_code,
            "error_message": item.error_message,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    @classmethod
    def preview(
        cls,
        db: Session,
        connector: ConnectorDefinition,
        database_id: int,
        patent_ids: list[int],
        fields: list[str] | None = None,
    ) -> SyncUpdateBatch:
        selected_fields = cls._validate_fields(fields)
        requested_ids = list(dict.fromkeys(patent_ids))
        if not requested_ids:
            raise BadRequestException("至少选择一条专利")
        patents = {patent.id: patent for patent in db.query(Patent).filter(Patent.id.in_(requested_ids)).all()}
        run = SyncRun(
            connector_id=connector.id,
            database_id=database_id,
            trigger="explicit_update_preview",
            status="running",
            started_at=now(),
            counts_json={"pages": 1, "records": 0, "matched": 0, "ready": 0, "no_change": 0, "errors": 0, "observations": 0, "legal_events": 0},
        )
        db.add(run)
        db.flush()
        batch = SyncUpdateBatch(
            connector_id=connector.id,
            database_id=database_id,
            sync_run_id=run.id,
            status="preview",
            requested_patent_ids=requested_ids,
            selected_fields=selected_fields,
            expires_at=now() + timedelta(minutes=UPDATE_BATCH_TTL_MINUTES),
        )
        db.add(batch)
        db.flush()
        runtime_connector = None
        try:
            runtime_connector = get_connector(connector)
            for patent_id in requested_ids:
                patent = patents.get(patent_id)
                item = SyncUpdateItem(batch_id=batch.id, patent_id=patent_id, selected_fields=[])
                db.add(item)
                db.flush()
                run.counts_json["records"] += 1
                if patent is None:
                    item.status = "not_found"
                    item.error_code = "patent_not_found"
                    item.error_message = "本地专利不存在"
                    run.counts_json["errors"] += 1
                    continue
                if not cls._patent_in_database(db, patent, database_id):
                    item.status = "out_of_scope"
                    item.error_code = "patent_out_of_scope"
                    item.error_message = "专利不属于当前数据库"
                    run.counts_json["errors"] += 1
                    continue
                try:
                    record = cls._fetch_record(runtime_connector, patent)
                except Exception as exc:
                    item.status = "not_found"
                    item.error_code = getattr(exc, "error_code", "provider_not_found")
                    item.error_message = str(exc)
                    run.counts_json["errors"] += 1
                    continue
                item.external_record_id = record.external_record_id
                payload = record.as_payload()
                snapshot = ExternalSnapshot(
                    connector_id=connector.id,
                    sync_run_id=run.id,
                    request_metadata={"mode": "explicit_update_preview", "patent_id": patent.id},
                    payload_json=payload,
                    payload_hash=hash_payload(payload),
                    source_version=record.source_version,
                )
                db.add(snapshot)
                db.flush()
                sync_record = SyncRecord(
                    sync_run_id=run.id,
                    external_record_id=record.external_record_id,
                    external_snapshot_id=snapshot.id,
                    idempotency_key=hash_payload({"batch": batch.id, "patent": patent.id, "record": record.external_record_id}),
                )
                db.add(sync_record)
                db.flush()
                item.sync_record_id = sync_record.id
                item.external_snapshot_id = snapshot.id
                resolved, identity_status, candidate_ids = resolve_patent(db, record)
                if identity_status != "matched" or resolved is None or resolved.id != patent.id:
                    item.status = "identity_conflict" if candidate_ids or resolved else "not_matched"
                    item.error_code = item.status
                    item.error_message = "外部返回记录无法唯一确认属于当前专利"
                    sync_record.identity_status = "identity_conflict" if item.status == "identity_conflict" else "unmatched"
                    sync_record.identity_candidate_patent_ids = candidate_ids
                    sync_record.outcome = item.status
                    run.counts_json["errors"] += 1
                    continue
                sync_record.patent_id = patent.id
                sync_record.identity_status = "matched"
                sync_record.outcome = "update_preview"
                run.counts_json["matched"] += 1
                candidates = cls._record_candidates(record, selected_fields)
                current = {field_key: cls._current_value(patent, field_key) for field_key in candidates}
                changed = [field_key for field_key in candidates if current.get(field_key) != serialize_value(candidates[field_key])]
                item.current_fields = current
                item.candidate_fields = candidates
                item.changed_fields = changed
                item.selected_fields = changed.copy()
                item.status = "ready" if changed or record.legal_events else "no_change"
                run.counts_json[item.status] += 1
                for field_key, candidate in candidates.items():
                    observation = ExternalFactObservation(
                        sync_run_id=run.id,
                        external_snapshot_id=snapshot.id,
                        sync_record_id=sync_record.id,
                        patent_id=patent.id,
                        canonical_field_key=field_key,
                        raw_value=serialize_value(candidate),
                        normalized_value=serialize_value(candidate),
                        current_value=current.get(field_key),
                        candidate_value=serialize_value(candidate),
                        confidence="high",
                        decision="pending_update" if field_key in changed else "no_change",
                    )
                    db.add(observation)
                    run.counts_json["observations"] += 1
                run.counts_json["legal_events"] += len(record.legal_events)
            run.counts_json["errors"] = int(run.counts_json["errors"])
            run.status = "succeeded"
            run.finished_at = now()
            flag_modified(run, "counts_json")
            db.commit()
            db.refresh(batch)
            return batch
        except Exception:
            db.rollback()
            raise
        finally:
            if runtime_connector is not None:
                close = getattr(runtime_connector, "close", None)
                if callable(close):
                    close()

    @classmethod
    def confirm(cls, db: Session, batch: SyncUpdateBatch, selected_items: list[dict[str, Any]], confirmed_by: str) -> SyncUpdateBatch:
        if batch.status != "preview":
            raise BadRequestException("该更新预览已经确认、取消或失效")
        if batch.expires_at <= now():
            batch.status = "expired"
            db.commit()
            raise BadRequestException("更新预览已过期，请重新生成")
        choices = {int(item["item_id"]): list(dict.fromkeys(item.get("fields") or [])) for item in selected_items}
        items_by_id = {item.id: item for item in batch.items}
        if set(choices) - set(items_by_id):
            raise BadRequestException("确认列表包含不属于该批次的专利项")
        try:
            for item_id, fields in choices.items():
                item = items_by_id[item_id]
                if item.status not in {"ready", "no_change"}:
                    raise BadRequestException(f"专利项 {item_id} 当前不可覆盖：{item.status}")
                invalid = set(fields) - set(item.changed_fields or [])
                if invalid:
                    raise BadRequestException(f"专利项 {item_id} 包含未出现在预览中的字段")
                if not item.patent_id:
                    raise BadRequestException(f"专利项 {item_id} 没有关联本地专利")
                patent = db.get(Patent, item.patent_id)
                if not patent:
                    raise BadRequestException(f"专利 {item.patent_id} 已不存在")
                for field_key in fields:
                    before = cls._current_value(patent, field_key)
                    if before != (item.current_fields or {}).get(field_key):
                        raise BadRequestException(f"专利 {item.patent_id} 的字段 {field_key} 在预览后已发生变化，请重新预览")
                update_values = {}
                for field_key in fields:
                    candidate = (item.candidate_fields or {}).get(field_key)
                    if field_key != "legal_status":
                        update_values[field_key] = date_value(candidate) if field_key.endswith("_date") else candidate
                if update_values:
                    PatentService.update_patent(db, patent, update_values, source="external_sync_update", changed_by=confirmed_by, commit=False)
                # Legal events are retained as provider evidence whenever an
                # item is confirmed.  The current Patent projection changes
                # only when the user explicitly selects legal_status.
                record = item.snapshot.payload_json if item.snapshot else {}
                provider_record = cls._record_from_snapshot(record)
                apply_legal_events(
                    db,
                    batch.run,
                    item.snapshot,
                    patent,
                    provider_record,
                    batch.database_id,
                    None,
                    apply_current_status="legal_status" in fields,
                )
                observations = db.query(ExternalFactObservation).filter(
                    ExternalFactObservation.sync_record_id == item.sync_record_id,
                ).all()
                for observation in observations:
                    if observation.canonical_field_key in fields:
                        observation.decision = "accepted_update"
                        observation.decided_by = confirmed_by
                        observation.decided_at = now()
                    elif observation.decision == "pending_update":
                        observation.decision = "skipped_update"
                item.selected_fields = fields
                item.status = "updated" if fields else "skipped"
                if item.sync_record:
                    item.sync_record.outcome = item.status
            for item in batch.items:
                if item.id not in choices and item.status in {"ready", "no_change"}:
                    item.status = "skipped"
            batch.status = "confirmed"
            batch.confirmed_at = now()
            batch.confirmed_by = confirmed_by
            if batch.run:
                batch.run.status = "succeeded"
                batch.run.finished_at = now()
            db.commit()
            db.refresh(batch)
            return batch
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def cancel(db: Session, batch: SyncUpdateBatch) -> SyncUpdateBatch:
        if batch.status != "preview":
            raise BadRequestException("该更新预览已经结束")
        batch.status = "cancelled"
        db.commit()
        db.refresh(batch)
        return batch
