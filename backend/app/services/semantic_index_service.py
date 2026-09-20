from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Patent, PatentDatabaseMembership, SemanticDocumentState, SemanticIndex, SemanticIndexJob, SemanticIndexOutbox, SemanticProviderDefinition, SemanticSearchProfile
from app.search.contracts import SemanticError, VectorDocument
from app.search.document_builder import SemanticDocumentBuilder
from app.search.providers.openai_embedding import OpenAICompatibleEmbeddingProvider
from app.search.vector import open_vector_store
from app.services.patent_database_scope import in_database


class SemanticIndexService:
    @staticmethod
    def profile_dict(profile: SemanticSearchProfile) -> dict:
        return {key: getattr(profile, key) for key in (
            "id", "name", "is_default", "enabled", "vector_backend", "embedding_provider_id",
            "embedding_model", "embedding_dimensions", "retrieval_mode", "keyword_weight", "vector_weight",
            "rrf_k", "keyword_candidate_count", "vector_candidate_count", "result_top_k", "template_version",
            "chunk_strategy_version", "distance_metric", "indexed_field_allowlist", "remote_field_allowlist",
        )}

    @staticmethod
    def index_dict(index: SemanticIndex) -> dict:
        return {key: getattr(index, key) for key in (
            "id", "profile_id", "database_id", "index_version", "backend_type", "path", "status", "is_active",
            "document_count", "patent_count", "source_watermark", "manifest_hash", "started_at", "completed_at",
            "activated_at", "last_error_code", "last_error_message", "created_at",
        )}

    @staticmethod
    def job_dict(job: SemanticIndexJob) -> dict:
        return {key: getattr(job, key) for key in (
            "id", "profile_id", "index_id", "job_type", "status", "total_items", "processed_items",
            "failed_items", "skipped_items", "attempt_count", "max_attempts", "next_retry_at", "error_code",
            "error_message", "created_at", "started_at", "finished_at",
        )}

    @staticmethod
    def _version(profile: SemanticSearchProfile) -> str:
        identity = json.dumps({"backend": profile.vector_backend, "model": profile.embedding_model,
            "dimensions": profile.embedding_dimensions, "template": profile.template_version,
            "chunk": profile.chunk_strategy_version, "metric": profile.distance_metric}, sort_keys=True)
        return hashlib.sha256(identity.encode()).hexdigest()[:16]

    @staticmethod
    def _index_path(profile_id: int, version: str) -> Path:
        return settings.VECTORS_DIR / str(profile_id) / version

    @classmethod
    def get_active_index(cls, db: Session, profile_id: int, database_id: int | None = None) -> SemanticIndex | None:
        query = db.query(SemanticIndex).filter(SemanticIndex.profile_id == profile_id, SemanticIndex.is_active == True)
        if database_id is None:
            query = query.filter(SemanticIndex.database_id.is_(None))
        else:
            query = query.filter(SemanticIndex.database_id == database_id)
        return query.order_by(SemanticIndex.id.desc()).first()

    @staticmethod
    def _provider(db: Session, profile: SemanticSearchProfile):
        provider = db.get(SemanticProviderDefinition, profile.embedding_provider_id) if profile.embedding_provider_id else None
        if not provider or not provider.enabled:
            raise SemanticError("SEMANTIC_PROVIDER_DISABLED", "No enabled embedding provider is configured for this profile")
        if provider.provider_kind != "embedding" or provider.provider_type != "openai_compatible":
            raise SemanticError("SEMANTIC_PROVIDER_DISABLED", "Unsupported embedding provider configuration")
        return OpenAICompatibleEmbeddingProvider(endpoint=provider.endpoint, credential_ref=provider.credential_ref,
            model=profile.embedding_model, dimensions=profile.embedding_dimensions)

    @classmethod
    def enqueue_rebuild(cls, db: Session, profile: SemanticSearchProfile, database_id: int | None = None) -> SemanticIndexJob:
        version = cls._version(profile)
        index_version = f"{version}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        index = SemanticIndex(profile_id=profile.id, database_id=database_id, index_version=index_version,
            backend_type=profile.vector_backend, path=str(cls._index_path(profile.id, index_version)), status="building")
        # Recompute the path from the persisted version so timestamp identity always agrees.
        index.path = str(cls._index_path(profile.id, index.index_version))
        db.add(index)
        db.flush()
        job = SemanticIndexJob(profile_id=profile.id, index_id=index.id, job_type="rebuild", status="pending")
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @classmethod
    def run_job(cls, db: Session, job: SemanticIndexJob) -> SemanticIndexJob:
        index = db.get(SemanticIndex, job.index_id)
        profile = db.get(SemanticSearchProfile, job.profile_id)
        if not index or not profile:
            raise SemanticError("SEMANTIC_INDEX_NOT_READY", "Semantic index job references missing configuration")
        job.status, job.started_at, job.attempt_count = "running", datetime.utcnow(), job.attempt_count + 1
        db.commit()
        store = None
        try:
            provider = cls._provider(db, profile)
            patents = db.query(Patent).filter(in_database(index.database_id)).all() if index.database_id else db.query(Patent).all()
            job.total_items = len(patents)
            store = open_vector_store(profile.vector_backend, Path(index.path), profile.embedding_dimensions)
            for patent in patents:
                document = SemanticDocumentBuilder.build_summary(patent, profile.indexed_field_allowlist or [])
                vector = provider.embed_documents([document.text])[0]
                store.upsert([VectorDocument(document.document_id, patent.id, document.text, vector, document.metadata)])
                state = db.query(SemanticDocumentState).filter_by(profile_id=profile.id, index_version=index.index_version, document_id=document.document_id).first()
                if not state:
                    state = SemanticDocumentState(profile_id=profile.id, index_version=index.index_version, patent_id=patent.id,
                        document_type="patent_summary", document_id=document.document_id, content_hash=document.content_hash)
                    db.add(state)
                state.indexed_hash, state.status, state.last_indexed_at = document.content_hash, "indexed", datetime.utcnow()
                job.processed_items += 1
            index.document_count, index.patent_count, index.status, index.completed_at = store.count(), len(patents), "validating", datetime.utcnow()
            index.manifest_hash = hashlib.sha256(index.index_version.encode()).hexdigest()
            job.status, job.finished_at = "succeeded", datetime.utcnow()
            db.commit()
        except SemanticError as exc:
            job.status, job.error_code, job.error_message, job.finished_at = "failed", exc.code, str(exc), datetime.utcnow()
            index.status, index.last_error_code, index.last_error_message = "failed", exc.code, str(exc)
            db.commit()
        except Exception as exc:
            job.status, job.error_code, job.error_message, job.finished_at = "failed", "SEMANTIC_INDEX_FAILED", str(exc), datetime.utcnow()
            index.status, index.last_error_code, index.last_error_message = "failed", "SEMANTIC_INDEX_FAILED", str(exc)
            db.commit()
        finally:
            close = getattr(store, "close", None)
            if close:
                close()
        return job

    @classmethod
    def activate(cls, db: Session, index: SemanticIndex) -> SemanticIndex:
        if index.status not in {"validating", "active"} or not Path(index.path).exists():
            raise SemanticError("SEMANTIC_INDEX_NOT_READY", "Index must finish validation before activation")
        db.query(SemanticIndex).filter(SemanticIndex.profile_id == index.profile_id, SemanticIndex.database_id == index.database_id,
            SemanticIndex.is_active == True).update({"is_active": False, "status": "retired"}, synchronize_session=False)
        index.is_active, index.status, index.activated_at = True, "active", datetime.utcnow()
        db.commit()
        db.refresh(index)
        return index

    @staticmethod
    def enqueue_patent(db: Session, patent_id: int, reason: str) -> None:
        key = f"upsert:{patent_id}"
        row = db.query(SemanticIndexOutbox).filter_by(dedupe_key=key).first()
        if row and row.status in {"pending", "claimed", "retry_wait"}:
            row.reason = reason
            return
        if not row:
            db.add(SemanticIndexOutbox(operation="upsert", patent_id=patent_id, reason=reason, dedupe_key=key))

    @staticmethod
    def enqueue_delete(db: Session, patent_id: int, reason: str = "record_deleted") -> None:
        key = f"delete:{patent_id}"
        if not db.query(SemanticIndexOutbox).filter_by(dedupe_key=key).first():
            db.add(SemanticIndexOutbox(operation="delete", patent_id=patent_id, reason=reason, dedupe_key=key))

    @classmethod
    def apply_outbox(cls, db: Session, item: SemanticIndexOutbox) -> bool:
        """Apply one durable event to every relevant active projection."""
        patent = db.get(Patent, item.patent_id)
        indexes = db.query(SemanticIndex).filter(SemanticIndex.is_active == True).all()
        if patent:
            membership_ids = {row.database_id for row in db.query(PatentDatabaseMembership).filter(PatentDatabaseMembership.patent_id == item.patent_id).all()}
            relevant = [index for index in indexes if index.database_id is None or index.database_id in membership_ids]
        else:
            # Membership is gone after a delete. Document state is the durable proof
            # that a projection contains this Patent and must be cleaned up.
            relevant = [index for index in indexes if db.query(SemanticDocumentState).filter_by(
                profile_id=index.profile_id, index_version=index.index_version,
                document_id=f"{item.patent_id}:patent_summary:0",
            ).first()]
        if not relevant:
            return False
        for index in relevant:
            profile = db.get(SemanticSearchProfile, index.profile_id)
            if not profile:
                continue
            document_id = f"{item.patent_id}:patent_summary:0"
            store = None
            try:
                store = open_vector_store(profile.vector_backend, Path(index.path), profile.embedding_dimensions)
                if item.operation == "delete" or not patent:
                    store.delete([document_id])
                    index.document_count = store.count()
                    state = db.query(SemanticDocumentState).filter_by(profile_id=profile.id, index_version=index.index_version, document_id=document_id).first()
                    if state:
                        state.status = "deleted"
                    continue
                provider = cls._provider(db, profile)
                document = SemanticDocumentBuilder.build_summary(patent, profile.indexed_field_allowlist or [])
                state = db.query(SemanticDocumentState).filter_by(profile_id=profile.id, index_version=index.index_version, document_id=document.document_id).first()
                if state and state.indexed_hash == document.content_hash:
                    continue
                store.upsert([VectorDocument(document.document_id, patent.id, document.text, provider.embed_documents([document.text])[0], document.metadata)])
                index.document_count = store.count()
                if not state:
                    state = SemanticDocumentState(profile_id=profile.id, index_version=index.index_version, patent_id=patent.id,
                        document_type="patent_summary", document_id=document.document_id, content_hash=document.content_hash)
                    db.add(state)
                state.content_hash, state.indexed_hash, state.status, state.last_indexed_at = document.content_hash, document.content_hash, "indexed", datetime.utcnow()
            finally:
                close = getattr(store, "close", None)
                if close:
                    close()
        return True
