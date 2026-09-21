"""External patent connector, subscription and synchronization APIs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException, NotFoundException
from app.database import get_db
from app.integrations.contracts import ProviderIdentifier
from app.integrations.credentials import CredentialStoreError, validate_credential_ref
from app.models import (
    ConnectorCredential,
    ConnectorDefinition,
    ExternalFactObservation,
    LegalStatusEvent,
    PatentDatabase,
    SavedPatentQuery,
    SyncRun,
    SyncSubscription,
    SyncUpdateBatch,
    WatchEvent,
)
from app.schemas.sync import (
    ConnectorCreate,
    ConnectorUpdate,
    CredentialCreate,
    ObservationDecisionRequest,
    PatentRefreshRequest,
    RunRequest,
    SavedQueryCreate,
    SavedQueryUpdate,
    SubscriptionCreate,
    SubscriptionUpdate,
    WatchEventUpdate,
    SyncUpdatePreviewRequest,
    SyncUpdateConfirmRequest,
)
from app.services.sync_service import SyncService
from app.services.sync_update_service import SyncUpdateService
from app.integrations.registry import get_connector


router = APIRouter(prefix="/sync", tags=["external-sync"])


def _require_database(db: Session, database_id: int) -> PatentDatabase:
    database = db.query(PatentDatabase).filter(PatentDatabase.id == database_id).first()
    if not database:
        raise NotFoundException("数据库不存在")
    return database


def _require_connector(db: Session, connector_id: int) -> ConnectorDefinition:
    connector = db.query(ConnectorDefinition).filter(ConnectorDefinition.id == connector_id).first()
    if not connector:
        raise NotFoundException("连接器不存在")
    return connector


@router.post("/updates/preview")
def preview_explicit_update(body: SyncUpdatePreviewRequest, db: Session = Depends(get_db)):
    _require_database(db, body.database_id)
    connector = _require_connector(db, body.connector_id)
    if not connector.enabled:
        raise BadRequestException("连接器已停用")
    try:
        batch = SyncUpdateService.preview(db, connector, body.database_id, body.patent_ids, body.fields)
    except BadRequestException:
        raise
    except Exception as exc:
        raise BadRequestException(f"生成外部更新预览失败：{exc}") from exc
    return SyncUpdateService._batch_dict(batch)


@router.get("/updates/{batch_id}")
def get_explicit_update(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(SyncUpdateBatch, batch_id)
    if not batch:
        raise NotFoundException("外部更新批次不存在")
    return SyncUpdateService._batch_dict(batch)


@router.post("/updates/{batch_id}/confirm")
def confirm_explicit_update(batch_id: int, body: SyncUpdateConfirmRequest, db: Session = Depends(get_db)):
    from app.models import SyncUpdateBatch
    batch = db.get(SyncUpdateBatch, batch_id)
    if not batch:
        raise NotFoundException("外部更新批次不存在")
    try:
        result = SyncUpdateService.confirm(db, batch, [item.model_dump() for item in body.selected_items], body.confirmed_by)
    except BadRequestException:
        raise
    except Exception as exc:
        raise BadRequestException(f"确认外部更新失败：{exc}") from exc
    return SyncUpdateService._batch_dict(result)


@router.post("/updates/{batch_id}/cancel")
def cancel_explicit_update(batch_id: int, db: Session = Depends(get_db)):
    from app.models import SyncUpdateBatch
    batch = db.get(SyncUpdateBatch, batch_id)
    if not batch:
        raise NotFoundException("外部更新批次不存在")
    return SyncUpdateService._batch_dict(SyncUpdateService.cancel(db, batch))


def _validate_connector_config(values: dict) -> None:
    config = values.get("config_json") or {}
    auth = config.get("auth") or {}
    reference = auth.get("credential_ref") or config.get("credential_ref")
    if reference:
        try:
            validate_credential_ref(str(reference))
        except CredentialStoreError as exc:
            raise BadRequestException(str(exc)) from exc
    # credential_value is accepted for the local desktop setup flow. It is
    # never included in connector/list responses; references remain preferred
    # for deployments that have an OS keyring or environment secret store.
    sensitive_keys = {"authorization", "api_key", "apikey", "access_token", "refresh_token", "password", "cookie", "secret", "token", "client_secret"}

    def contains_inline_secret(value: object, parent_key: str = "") -> bool:
        key = parent_key.casefold().replace("-", "_")
        if key in sensitive_keys and key != "credential_ref":
            return True
        if isinstance(value, dict):
            return any(contains_inline_secret(item, str(name)) for name, item in value.items())
        if isinstance(value, list):
            return any(contains_inline_secret(item, parent_key) for item in value)
        return False

    if contains_inline_secret(config):
        raise BadRequestException("连接器配置禁止保存明文凭证，请使用 env:// 或 keyring:// 引用")
    if values.get("transport") == "mcp" and not values.get("provider_type"):
        raise BadRequestException("MCP 连接器必须指定 provider_type")


@router.get("/connectors")
def list_connectors(db: Session = Depends(get_db)):
    return {"items": [SyncService.connector_dict(item) for item in db.query(ConnectorDefinition).order_by(ConnectorDefinition.id).all()]}


@router.post("/connectors")
def create_connector(body: ConnectorCreate, db: Session = Depends(get_db)):
    if db.query(ConnectorDefinition).filter(ConnectorDefinition.code == body.code).first():
        raise BadRequestException("连接器 code 已存在")
    values = body.model_dump()
    _validate_connector_config(values)
    connector = SyncService.create_or_update_connector(db, values)
    return SyncService.connector_dict(connector)


@router.patch("/connectors/{connector_id}")
def update_connector(connector_id: int, body: ConnectorUpdate, db: Session = Depends(get_db)):
    connector = _require_connector(db, connector_id)
    values = body.model_dump(exclude_unset=True)
    _validate_connector_config(values)
    connector = SyncService.create_or_update_connector(db, values, connector)
    return SyncService.connector_dict(connector)


@router.post("/connectors/{connector_id}/test")
def test_connector(connector_id: int, db: Session = Depends(get_db)):
    connector = _require_connector(db, connector_id)
    runtime_connector = None
    try:
        runtime_connector = get_connector(connector)
        health = runtime_connector.healthcheck()
    except Exception as exc:
        raise BadRequestException(f"连接器健康检查失败：{exc}") from exc
    finally:
        if runtime_connector is not None:
            close = getattr(runtime_connector, "close", None)
            if callable(close):
                close()
    return {"status": health.status, "message": health.message, "latency_ms": health.latency_ms}


@router.post("/connectors/{connector_id}/discover")
def discover_connector_tools(connector_id: int, db: Session = Depends(get_db)):
    """Explicitly discover MCP tools; this may make a billable provider call."""
    connector = _require_connector(db, connector_id)
    runtime_connector = None
    try:
        runtime_connector = get_connector(connector)
        discover = getattr(runtime_connector, "discover_tools", None)
        if not callable(discover):
            raise BadRequestException("该连接器不支持 MCP 工具发现")
        catalog = discover()
        connector.mcp_catalog_json = catalog
        from app.core.time import utc_now_naive
        connector.mcp_catalog_updated_at = utc_now_naive()
        db.commit()
        db.refresh(connector)
        return {
            **catalog,
            "connector_id": connector.id,
            "updated_at": connector.mcp_catalog_updated_at.isoformat() if connector.mcp_catalog_updated_at else None,
        }
    except BadRequestException:
        raise
    except Exception as exc:
        raise BadRequestException(f"MCP 工具发现失败：{exc}") from exc
    finally:
        if runtime_connector is not None:
            close = getattr(runtime_connector, "close", None)
            if callable(close):
                close()


@router.get("/connectors/{connector_id}/credentials")
def list_connector_credentials(connector_id: int, db: Session = Depends(get_db)):
    connector = _require_connector(db, connector_id)
    return {"items": [
        {
            "id": item.id,
            "connector_id": connector.id,
            "credential_type": item.credential_type,
            "label": item.label,
            "configured": True,
            "credential_ref": item.credential_ref,
        }
        for item in connector.credentials
    ]}


@router.post("/connectors/{connector_id}/credentials")
def add_connector_credential(connector_id: int, body: CredentialCreate, db: Session = Depends(get_db)):
    _require_connector(db, connector_id)
    try:
        validate_credential_ref(body.credential_ref)
    except CredentialStoreError as exc:
        raise BadRequestException(str(exc)) from exc
    credential = ConnectorCredential(connector_id=connector_id, **body.model_dump())
    db.add(credential)
    db.commit()
    return {
        "id": credential.id,
        "connector_id": connector_id,
        "credential_type": credential.credential_type,
        "label": credential.label,
        "configured": True,
    }


@router.get("/queries")
def list_queries(database_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(SavedPatentQuery)
    if database_id is not None:
        query = query.filter(SavedPatentQuery.database_id == database_id)
    return {"items": [SyncService.query_dict(item) for item in query.order_by(SavedPatentQuery.id.desc()).all()]}


@router.post("/queries")
def create_query(body: SavedQueryCreate, db: Session = Depends(get_db)):
    _require_database(db, body.database_id)
    return SyncService.query_dict(SyncService.create_query(db, body.model_dump()))


@router.patch("/queries/{query_id}")
def update_query(query_id: int, body: SavedQueryUpdate, db: Session = Depends(get_db)):
    query = db.query(SavedPatentQuery).filter(SavedPatentQuery.id == query_id).first()
    if not query:
        raise NotFoundException("保存的检索式不存在")
    values = body.model_dump(exclude_unset=True)
    if "query_json" in values:
        query.query_json = values["query_json"] or {}
        query.query_version += 1
        from app.services.sync_service import _hash_payload
        query.query_hash = _hash_payload(query.query_json)
    for key, value in values.items():
        if key != "query_json":
            setattr(query, key, value)
    db.commit()
    db.refresh(query)
    return SyncService.query_dict(query)


@router.get("/subscriptions")
def list_subscriptions(database_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(SyncSubscription)
    if database_id is not None:
        query = query.filter(SyncSubscription.database_id == database_id)
    return {"items": [SyncService.subscription_dict(item) for item in query.order_by(SyncSubscription.id.desc()).all()]}


@router.post("/subscriptions")
def create_subscription(body: SubscriptionCreate, db: Session = Depends(get_db)):
    _require_database(db, body.database_id)
    _require_connector(db, body.connector_id)
    if body.saved_query_id is not None:
        query = db.query(SavedPatentQuery).filter(SavedPatentQuery.id == body.saved_query_id).first()
        if not query or query.database_id != body.database_id:
            raise BadRequestException("检索式不存在或不属于目标数据库")
    values = body.model_dump()
    if body.enabled and not body.schedule_json:
        values["schedule_json"] = {"interval_minutes": 1440}
    if values.get("enabled"):
        from app.core.time import utc_now_naive
        values["next_run_at"] = utc_now_naive()
    return SyncService.subscription_dict(SyncService.create_subscription(db, values))


@router.patch("/subscriptions/{subscription_id}")
def update_subscription(subscription_id: int, body: SubscriptionUpdate, db: Session = Depends(get_db)):
    subscription = db.query(SyncSubscription).filter(SyncSubscription.id == subscription_id).first()
    if not subscription:
        raise NotFoundException("同步订阅不存在")
    values = body.model_dump(exclude_unset=True)
    if "saved_query_id" in values and values["saved_query_id"] is not None:
        query = db.query(SavedPatentQuery).filter(SavedPatentQuery.id == values["saved_query_id"]).first()
        if not query or query.database_id != subscription.database_id:
            raise BadRequestException("检索式不存在或不属于目标数据库")
    for key, value in values.items():
        setattr(subscription, key, value)
    if values.get("enabled") is True and subscription.next_run_at is None:
        from app.core.time import utc_now_naive
        subscription.next_run_at = utc_now_naive()
    db.commit()
    db.refresh(subscription)
    return SyncService.subscription_dict(subscription)


@router.post("/subscriptions/{subscription_id}/run")
def run_subscription(subscription_id: int, body: RunRequest, db: Session = Depends(get_db)):
    subscription = db.query(SyncSubscription).filter(SyncSubscription.id == subscription_id).first()
    if not subscription:
        raise NotFoundException("同步订阅不存在")
    if not subscription.enabled:
        raise BadRequestException("同步订阅已停用")
    try:
        run = SyncService.run_subscription(db, subscription, trigger=body.trigger, max_pages=body.max_pages)
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    except Exception as exc:
        raise BadRequestException(f"同步执行失败：{exc}") from exc
    return SyncService.run_dict(run)


@router.post("/patents/refresh")
def refresh_patent(body: PatentRefreshRequest, db: Session = Depends(get_db)):
    connector = _require_connector(db, body.connector_id)
    if body.database_id is None:
        database = db.query(PatentDatabase).filter(PatentDatabase.is_default == True).first()
        if not database:
            raise NotFoundException("未找到默认数据库")
        database_id = database.id
    else:
        _require_database(db, body.database_id)
        database_id = body.database_id
    identifier = ProviderIdentifier(identifier_type=body.identifier_type, raw_value=body.identifier)
    try:
        run = SyncService.refresh_patent(db, connector, identifier, database_id, body.review_policy)
    except Exception as exc:
        raise BadRequestException(f"专利刷新失败：{exc}") from exc
    return SyncService.run_dict(run)


@router.get("/runs")
def list_runs(subscription_id: int | None = None, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    query = db.query(SyncRun)
    if subscription_id is not None:
        query = query.filter(SyncRun.subscription_id == subscription_id)
    return {"items": [SyncService.run_dict(item) for item in query.order_by(SyncRun.id.desc()).limit(limit).all()]}


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(SyncRun).filter(SyncRun.id == run_id).first()
    if not run:
        raise NotFoundException("同步运行不存在")
    return SyncService.run_dict(run)


@router.get("/runs/{run_id}/records")
def list_run_records(run_id: int, limit: int = Query(500, ge=1, le=2000), db: Session = Depends(get_db)):
    run = db.query(SyncRun).filter(SyncRun.id == run_id).first()
    if not run:
        raise NotFoundException("同步运行不存在")
    from app.models import SyncRecord
    records = db.query(SyncRecord).filter(SyncRecord.sync_run_id == run_id).order_by(SyncRecord.id).limit(limit).all()
    return {"items": [SyncService.record_dict(item) for item in records]}


@router.get("/observations")
def list_observations(decision: str | None = None, patent_id: int | None = None, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    query = db.query(ExternalFactObservation)
    if decision:
        query = query.filter(ExternalFactObservation.decision == decision)
    if patent_id is not None:
        query = query.filter(ExternalFactObservation.patent_id == patent_id)
    return {"items": [SyncService.observation_dict(item) for item in query.order_by(ExternalFactObservation.id.desc()).limit(limit).all()]}


@router.post("/observations/{observation_id}/decision")
def decide_observation(observation_id: int, body: ObservationDecisionRequest, db: Session = Depends(get_db)):
    observation = db.query(ExternalFactObservation).filter(ExternalFactObservation.id == observation_id).first()
    if not observation:
        raise NotFoundException("外部事实观察不存在")
    try:
        return SyncService.observation_dict(SyncService.decide_observation(db, observation, body.decision, body.decided_by, body.reason))
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc


@router.get("/patents/{patent_id}/legal-events")
def list_legal_events(patent_id: int, limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)):
    rows = db.query(LegalStatusEvent).filter(LegalStatusEvent.patent_id == patent_id).order_by(LegalStatusEvent.event_date.desc(), LegalStatusEvent.id.desc()).limit(limit).all()
    return {"items": [{"id": item.id, "patent_id": item.patent_id, "connector_id": item.connector_id, "provider_event_id": item.provider_event_id, "jurisdiction_code": item.jurisdiction_code, "event_code": item.event_code, "event_date": item.event_date.isoformat(), "status": item.status, "raw_description": item.raw_description, "created_at": item.created_at.isoformat() if item.created_at else None} for item in rows]}


@router.get("/watch-events")
def list_watch_events(database_id: int | None = None, status: str | None = None, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    query = db.query(WatchEvent)
    if database_id is not None:
        query = query.filter(WatchEvent.database_id == database_id)
    if status:
        query = query.filter(WatchEvent.status == status)
    return {"items": [SyncService.watch_event_dict(item) for item in query.order_by(WatchEvent.id.desc()).limit(limit).all()]}


@router.patch("/watch-events/{event_id}")
def update_watch_event(event_id: int, body: WatchEventUpdate, db: Session = Depends(get_db)):
    event = db.query(WatchEvent).filter(WatchEvent.id == event_id).first()
    if not event:
        raise NotFoundException("监控事件不存在")
    event.status = body.status
    event.acknowledged_by = body.acknowledged_by
    from app.core.time import utc_now_naive
    event.acknowledged_at = utc_now_naive()
    db.commit()
    return SyncService.watch_event_dict(event)
