from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.database import get_db
from app.models import SemanticIndex, SemanticIndexJob, SemanticProviderDefinition, SemanticSearchProfile
from app.schemas.semantic_search import SemanticProfileCreate, SemanticProfileUpdate, SemanticProviderCreate, SemanticProviderUpdate, SemanticQueryRequest, SemanticRebuildRequest
from app.search.contracts import SemanticError
from app.services.semantic_index_service import SemanticIndexService
from app.services.semantic_search_service import SemanticSearchService

router = APIRouter(prefix="/semantic-search", tags=["semantic-search"])


def _provider_dict(row: SemanticProviderDefinition) -> dict:
    return {"id": row.id, "name": row.name, "provider_kind": row.provider_kind, "provider_type": row.provider_type,
        "endpoint": row.endpoint, "credential_ref": row.credential_ref, "config_json": row.config_json or {}, "enabled": row.enabled,
        "last_health_status": row.last_health_status, "last_health_at": row.last_health_at, "last_error_code": row.last_error_code}


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
    if body.embedding_provider_id and not db.get(SemanticProviderDefinition, body.embedding_provider_id):
        raise NotFoundException("Semantic provider", body.embedding_provider_id)
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
    if changes.get("embedding_provider_id") and not db.get(SemanticProviderDefinition, changes["embedding_provider_id"]):
        raise NotFoundException("Semantic provider", changes["embedding_provider_id"])
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
    if body.provider_kind != "embedding" or body.provider_type != "openai_compatible":
        raise AppException("VALIDATION_ERROR", "Only OpenAI-compatible embedding providers are supported in Phase 1")
    if body.credential_ref and not body.credential_ref.startswith(("env://", "keyring://")):
        raise AppException("VALIDATION_ERROR", "credential_ref must use env:// or keyring://")
    row = SemanticProviderDefinition(**body.model_dump())
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
    if credential_ref is not None and credential_ref and not credential_ref.startswith(("env://", "keyring://")):
        raise AppException("VALIDATION_ERROR", "credential_ref must use env:// or keyring://")
    for field, value in changes.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return _provider_dict(row)


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


@router.get("/status")
def semantic_status(db: Session = Depends(get_db)):
    active = db.query(SemanticIndex).filter(SemanticIndex.is_active == True).count()
    pending = db.query(SemanticIndexJob).filter(SemanticIndexJob.status.in_(["pending", "running", "retry_wait"])).count()
    return {"configured_profiles": db.query(SemanticSearchProfile).filter(SemanticSearchProfile.enabled == True).count(),
        "active_indexes": active, "pending_jobs": pending, "checked_at": datetime.utcnow()}
