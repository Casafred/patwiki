from __future__ import annotations

import hashlib
import time
from pathlib import Path

from sqlalchemy import String, or_
from sqlalchemy.orm import Session

from app.models import Patent, PatentIdentifier, SemanticIndex, SemanticSearchLog, SemanticSearchProfile
from app.search.contracts import RerankDocument, SemanticError
from app.search.document_builder import SemanticDocumentBuilder
from app.search.fusion import weighted_rrf
from app.search.sparse import search as sparse_search
from app.search.providers.openai_embedding import OpenAICompatibleEmbeddingProvider
from app.search.vector import open_vector_store
from app.services.patent_database_scope import in_database
from app.services.semantic_index_service import SemanticIndexService


KEYWORD_FIELDS = ("title", "abstract", "claims", "description_full", "application_number", "publication_number", "grant_number", "applicant", "inventor", "assignee", "ipc_main", "ipc_all", "cpc_main", "cpc_all", "technical_problem", "technical_solution", "technical_effect")


class SemanticSearchService:
    @staticmethod
    def _profile(db: Session, profile_id: int | None) -> SemanticSearchProfile | None:
        if profile_id is not None:
            return db.get(SemanticSearchProfile, profile_id)
        return db.query(SemanticSearchProfile).filter(SemanticSearchProfile.is_default == True, SemanticSearchProfile.enabled == True).first()

    @staticmethod
    def _base_query(db: Session, database_id: int | None):
        query = db.query(Patent).filter(Patent.title != "待补全")
        return query.filter(in_database(database_id)) if database_id is not None else query

    @classmethod
    def query(cls, db: Session, *, text: str, database_id: int | None, mode: str, top_k: int, profile_id: int | None, include_explain: bool = False, index_override: SemanticIndex | None = None) -> dict:
        started = time.perf_counter()
        text = text.strip()
        if not text:
            raise SemanticError("SEMANTIC_QUERY_TOO_LONG", "Search query must not be empty")
        if len(text) > 2000:
            raise SemanticError("SEMANTIC_QUERY_TOO_LONG", "Search query is too long")
        if mode not in {"keyword", "semantic", "hybrid"}:
            raise SemanticError("BAD_REQUEST", "Unsupported semantic search mode")
        profile = cls._profile(db, profile_id)
        if profile_id is not None and not profile:
            raise SemanticError("SEMANTIC_PROFILE_NOT_FOUND", "Semantic search profile not found")
        if profile and not profile.enabled:
            raise SemanticError("SEMANTIC_PROVIDER_DISABLED", "Semantic search profile is disabled")

        timings: dict[str, int] = {}
        exact_started = time.perf_counter()
        scope = cls._base_query(db, database_id)
        exact_rows = scope.filter(or_(Patent.publication_number == text, Patent.application_number == text, Patent.grant_number == text)).all()
        if not exact_rows:
            identity_ids = [row.patent_id for row in db.query(PatentIdentifier).filter(PatentIdentifier.normalized_value == text).all()]
            if identity_ids:
                exact_rows = scope.filter(Patent.id.in_(identity_ids)).all()
        exact_ids = [row.id for row in exact_rows]
        timings["exact"] = int((time.perf_counter() - exact_started) * 1000)

        keyword_ids: list[int] = []
        if mode in {"keyword", "hybrid"}:
            keyword_started = time.perf_counter()
            term = f"%{text}%"
            candidate_limit = profile.keyword_candidate_count if profile else 100
            sparse_ids = sparse_search(db, text, candidate_limit)
            rows = scope.filter(or_(*(getattr(Patent, field).cast(String).ilike(term) for field in KEYWORD_FIELDS))).limit(candidate_limit).all()
            like_ids = [row.id for row in rows]
            keyword_ids = list(dict.fromkeys(sparse_ids + like_ids))[:candidate_limit]
            timings["keyword"] = int((time.perf_counter() - keyword_started) * 1000)

        vector_ids: list[int] = []
        vector_matches: dict[int, dict] = {}
        degraded: list[str] = []
        index = None
        if mode in {"semantic", "hybrid"}:
            vector_started = time.perf_counter()
            index = index_override or (SemanticIndexService.get_active_index(db, profile.id, database_id) if profile else None)
            if not profile or not index:
                degraded.append("SEMANTIC_INDEX_NOT_READY")
            else:
                try:
                    provider = SemanticIndexService._provider(db, profile)
                    vector = provider.embed_query(text)
                    store = open_vector_store(profile.vector_backend, Path(index.path), profile.embedding_dimensions)
                    try:
                        matches = store.dense_search(vector, profile.vector_candidate_count)
                    finally:
                        close = getattr(store, "close", None)
                        if close:
                            close()
                    # Scope is applied again below through authoritative SQLite rehydration.
                    best_matches: dict[int, dict] = {}
                    for item in matches:
                        patent_id = item["patent_id"]
                        if patent_id not in best_matches or item.get("score", 0) > best_matches[patent_id].get("score", 0):
                            best_matches[patent_id] = item
                    vector_matches = best_matches
                    vector_ids = [item["patent_id"] for item in sorted(best_matches.values(), key=lambda value: (-value.get("score", 0), value["patent_id"]))]
                except SemanticError as exc:
                    degraded.append(exc.code)
            timings["vector"] = int((time.perf_counter() - vector_started) * 1000)

        # A provider/index failure must preserve exact and keyword recall even
        # for an explicitly semantic request; the response marks the fallback.
        fallback_keyword_ids = keyword_ids
        if mode == "semantic" and not vector_ids and degraded and not fallback_keyword_ids:
            term = f"%{text}%"
            fallback_keyword_ids = list(dict.fromkeys(sparse_search(db, text, 100) + [row.id for row in scope.filter(or_(*(getattr(Patent, field).cast(String).ilike(term) for field in KEYWORD_FIELDS))).limit(100).all()]))[:100]
        scores = weighted_rrf([
            (1000.0, exact_ids),
            ((profile.keyword_weight if profile else 1), fallback_keyword_ids),
            ((profile.vector_weight if profile else 1), vector_ids),
        ], profile.rrf_k if profile else 60)
        candidate_ids = [patent_id for patent_id, _ in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))]
        if fallback_keyword_ids is not keyword_ids:
            keyword_ids = fallback_keyword_ids

        # Authoritative rehydration is the second scope check; the index never owns visibility.
        rows = cls._base_query(db, database_id).filter(Patent.id.in_(candidate_ids)).all() if candidate_ids else []
        by_id = {row.id: row for row in rows}
        rerank_scores: dict[int, float] = {}
        reranked = False
        if profile and profile.rerank_enabled and candidate_ids:
            try:
                rerank_documents = []
                for patent_id in candidate_ids:
                    patent = by_id.get(patent_id)
                    if not patent:
                        continue
                    document = SemanticDocumentBuilder.build_summary(patent, profile.remote_field_allowlist or profile.indexed_field_allowlist or [])
                    rerank_documents.append(RerankDocument(document.document_id, patent_id, document.text))
                rerank_provider = SemanticIndexService._rerank_provider(db, profile)
                rerank_results = rerank_provider.rerank(text, rerank_documents, min(profile.rerank_top_n, len(rerank_documents)))
                rerank_ids = [item.patent_id for item in rerank_results]
                if len(set(rerank_ids)) != len(rerank_ids) or any(patent_id not in by_id for patent_id in rerank_ids):
                    raise SemanticError("SEMANTIC_RERANK_INVALID_RESPONSE", "Rerank provider returned an unknown patent")
                rerank_scores = {item.patent_id: item.score for item in rerank_results}
                remaining = [patent_id for patent_id in candidate_ids if patent_id not in rerank_ids]
                candidate_ids = rerank_ids + remaining
                exact_set = set(exact_ids)
                candidate_ids = [patent_id for patent_id in candidate_ids if patent_id in exact_set] + [
                    patent_id for patent_id in candidate_ids if patent_id not in exact_set
                ]
                reranked = True
            except SemanticError as exc:
                degraded.append(exc.code)
        results = []
        for patent_id in candidate_ids:
            patent = by_id.get(patent_id)
            if not patent:
                continue
            item = {"patent": {"id": patent.id, "title": patent.title, "publication_number": patent.publication_number,
                "application_number": patent.application_number, "grant_number": patent.grant_number, "abstract": patent.abstract,
                "applicant": patent.applicant, "legal_status": str(patent.legal_status.value if hasattr(patent.legal_status, "value") else patent.legal_status)},
                "scores": {"exact": patent_id in exact_ids, "keyword_rank": keyword_ids.index(patent_id) + 1 if patent_id in keyword_ids else None,
                    "vector_rank": vector_ids.index(patent_id) + 1 if patent_id in vector_ids else None,
                    "rerank_score": rerank_scores.get(patent_id)}, "matches": []}
            if include_explain:
                item["scores"]["fusion_score"] = weighted_rrf([(1000.0, exact_ids), ((profile.keyword_weight if profile else 1), keyword_ids), ((profile.vector_weight if profile else 1), vector_ids)], profile.rrf_k if profile else 60).get(patent_id, 0)
                if patent_id in vector_matches:
                    item["matches"].append({"document_type": "patent_summary", "snippet": vector_matches[patent_id]["text"][:300]})
            results.append(item)
            if len(results) >= top_k:
                break
        timings["total"] = int((time.perf_counter() - started) * 1000)
        db.add(SemanticSearchLog(query_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(), database_id=database_id,
            profile_id=profile.id if profile else None, index_version=index.index_version if index else None, mode=mode,
            degraded_reasons=degraded, candidate_count=len(candidate_ids), result_count=len(results), latency_ms=timings))
        db.commit()
        return {"items": results, "meta": {"mode": mode, "profile_id": profile.id if profile else None,
            "index_version": index.index_version if index else None, "reranked": reranked, "degraded": bool(degraded), "degraded_reasons": degraded, "latency_ms": timings}}
