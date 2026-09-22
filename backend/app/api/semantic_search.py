from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.database import get_db
from app.models import SemanticDocumentState, SemanticEvaluationCase, SemanticEvaluationDataset, SemanticEvaluationRun, SemanticIndex, SemanticIndexJob, SemanticIndexOutbox, SemanticProviderDefinition, SemanticSearchProfile
from app.schemas.semantic_search import SemanticEvaluationCaseCreate, SemanticEvaluationCaseUpdate, SemanticEvaluationDatasetCreate, SemanticEvaluationRunRequest, SemanticProfileCreate, SemanticProfileUpdate, SemanticProviderCreate, SemanticProviderTestRequest, SemanticProviderUpdate, SemanticQueryRequest, SemanticRebuildRequest
from app.search.contracts import RerankDocument, SemanticError
from app.services.semantic_index_service import SemanticIndexService
from app.services.semantic_search_service import SemanticSearchService
from app.services.semantic_evaluation_service import SemanticEvaluationService
from app.search.sparse import status as sparse_status
from app.search.providers.openai_rerank import OpenAICompatibleRerankProvider

router = APIRouter(prefix="/semantic-search", tags=["semantic-search"])


def _provider_dict(row: SemanticProviderDefinition) -> dict:
    return {"id": row.id, "name": row.name, "provider_kind": row.provider_kind, "provider_type": row.provider_type,
        "endpoint": row.endpoint, "credential_ref": row.credential_ref, "config_json": row.config_json or {}, "enabled": row.enabled,
        "last_health_status": row.last_health_status, "last_health_at": row.last_health_at, "last_error_code": row.last_error_code}


def _validate_provider_endpoint(provider_kind: str, endpoint: str | None) -> str | None:
    """Validate provider URLs before they reach an HTTP client or SDK."""
    normalized = endpoint.strip() if endpoint else None
    if not normalized:
        if provider_kind == "rerank":
            raise AppException("VALIDATION_ERROR", "Rerank provider endpoint is required")
        return None
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AppException("VALIDATION_ERROR", "Provider endpoint must be an absolute http or https URL")
    if parsed.username or parsed.password:
        raise AppException("VALIDATION_ERROR", "Provider endpoint must not contain embedded credentials")
    if parsed.fragment:
        raise AppException("VALIDATION_ERROR", "Provider endpoint must not contain a URL fragment")
    return normalized


def _validate_credential_ref(credential_ref: str | None) -> str | None:
    if credential_ref is None:
        return None
    normalized = credential_ref.strip()
    if not normalized:
        return None
    if normalized.startswith("env://"):
        if not normalized.removeprefix("env://"):
            raise AppException("VALIDATION_ERROR", "env credential reference must include a variable name")
        return normalized
    if normalized.startswith("keyring://"):
        value = normalized.removeprefix("keyring://")
        if "/" not in value:
            raise AppException("VALIDATION_ERROR", "keyring credential reference must include service and account")
        service, account = value.split("/", 1)
        if not service or not account:
            raise AppException("VALIDATION_ERROR", "keyring credential reference must include service and account")
        return normalized
    raise AppException("VALIDATION_ERROR", "credential_ref must use env:// or keyring://")


@router.post("/query")
def semantic_query(body: SemanticQueryRequest, db: Session = Depends(get_db)):
    try:
        return SemanticSearchService.query(db, text=body.query, database_id=body.database_id, mode=body.mode,
            top_k=body.top_k, profile_id=body.profile_id, include_explain=body.include_explain)
    except SemanticError as exc:
        raise AppException(exc.code, str(exc), 400)


@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db)):
    return {"items": [SemanticIndexService.profile_dict(row) for row in db.query(SemanticSearchProfile).order_by(SemanticSearchProfile.id).all()]}


@router.post("/profiles")
def create_profile(body: SemanticProfileCreate, db: Session = Depends(get_db)):
    if body.embedding_provider_id:
        provider = db.get(SemanticProviderDefinition, body.embedding_provider_id)
        if not provider or provider.provider_kind != "embedding":
            raise NotFoundException("Embedding provider", body.embedding_provider_id)
    if body.rerank_provider_id:
        provider = db.get(SemanticProviderDefinition, body.rerank_provider_id)
        if not provider or provider.provider_kind != "rerank":
            raise NotFoundException("Rerank provider", body.rerank_provider_id)
    if body.rerank_enabled and not body.rerank_provider_id:
        raise AppException("SEMANTIC_RERANK_DISABLED", "A rerank provider is required when rerank is enabled")
    if body.quality_gate_enabled and not body.quality_thresholds:
        raise AppException("SEMANTIC_QUALITY_GATE_FAILED", "Quality thresholds are required when the quality gate is enabled")
    if body.vector_backend not in {"zvec", "json_local"}:
        raise AppException("SEMANTIC_BACKEND_UNAVAILABLE", "Unsupported semantic vector backend")
    if body.retrieval_mode not in {"keyword", "semantic", "hybrid"}:
        raise AppException("VALIDATION_ERROR", "Unsupported retrieval mode")
    if body.is_default:
        db.query(SemanticSearchProfile).update({"is_default": False})
    row = SemanticSearchProfile(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return SemanticIndexService.profile_dict(row)


@router.patch("/profiles/{profile_id}")
def update_profile(profile_id: int, body: SemanticProfileUpdate, db: Session = Depends(get_db)):
    row = db.get(SemanticSearchProfile, profile_id)
    if not row:
        raise NotFoundException("Semantic profile", profile_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("embedding_provider_id"):
        provider = db.get(SemanticProviderDefinition, changes["embedding_provider_id"])
        if not provider or provider.provider_kind != "embedding":
            raise NotFoundException("Embedding provider", changes["embedding_provider_id"])
    if changes.get("rerank_provider_id"):
        provider = db.get(SemanticProviderDefinition, changes["rerank_provider_id"])
        if not provider or provider.provider_kind != "rerank":
            raise NotFoundException("Rerank provider", changes["rerank_provider_id"])
    if changes.get("rerank_enabled") and not changes.get("rerank_provider_id", row.rerank_provider_id):
        raise AppException("SEMANTIC_RERANK_DISABLED", "A rerank provider is required when rerank is enabled")
    if changes.get("quality_gate_enabled") and not changes.get("quality_thresholds", row.quality_thresholds or {}):
        raise AppException("SEMANTIC_QUALITY_GATE_FAILED", "Quality thresholds are required when the quality gate is enabled")
    if changes.get("vector_backend") and changes["vector_backend"] not in {"zvec", "json_local"}:
        raise AppException("SEMANTIC_BACKEND_UNAVAILABLE", "Unsupported semantic vector backend")
    if changes.get("retrieval_mode") and changes["retrieval_mode"] not in {"keyword", "semantic", "hybrid"}:
        raise AppException("VALIDATION_ERROR", "Unsupported retrieval mode")
    compatibility_fields = {"embedding_provider_id", "embedding_model", "embedding_dimensions", "vector_backend", "indexed_field_allowlist", "template_version", "chunk_strategy_version", "distance_metric"}
    has_active_index = db.query(SemanticIndex).filter(SemanticIndex.profile_id == profile_id, SemanticIndex.is_active == True).first()
    if has_active_index and compatibility_fields.intersection(changes):
        raise AppException("SEMANTIC_REBUILD_REQUIRED", "Create a new profile and rebuild before changing an active index's compatibility settings")
    if changes.get("is_default"):
        db.query(SemanticSearchProfile).filter(SemanticSearchProfile.id != profile_id).update({"is_default": False})
    for field, value in changes.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return SemanticIndexService.profile_dict(row)


@router.get("/providers")
def list_providers(db: Session = Depends(get_db)):
    return {"items": [_provider_dict(row) for row in db.query(SemanticProviderDefinition).order_by(SemanticProviderDefinition.id).all()]}


@router.post("/providers")
def create_provider(body: SemanticProviderCreate, db: Session = Depends(get_db)):
    valid_types = {"embedding": {"openai_compatible"}, "rerank": {"openai_compatible_rerank"}}
    if body.provider_type not in valid_types.get(body.provider_kind, set()):
        raise AppException("VALIDATION_ERROR", "Unsupported semantic provider kind or type")
    values = body.model_dump()
    values["endpoint"] = _validate_provider_endpoint(body.provider_kind, body.endpoint)
    values["credential_ref"] = _validate_credential_ref(body.credential_ref)
    row = SemanticProviderDefinition(**values)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _provider_dict(row)


@router.patch("/providers/{provider_id}")
def update_provider(provider_id: int, body: SemanticProviderUpdate, db: Session = Depends(get_db)):
    row = db.get(SemanticProviderDefinition, provider_id)
    if not row:
        raise NotFoundException("Semantic provider", provider_id)
    changes = body.model_dump(exclude_unset=True)
    credential_ref = changes.get("credential_ref")
    if "endpoint" in changes:
        changes["endpoint"] = _validate_provider_endpoint(row.provider_kind, changes["endpoint"])
    if credential_ref is not None:
        changes["credential_ref"] = _validate_credential_ref(credential_ref)
    for field, value in changes.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return _provider_dict(row)


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: int, body: SemanticProviderTestRequest, db: Session = Depends(get_db)):
    provider = db.get(SemanticProviderDefinition, provider_id)
    if not provider:
        raise NotFoundException("Semantic provider", provider_id)
    try:
        if provider.provider_kind == "embedding":
            profile = db.get(SemanticSearchProfile, body.profile_id) if body.profile_id else db.query(SemanticSearchProfile).filter_by(embedding_provider_id=provider.id, enabled=True).first()
            if not profile:
                raise SemanticError("SEMANTIC_PROVIDER_DISABLED", "An embedding profile is required to test this provider")
            if profile.embedding_provider_id != provider.id:
                raise SemanticError("SEMANTIC_PROVIDER_DISABLED", "The selected profile does not reference this embedding provider")
            vector = SemanticIndexService._provider(db, profile).embed_query("patwiki provider health check")
            provider.last_health_status, provider.last_health_at, provider.last_error_code = "healthy", datetime.utcnow(), None
            db.commit()
            return {"status": "healthy", "dimensions": len(vector), "checked_at": provider.last_health_at}
        if provider.provider_kind == "rerank":
            model = body.model or (provider.config_json or {}).get("model") or "rerank-default"
            reranker = OpenAICompatibleRerankProvider(endpoint=provider.endpoint, credential_ref=provider.credential_ref, model=model)
            result = reranker.rerank("patwiki provider health check", [RerankDocument("health-check", 0, "provider health check")], 1)
            provider.last_health_status, provider.last_health_at, provider.last_error_code = "healthy", datetime.utcnow(), None
            db.commit()
            return {"status": "healthy", "result_count": len(result), "checked_at": provider.last_health_at}
        raise SemanticError("SEMANTIC_PROVIDER_DISABLED", "Unsupported semantic provider kind")
    except SemanticError as exc:
        provider.last_health_status, provider.last_health_at, provider.last_error_code = "failed", datetime.utcnow(), exc.code
        db.commit()
        raise AppException(exc.code, str(exc), 400)


@router.post("/profiles/{profile_id}/health")
def healthcheck_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.get(SemanticSearchProfile, profile_id)
    if not profile:
        raise NotFoundException("Semantic profile", profile_id)
    provider = db.get(SemanticProviderDefinition, profile.embedding_provider_id) if profile.embedding_provider_id else None
    if not provider:
        raise AppException("SEMANTIC_PROVIDER_DISABLED", "No embedding provider is configured for this profile")
    try:
        vector = SemanticIndexService._provider(db, profile).embed_query("patwiki semantic health check")
        if profile.embedding_dimensions and len(vector) != profile.embedding_dimensions:
            raise SemanticError("SEMANTIC_DIMENSION_MISMATCH", "Embedding provider returned unexpected dimensions")
        provider.last_health_status, provider.last_health_at, provider.last_error_code = "healthy", datetime.utcnow(), None
        db.commit()
        return {"status": "healthy", "dimensions": len(vector), "checked_at": provider.last_health_at}
    except SemanticError as exc:
        provider.last_health_status, provider.last_health_at, provider.last_error_code = "failed", datetime.utcnow(), exc.code
        db.commit()
        raise AppException(exc.code, str(exc), 400)


@router.post("/indexes/rebuild")
def rebuild_index(body: SemanticRebuildRequest, db: Session = Depends(get_db)):
    profile = db.get(SemanticSearchProfile, body.profile_id)
    if not profile:
        raise NotFoundException("Semantic profile", body.profile_id)
    try:
        job = SemanticIndexService.enqueue_rebuild(db, profile, body.database_id)
        return SemanticIndexService.job_dict(job)
    except SemanticError as exc:
        raise AppException(exc.code, str(exc), 400)


@router.get("/indexes")
def list_indexes(db: Session = Depends(get_db)):
    return {"items": [SemanticIndexService.index_dict(row) for row in db.query(SemanticIndex).order_by(SemanticIndex.id.desc()).all()]}


@router.post("/indexes/{index_id}/activate")
def activate_index(index_id: int, db: Session = Depends(get_db)):
    index = db.get(SemanticIndex, index_id)
    if not index:
        raise NotFoundException("Semantic index", index_id)
    try:
        return SemanticIndexService.index_dict(SemanticIndexService.activate(db, index))
    except SemanticError as exc:
        raise AppException(exc.code, str(exc), 400)


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)):
    return {"items": [SemanticIndexService.job_dict(row) for row in db.query(SemanticIndexJob).order_by(SemanticIndexJob.id.desc()).all()]}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(SemanticIndexJob, job_id)
    if not job:
        raise NotFoundException("Semantic index job", job_id)
    return SemanticIndexService.job_dict(job)


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(SemanticIndexJob, job_id)
    if not job:
        raise NotFoundException("Semantic index job", job_id)
    try:
        return SemanticIndexService.job_dict(SemanticIndexService.retry_job(db, job))
    except SemanticError as exc:
        raise AppException(exc.code, str(exc), 400)


@router.get("/evaluations/datasets")
def list_evaluation_datasets(db: Session = Depends(get_db)):
    rows = db.query(SemanticEvaluationDataset).order_by(SemanticEvaluationDataset.id.desc()).all()
    return {"items": [SemanticEvaluationService.dataset_dict(row, db.query(SemanticEvaluationCase).filter_by(dataset_id=row.id).count()) for row in rows]}


@router.post("/evaluations/datasets")
def create_evaluation_dataset(body: SemanticEvaluationDatasetCreate, db: Session = Depends(get_db)):
    row = SemanticEvaluationDataset(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return SemanticEvaluationService.dataset_dict(row, 0)


@router.get("/evaluations/datasets/{dataset_id}/cases")
def list_evaluation_cases(dataset_id: int, db: Session = Depends(get_db)):
    if not db.get(SemanticEvaluationDataset, dataset_id):
        raise NotFoundException("Semantic evaluation dataset", dataset_id)
    return {"items": [SemanticEvaluationService.case_dict(row) for row in db.query(SemanticEvaluationCase).filter_by(dataset_id=dataset_id).order_by(SemanticEvaluationCase.id).all()]}


@router.post("/evaluations/datasets/{dataset_id}/cases")
def create_evaluation_case(dataset_id: int, body: SemanticEvaluationCaseCreate, db: Session = Depends(get_db)):
    if not db.get(SemanticEvaluationDataset, dataset_id):
        raise NotFoundException("Semantic evaluation dataset", dataset_id)
    row = SemanticEvaluationCase(dataset_id=dataset_id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return SemanticEvaluationService.case_dict(row)


@router.patch("/evaluations/cases/{case_id}")
def update_evaluation_case(case_id: int, body: SemanticEvaluationCaseUpdate, db: Session = Depends(get_db)):
    row = db.get(SemanticEvaluationCase, case_id)
    if not row:
        raise NotFoundException("Semantic evaluation case", case_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return SemanticEvaluationService.case_dict(row)


@router.delete("/evaluations/cases/{case_id}")
def delete_evaluation_case(case_id: int, db: Session = Depends(get_db)):
    row = db.get(SemanticEvaluationCase, case_id)
    if not row:
        raise NotFoundException("Semantic evaluation case", case_id)
    db.delete(row)
    db.commit()
    return {"success": True}


@router.get("/evaluations/runs")
def list_evaluation_runs(db: Session = Depends(get_db)):
    return {"items": [SemanticEvaluationService.run_dict(row) for row in db.query(SemanticEvaluationRun).order_by(SemanticEvaluationRun.id.desc()).limit(100).all()]}


@router.post("/evaluations/run")
def run_evaluation(body: SemanticEvaluationRunRequest, db: Session = Depends(get_db)):
    dataset = db.get(SemanticEvaluationDataset, body.dataset_id)
    profile = db.get(SemanticSearchProfile, body.profile_id)
    if not dataset:
        raise NotFoundException("Semantic evaluation dataset", body.dataset_id)
    if not profile:
        raise NotFoundException("Semantic profile", body.profile_id)
    index = db.get(SemanticIndex, body.index_id) if body.index_id else None
    if body.index_id and (not index or index.profile_id != profile.id):
        raise AppException("SEMANTIC_INDEX_NOT_READY", "Evaluation index does not belong to the selected profile")
    try:
        run = SemanticEvaluationService.run(db, dataset, profile, body.mode, body.top_k, index=index)
        return SemanticEvaluationService.run_dict(run)
    except SemanticError as exc:
        raise AppException(exc.code, str(exc), 400)


@router.get("/status")
def semantic_status(db: Session = Depends(get_db)):
    active = db.query(SemanticIndex).filter(SemanticIndex.is_active == True).count()
    pending = db.query(SemanticIndexJob).filter(SemanticIndexJob.status.in_(["pending", "running", "retry_wait"])).count()
    sparse = sparse_status(db)
    active_indexes = db.query(SemanticIndex).filter(SemanticIndex.is_active == True).all()
    active_versions = [row.index_version for row in active_indexes]
    state_query = db.query(SemanticDocumentState).filter(SemanticDocumentState.index_version.in_(active_versions)) if active_versions else None
    document_indexed = state_query.filter(SemanticDocumentState.status == "indexed").count() if state_query else 0
    document_pending = state_query.filter(SemanticDocumentState.status.in_(["pending", "claimed", "retry_wait"])).count() if state_query else 0
    document_stale = state_query.filter(SemanticDocumentState.status == "stale").count() if state_query else 0
    document_failed = state_query.filter(SemanticDocumentState.status == "failed").count() if state_query else 0
    document_total = state_query.filter(SemanticDocumentState.status != "deleted").count() if state_query else 0
    outbox_counts = {
        key: db.query(SemanticIndexOutbox).filter(SemanticIndexOutbox.status == key).count()
        for key in ("pending", "retry_wait", "dead_letter")
    }
    job_failed = db.query(SemanticIndexJob).filter(SemanticIndexJob.status == "failed").count()
    job_dead_letter = db.query(SemanticIndexJob).filter(SemanticIndexJob.status == "dead_letter").count()
    last_passed = db.query(func.max(SemanticEvaluationRun.completed_at)).filter(SemanticEvaluationRun.status == "passed").scalar()
    return {"configured_profiles": db.query(SemanticSearchProfile).filter(SemanticSearchProfile.enabled == True).count(),
        "active_indexes": active, "pending_jobs": pending,
        "outbox_pending": outbox_counts["pending"], "outbox_retry_wait": outbox_counts["retry_wait"],
        "outbox_dead_letter": outbox_counts["dead_letter"], "job_failed": job_failed,
        "job_dead_letter": job_dead_letter, "document_indexed": document_indexed,
        "document_pending": document_pending, "document_stale": document_stale,
        "document_failed": document_failed,
        "coverage_rate": round(document_indexed / document_total, 4) if document_total else 0.0,
        "last_passed_evaluation_at": last_passed,
        "sparse_backend": sparse["backend"], "sparse_available": sparse["available"],
        "evaluated_profiles": db.query(SemanticEvaluationRun.profile_id).filter(SemanticEvaluationRun.status == "passed").distinct().count(),
        "checked_at": datetime.utcnow()}
