"""External patent connector, subscription and synchronization APIs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from jsonschema import Draft202012Validator

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.time import utc_now_naive
from app.services.patent_database_scope import in_database
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
    SyncLease,
    Patent,
    SyncUpdateBatch,
    WatchEvent,
)
from app.schemas.sync import (
    ConnectorCreate,
    ConnectorUpdate,
    CredentialCreate,
    McpToolMapPreviewRequest,
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
from app.services.patent_identity_service import normalize_publication_number
from app.services.publication_governance_service import classify_database, publication_parts


router = APIRouter(prefix="/sync", tags=["external-sync"])


class PublicationMatchRequest(BaseModel):
    database_id: int
    publications: list[str] = Field(default_factory=list, max_length=500)
    patent_ids: list[int] = Field(default_factory=list, max_length=500)


class McpToolRequest(BaseModel):
    service: str = Field(min_length=1, max_length=150)
    tool: str = Field(min_length=1, max_length=150)
    arguments: dict = Field(default_factory=dict)


@router.post("/resolve-publications")
def resolve_publications(body: PublicationMatchRequest, db: Session = Depends(get_db)):
    _require_database(db, body.database_id)
    requested = list(dict.fromkeys(filter(None, (normalize_publication_number(value) for value in body.publications))))
    candidates = db.query(Patent).filter(in_database(body.database_id)).filter(
        (Patent.publication_number.in_(requested)) | (Patent.id.in_(body.patent_ids or [-1]))
    ).all()
    matched = []
    found = set()
    for patent in candidates:
        normalized = normalize_publication_number(patent.publication_number)
        if normalized in requested or patent.id in body.patent_ids:
            found.add(normalized)
            _, country, kind = publication_parts(patent.publication_number)
            matched.append({"patent_id": patent.id, "publication_number": patent.publication_number,
                            "application_number": patent.application_number, "title": patent.title,
                            "country": country or patent.country, "ungranted": kind.startswith("A") if kind else False})
    return {"matched": matched, "unmatched": [number for number in requested if number not in found]}


@router.post("/databases/{database_id}/classify-publications")
def classify_publications(database_id: int, db: Session = Depends(get_db)):
    _require_database(db, database_id)
    return {"updated": classify_database(db, database_id)}


def _require_database(db: Session, database_id: int) -> PatentDatabase:
    database = db.query(PatentDatabase).filter(PatentDatabase.id == database_id).first()
    if not database:
        raise NotFoundException("数据库不存在")
    return database


def _require_connector(db: Session, connector_id: int) -> ConnectorDefinition:
    connector = db.query(ConnectorDefinition).filter(
        ConnectorDefinition.id == connector_id,
        ConnectorDefinition.deleted_at.is_(None),
    ).first()
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
    # Demo connectors were seed data only and must not be selectable as an
    # external source for production updates.
    connectors = db.query(ConnectorDefinition).filter(ConnectorDefinition.provider_type != "demo")
    active = connectors.filter(ConnectorDefinition.deleted_at.is_(None)).order_by(ConnectorDefinition.id).all()
    archived = connectors.filter(ConnectorDefinition.deleted_at.is_not(None)).order_by(ConnectorDefinition.id).all()
    return {
        "items": [SyncService.connector_dict(item) for item in active],
        "archived_items": [SyncService.connector_dict(item) for item in archived],
    }


@router.post("/connectors")
def create_connector(body: ConnectorCreate, db: Session = Depends(get_db)):
    existing = db.query(ConnectorDefinition).filter(ConnectorDefinition.code == body.code).first()
    if existing and existing.deleted_at is None:
        raise BadRequestException("连接器 code 已存在")
    values = body.model_dump()
    _validate_connector_config(values)
    if existing:
        existing.deleted_at = None
        connector = SyncService.create_or_update_connector(db, values, existing)
    else:
        connector = SyncService.create_or_update_connector(db, values)
    return SyncService.connector_dict(connector)


@router.patch("/connectors/{connector_id}")
def update_connector(connector_id: int, body: ConnectorUpdate, db: Session = Depends(get_db)):
    connector = _require_connector(db, connector_id)
    values = body.model_dump(exclude_unset=True)
    _validate_connector_config(values)
    connector = SyncService.create_or_update_connector(db, values, connector)
    return SyncService.connector_dict(connector)


@router.delete("/connectors/{connector_id}")
def delete_connector(connector_id: int, db: Session = Depends(get_db)):
    connector = _require_connector(db, connector_id)
    from app.core.time import utc_now_naive
    connector.deleted_at = utc_now_naive()
    connector.enabled = False
    db.commit()
    return {"success": True, "connector_id": connector_id, "deleted_at": connector.deleted_at.isoformat()}


@router.post("/connectors/{connector_id}/restore")
def restore_connector(connector_id: int, db: Session = Depends(get_db)):
    connector = db.query(ConnectorDefinition).filter(ConnectorDefinition.id == connector_id).first()
    if not connector:
        raise NotFoundException("连接器不存在")
    if connector.deleted_at is None:
        raise BadRequestException("连接器当前未删除")
    connector.deleted_at = None
    connector.enabled = False
    db.commit()
    db.refresh(connector)
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
        from app.integrations.himmpat import tool_mappable_fields
        for service in catalog.get("services", []):
            for tool in service.get("tools", []):
                tool["mappable_fields"] = tool_mappable_fields(tool.get("name"))
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


@router.post("/connectors/{connector_id}/tools/call")
def call_connector_tool(connector_id: int, body: McpToolRequest, db: Session = Depends(get_db)):
    connector = _require_connector(db, connector_id)
    if not connector.enabled:
        raise BadRequestException("连接器已停用")
    catalog = connector.mcp_catalog_json or {}
    tool = next((tool for service in catalog.get("services", []) if service.get("service") == body.service
                 for tool in service.get("tools", []) if tool.get("name") == body.tool), None)
    if tool is None:
        raise BadRequestException("工具不在当前连接器目录中，请先发现工具")
    schema = tool.get("inputSchema") or {}
    errors = list(Draft202012Validator(schema).iter_errors(body.arguments))
    if errors:
        # Schema errors may include the submitted value, so expose only the
        # path and rule rather than echoing image data or user documents.
        first = errors[0]
        path = ".".join(str(part) for part in first.absolute_path) or "arguments"
        raise BadRequestException(f"工具参数 {path} 不符合规则：{first.validator}")
    runtime = None
    try:
        runtime = get_connector(connector)
        call = getattr(runtime, "call_discovered_tool", None)
        if not callable(call):
            raise BadRequestException("该连接器不支持工具调用")
        data, evidence = call(body.service, body.tool, body.arguments)
        from app.models import ExternalSnapshot
        from app.services.sync_support import hash_payload
        run = SyncRun(connector_id=connector.id, trigger="mcp_tool", status="succeeded",
                      started_at=utc_now_naive(), finished_at=utc_now_naive(),
                      counts_json={"tools": 1})
        db.add(run)
        db.flush()
        snapshot = ExternalSnapshot(connector_id=connector.id,
                                    sync_run_id=run.id,
                                    request_metadata={"mode": "mcp_tool", "service": body.service, "tool": body.tool},
                                    payload_json=evidence, payload_hash=hash_payload(evidence), source_version="himmpat-mcp")
        db.add(snapshot)
        db.commit()
        return {"data": data, "snapshot_id": snapshot.id, "service": body.service, "tool": body.tool}
    except BadRequestException:
        raise
    except Exception as exc:
        db.rollback()
        raise BadRequestException(f"MCP 工具调用失败：{exc}") from exc
    finally:
        if runtime is not None:
            close = getattr(runtime, "close", None)
            if callable(close):
                close()


@router.post("/connectors/{connector_id}/tools/map-preview")
def map_tool_result_preview(connector_id: int, body: McpToolMapPreviewRequest, db: Session = Depends(get_db)):
    connector = _require_connector(db, connector_id)
    if not connector.enabled:
        raise BadRequestException("连接器已停用")
    _require_database(db, body.database_id)
    patent = db.query(Patent).filter(Patent.id == body.patent_id).first()
    if not patent:
        raise NotFoundException("专利不存在")
    catalog = connector.mcp_catalog_json or {}
    tool = next((tool for service in catalog.get("services", []) if service.get("service") == body.service
                 for tool in service.get("tools", []) if tool.get("name") == body.tool), None)
    if tool is None:
        raise BadRequestException("工具不在当前连接器目录中，请先发现工具")
    schema = tool.get("inputSchema") or {}
    errors = list(Draft202012Validator(schema).iter_errors(body.arguments))
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.absolute_path) or "arguments"
        raise BadRequestException(f"工具参数 {path} 不符合规则：{first.validator}")
    from app.integrations.himmpat import tool_mappable_fields
    mappable = tool_mappable_fields(body.tool)
    if not mappable:
        raise BadRequestException("该工具的结果暂不支持映射到专利字段")
    runtime = None
    try:
        runtime = get_connector(connector)
        call = getattr(runtime, "call_discovered_tool", None)
        extract = getattr(runtime, "extract_mapped_fields", None)
        if not callable(call) or not callable(extract):
            raise BadRequestException("该连接器不支持工具结果映射")
        data, evidence = call(body.service, body.tool, body.arguments)
        patent_id = _external_patent_id(body.arguments)
        mapped = extract(body.tool, data, patent_id)
        if not mapped:
            raise BadRequestException("未能从工具结果中识别出可写入的字段")
        record = ProviderPatentRecord(
            external_record_id=str(patent_id or patent.publication_number or patent.id),
            identifiers=tuple(SyncUpdateService._identifiers(patent)),
            fields=mapped,
            source_version="himmpat-mcp",
            raw_payload=evidence,
        )
        batch = SyncUpdateService.preview_from_records(
            db, connector, body.database_id, {patent.id: record}, body.fields,
            request_metadata={"mode": "mcp_tool_map", "service": body.service, "tool": body.tool},
        )
    except BadRequestException:
        raise
    except Exception as exc:
        db.rollback()
        raise BadRequestException(f"MCP 工具结果映射失败：{exc}") from exc
    finally:
        if runtime is not None:
            close = getattr(runtime, "close", None)
            if callable(close):
                close()
    return SyncUpdateService._batch_dict(batch)


def _external_patent_id(arguments: dict) -> str | None:
    for key in ("id", "patentId", "patent_id"):
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, list) and value:
            return str(value[0])
    ids = arguments.get("ids")
    if isinstance(ids, list) and ids:
        return str(ids[0])
    return None


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
    return {"items": [SyncService.subscription_dict(item) for item in query.order_by(SyncSubscription.id.desc()).all() if not (item.schedule_json or {}).get("deleted_at")]}


@router.delete("/subscriptions/{subscription_id}")
def delete_subscription(subscription_id: int, db: Session = Depends(get_db)):
    subscription = db.query(SyncSubscription).filter(SyncSubscription.id == subscription_id).first()
    if not subscription:
        raise NotFoundException("同步订阅不存在")
    lease = db.query(SyncLease).filter(SyncLease.subscription_id == subscription_id).first()
    if lease and lease.expires_at > utc_now_naive():
        raise BadRequestException("规则正在运行，请等待运行结束后删除")
    subscription.enabled = False
    subscription.next_run_at = None
    subscription.schedule_json = {**(subscription.schedule_json or {}), "deleted_at": utc_now_naive().isoformat()}
    db.commit()
    return {"success": True}


@router.post("/subscriptions")
def create_subscription(body: SubscriptionCreate, db: Session = Depends(get_db)):
    _require_database(db, body.database_id)
    _require_connector(db, body.connector_id)
    if body.saved_query_id is not None:
        query = db.query(SavedPatentQuery).filter(SavedPatentQuery.id == body.saved_query_id).first()
        if not query or query.database_id != body.database_id:
            raise BadRequestException("检索式不存在或不属于目标数据库")
    values = body.model_dump(exclude={"tracked_patent_ids", "status_strategies"})
    tracked_patent_ids = list(dict.fromkeys(body.tracked_patent_ids))
    if tracked_patent_ids:
        matches = db.query(Patent.id).filter(Patent.id.in_(tracked_patent_ids), in_database(body.database_id)).all()
        if len(matches) != len(tracked_patent_ids):
            raise BadRequestException("指定专利必须全部属于当前数据库")
        values["mode"] = "tracked_patents"
        values["scope_json"] = {**(values.get("scope_json") or {}), "patent_ids": tracked_patent_ids}
    schedule = dict(values.get("schedule_json") or {})
    if body.status_strategies:
        schedule["status_strategies"] = body.status_strategies
    _validate_schedule(schedule)
    values["schedule_json"] = schedule
    if body.enabled and not schedule:
        values["schedule_json"] = {"interval_minutes": 1440}
    if values.get("enabled"):
        if schedule.get("run_at") or schedule.get("start_at"):
            values["next_run_at"] = SyncService.next_run_at(schedule) or utc_now_naive()
        else:
            values["next_run_at"] = utc_now_naive()
    for patent_id in list((values.get("scope_json") or {}).get("patent_ids") or []):
        if not db.query(Patent.id).filter(Patent.id == int(patent_id)).first():
            raise BadRequestException(f"指定专利不存在：{patent_id}")
    return SyncService.subscription_dict(SyncService.create_subscription(db, values))


@router.patch("/subscriptions/{subscription_id}")
def update_subscription(subscription_id: int, body: SubscriptionUpdate, db: Session = Depends(get_db)):
    subscription = db.query(SyncSubscription).filter(SyncSubscription.id == subscription_id).first()
    if not subscription:
        raise NotFoundException("同步订阅不存在")
    values = body.model_dump(exclude_unset=True)
    if "status_strategies" in values:
        strategy = values.pop("status_strategies") or {}
        schedule = dict(values.get("schedule_json") or subscription.schedule_json or {})
        schedule["status_strategies"] = strategy
        values["schedule_json"] = schedule
    if "schedule_json" in values:
        _validate_schedule(values["schedule_json"] or {})
    if "saved_query_id" in values and values["saved_query_id"] is not None:
        query = db.query(SavedPatentQuery).filter(SavedPatentQuery.id == values["saved_query_id"]).first()
        if not query or query.database_id != subscription.database_id:
            raise BadRequestException("检索式不存在或不属于目标数据库")
    for key, value in values.items():
        setattr(subscription, key, value)
    if values.get("enabled") is True and subscription.next_run_at is None:
        subscription.next_run_at = utc_now_naive()
    if "schedule_json" in values and subscription.enabled:
        schedule = subscription.schedule_json or {}
        subscription.next_run_at = SyncService.next_run_at(schedule) if schedule.get("run_at") or schedule.get("start_at") else utc_now_naive()
        if subscription.mode in {"patent_list", "tracked_patents"}:
            due_times = []
            strategies = schedule.get("status_strategies") or {}
            for tracked in subscription.tracked_patents:
                patent = db.query(Patent).filter(Patent.id == tracked.patent_id).first()
                status = str(getattr(patent.legal_status, "value", patent.legal_status) or "unknown") if patent else "unknown"
                policy = strategies.get(status) or {}
                tracked.enabled = bool(policy.get("enabled", True))
                tracked.next_run_at = subscription.next_run_at if tracked.enabled else None
                if tracked.next_run_at:
                    due_times.append(tracked.next_run_at)
            subscription.next_run_at = min(due_times) if due_times else None
    db.commit()
    db.refresh(subscription)
    return SyncService.subscription_dict(subscription)


def _validate_schedule(schedule: dict) -> None:
    from app.models import LegalStatus
    from datetime import datetime

    if schedule.get("interval_days") is not None:
        try:
            days = int(schedule["interval_days"])
        except (TypeError, ValueError) as exc:
            raise BadRequestException("扫描间隔天数必须是整数") from exc
        if days < 1 or days > 3650:
            raise BadRequestException("扫描间隔天数必须在 1 到 3650 天之间")
    if schedule.get("interval_minutes") is not None:
        try:
            minutes = int(schedule["interval_minutes"])
        except (TypeError, ValueError) as exc:
            raise BadRequestException("扫描间隔分钟必须是整数") from exc
        if minutes < 1 or minutes > 525600:
            raise BadRequestException("扫描间隔分钟必须在 1 到 525600 分钟之间")
    raw_run_at = schedule.get("run_at") or schedule.get("start_at")
    if raw_run_at:
        try:
            datetime.fromisoformat(str(raw_run_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise BadRequestException("指定触发时间格式无效") from exc
    known_statuses = {item.value for item in LegalStatus} | {"unknown"}
    for status, policy in (schedule.get("status_strategies") or {}).items():
        if status not in known_statuses:
            raise BadRequestException(f"未知法律状态策略：{status}")
        if not isinstance(policy, dict):
            raise BadRequestException(f"法律状态 {status} 的扫描策略必须是对象")
        if policy.get("interval_days") is not None:
            try:
                days = int(policy["interval_days"])
            except (TypeError, ValueError) as exc:
                raise BadRequestException(f"法律状态 {status} 的间隔天数必须是整数") from exc
            if days < 1 or days > 3650:
                raise BadRequestException(f"法律状态 {status} 的间隔天数必须在 1 到 3650 天之间")


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
    if not connector.enabled:
        raise BadRequestException("连接器已停用")
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
        run = SyncService.refresh_patent(db, connector, identifier, database_id, body.review_policy, body.fields)
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
    from sqlalchemy.orm import joinedload
    records = (db.query(SyncRecord)
               .options(joinedload(SyncRecord.patent), joinedload(SyncRecord.snapshot))
               .filter(SyncRecord.sync_run_id == run_id).order_by(SyncRecord.id).limit(limit).all())
    return {"items": [SyncService.record_dict(item) for item in records]}


@router.get("/observations")
def list_observations(decision: str | None = None, patent_id: int | None = None, run_id: int | None = None,
                      limit: int = Query(100, ge=1, le=2000), db: Session = Depends(get_db)):
    query = db.query(ExternalFactObservation)
    if decision:
        query = query.filter(ExternalFactObservation.decision == decision)
    if patent_id is not None:
        query = query.filter(ExternalFactObservation.patent_id == patent_id)
    if run_id is not None:
        query = query.filter(ExternalFactObservation.sync_run_id == run_id)
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
