from __future__ import annotations

import math
import time
from sqlalchemy.orm import Session

from app.models import (
    SemanticEvaluationCase,
    SemanticEvaluationDataset,
    SemanticEvaluationResult,
    SemanticEvaluationRun,
    SemanticIndex,
    SemanticSearchProfile,
)
from app.search.contracts import SemanticError
from app.core.time import utc_now_naive
from app.services.semantic_search_service import SemanticSearchService


def _metrics(retrieved: list[int], relevant: set[int], top_k: int) -> dict[str, float | int]:
    ranked = retrieved[:top_k]
    hits = [index for index, patent_id in enumerate(ranked, start=1) if patent_id in relevant]
    hit_count = len(hits)
    reciprocal_rank = 1.0 / hits[0] if hits else 0.0
    dcg = sum(1.0 / math.log2(index + 1) for index in hits)
    ideal_count = min(len(relevant), top_k)
    ideal_dcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_count + 1))
    return {
        "retrieved_count": len(ranked),
        "relevant_count": len(relevant),
        "hit_count": hit_count,
        "precision_at_k": hit_count / top_k if top_k else 0.0,
        "recall_at_k": hit_count / len(relevant) if relevant else 0.0,
        "mrr": reciprocal_rank,
        "ndcg_at_k": dcg / ideal_dcg if ideal_dcg else 0.0,
        "zero_result": int(not ranked),
    }


def _average(results: list[dict[str, float | int]]) -> dict[str, float | int]:
    if not results:
        return {"case_count": 0, "zero_result_rate": 0.0, "precision_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0}
    output: dict[str, float | int] = {"case_count": len(results)}
    for key in ("precision_at_k", "recall_at_k", "mrr", "ndcg_at_k", "zero_result"):
        value = sum(float(item[key]) for item in results) / len(results)
        output["zero_result_rate" if key == "zero_result" else key] = value
    return output


class SemanticEvaluationService:
    @staticmethod
    def dataset_dict(row: SemanticEvaluationDataset, case_count: int | None = None) -> dict:
        return {"id": row.id, "name": row.name, "version": row.version, "description": row.description,
                "enabled": row.enabled, "case_count": case_count, "created_at": row.created_at}

    @staticmethod
    def case_dict(row: SemanticEvaluationCase) -> dict:
        return {"id": row.id, "dataset_id": row.dataset_id, "case_key": row.case_key, "query": row.query,
                "database_id": row.database_id, "relevant_patent_ids": row.relevant_patent_ids or [],
                "notes": row.notes, "enabled": row.enabled, "created_at": row.created_at}

    @staticmethod
    def run_dict(row: SemanticEvaluationRun) -> dict:
        return {"id": row.id, "dataset_id": row.dataset_id, "profile_id": row.profile_id,
                "index_version": row.index_version, "mode": row.mode, "top_k": row.top_k,
                "status": row.status, "metrics": row.metrics_json or {}, "thresholds": row.threshold_json or {},
                "error_code": row.error_code, "error_message": row.error_message,
                "created_at": row.created_at, "completed_at": row.completed_at}

    @classmethod
    def run(cls, db: Session, dataset: SemanticEvaluationDataset, profile: SemanticSearchProfile, mode: str, top_k: int, index: SemanticIndex | None = None) -> SemanticEvaluationRun:
        if mode not in {"keyword", "semantic", "hybrid"}:
            raise SemanticError("BAD_REQUEST", "Unsupported evaluation search mode")
        cases = db.query(SemanticEvaluationCase).filter(SemanticEvaluationCase.dataset_id == dataset.id, SemanticEvaluationCase.enabled == True).order_by(SemanticEvaluationCase.id).all()
        if not cases:
            raise SemanticError("SEMANTIC_EVALUATION_EMPTY", "Evaluation dataset must contain at least one enabled case")
        active = index or db.query(SemanticIndex).filter(SemanticIndex.profile_id == profile.id, SemanticIndex.is_active == True).order_by(SemanticIndex.id.desc()).first()
        run = SemanticEvaluationRun(dataset_id=dataset.id, profile_id=profile.id, index_version=active.index_version if active else None,
            mode=mode, top_k=top_k, status="running", threshold_json=profile.quality_thresholds or {})
        db.add(run)
        db.commit()
        case_metrics: list[dict[str, float | int]] = []
        try:
            for case in cases:
                started = time.perf_counter()
                response = SemanticSearchService.query(db, text=case.query, database_id=case.database_id, mode=mode, top_k=top_k, profile_id=profile.id, index_override=index)
                retrieved = [item["patent"]["id"] for item in response["items"]]
                metrics = _metrics(retrieved, set(case.relevant_patent_ids or []), top_k)
                case_metrics.append(metrics)
                db.add(SemanticEvaluationResult(run_id=run.id, case_id=case.id, retrieved_patent_ids=retrieved,
                    metrics_json=metrics, latency_ms=int((time.perf_counter() - started) * 1000)))
            averages = _average(case_metrics)
            thresholds = profile.quality_thresholds or {}
            passed = all(float(averages.get(key, 0)) >= float(value) for key, value in thresholds.items())
            run.metrics_json = averages
            run.status = "passed" if thresholds and passed else "completed"
            if thresholds and not passed:
                run.status = "failed"
            run.completed_at = utc_now_naive()
            db.commit()
        except Exception as exc:
            run.status, run.error_code, run.error_message, run.completed_at = "failed", getattr(exc, "code", "SEMANTIC_EVALUATION_FAILED"), str(exc), utc_now_naive()
            db.commit()
        return run
