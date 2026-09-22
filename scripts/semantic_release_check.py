"""Read-only semantic-search release readiness and optional benchmark check."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.models import (  # noqa: E402
    SemanticDocumentState,
    SemanticEvaluationRun,
    SemanticIndex,
    SemanticIndexJob,
    SemanticIndexOutbox,
    SemanticProviderDefinition,
)
from app.services.migration_service import CURRENT_MIGRATION_VERSION  # noqa: E402
from app.services.semantic_search_service import SemanticSearchService  # noqa: E402


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = max(0, math.ceil(len(ordered) * ratio) - 1)
    return round(ordered[position], 2)


def run_benchmark(db: Session, path: Path) -> dict:
    samples: list[float] = []
    labeled = 0
    hits = 0
    errors: list[str] = []
    total = 0
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        total += 1
        try:
            case = json.loads(raw_line)
            query = str(case["query"])
            expected = {int(value) for value in case.get("relevant_patent_ids", [])}
            started = time.perf_counter()
            result = SemanticSearchService.query(
                db,
                text=query,
                database_id=case.get("database_id"),
                mode=case.get("mode", "keyword"),
                top_k=int(case.get("top_k", 10)),
                profile_id=case.get("profile_id"),
            )
            samples.append((time.perf_counter() - started) * 1000)
            if expected:
                labeled += 1
                result_ids = {item["patent"]["id"] for item in result["items"]}
                if result_ids & expected:
                    hits += 1
        except Exception as exc:  # Report the line and keep checking the rest.
            errors.append(f"line {line_number}: {type(exc).__name__}: {exc}")
    db.rollback()
    return {
        "status": "completed" if not errors else "completed_with_errors",
        "case_count": total,
        "labeled_case_count": labeled,
        "recall_at_k": round(hits / labeled, 4) if labeled else None,
        "p50_latency_ms": percentile(samples, 0.50),
        "p95_latency_ms": percentile(samples, 0.95),
        "errors": errors,
        "evaluation_note": "No labeled cases were supplied; quality metrics are not run." if not labeled else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=settings.DATABASE_PATH)
    parser.add_argument("--benchmark", type=Path, help="JSONL file with query and optional relevant_patent_ids")
    args = parser.parse_args()
    database_path = args.database.resolve()
    report: dict = {
        "database": str(database_path),
        "migration": {"expected_version": CURRENT_MIGRATION_VERSION},
        "blocking_issues": [],
        "warnings": [],
    }
    if not database_path.exists():
        report["blocking_issues"].append(f"Database does not exist: {database_path}")
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 1

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    required_tables = {
        "migration_runs",
        "patents",
        "semantic_provider_definitions",
        "semantic_search_profiles",
        "semantic_indexes",
        "semantic_index_jobs",
        "semantic_document_states",
        "semantic_index_outbox",
        "semantic_evaluation_runs",
    }
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing_tables = sorted(required_tables - tables)
    report["schema"] = {"missing_tables": missing_tables, "ok": not missing_tables}
    if missing_tables:
        report["blocking_issues"].append(f"Missing required tables: {', '.join(missing_tables)}")

    with engine.connect() as connection:
        integrity = str(connection.execute(text("PRAGMA integrity_check")).scalar() or "unknown")
        migration_row = None
        if "migration_runs" in tables:
            migration_row = connection.execute(text(
                "SELECT migration_version, status, completed_at FROM migration_runs "
                "WHERE migration_version = :version AND status = 'completed' "
                "ORDER BY id DESC LIMIT 1"
            ), {"version": CURRENT_MIGRATION_VERSION}).mappings().first()
        fts_enabled = bool(connection.execute(text("SELECT sqlite_compileoption_used('ENABLE_FTS5')")).scalar())
        fts_table = bool(connection.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'semantic_patent_fts_v2'"
        )).scalar())
    report["integrity"] = {"status": integrity, "ok": integrity.lower() == "ok"}
    report["migration"].update({"completed": dict(migration_row) if migration_row else None})
    report["sparse"] = {"fts5_compiled": fts_enabled, "projection_exists": fts_table}
    if integrity.lower() != "ok":
        report["blocking_issues"].append(f"SQLite integrity check failed: {integrity}")
    if not fts_enabled:
        report["warnings"].append("SQLite was built without FTS5; keyword search will use ILIKE fallback.")
    if not migration_row:
        report["blocking_issues"].append(f"Migration {CURRENT_MIGRATION_VERSION} is not completed.")

    if missing_tables:
        report["ready_for_release"] = False
        report["benchmark"] = {"status": "not_run", "evaluation_note": "Required semantic tables are missing."}
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 1

    with Session(engine) as db:
        providers = db.query(SemanticProviderDefinition).all()
        invalid_credentials = [row.id for row in providers if row.credential_ref and not row.credential_ref.startswith(("env://", "keyring://"))]
        report["providers"] = {
            "count": len(providers),
            "enabled": sum(1 for row in providers if row.enabled),
            "invalid_credential_ref_ids": invalid_credentials,
        }
        if invalid_credentials:
            report["blocking_issues"].append("Plaintext or unsupported provider credentials were found.")

        active_indexes = db.query(SemanticIndex).filter(SemanticIndex.is_active == True).all()
        active_versions = [row.index_version for row in active_indexes]
        state_query = db.query(SemanticDocumentState).filter(SemanticDocumentState.index_version.in_(active_versions)) if active_versions else None
        indexed = state_query.filter(SemanticDocumentState.status == "indexed").count() if state_query else 0
        total = state_query.filter(SemanticDocumentState.status != "deleted").count() if state_query else 0
        report["indexes"] = {
            "active": len(active_indexes),
            "by_status": {status: db.query(SemanticIndex).filter(SemanticIndex.status == status).count() for status in ("building", "validating", "active", "retired", "failed")},
            "coverage_rate": round(indexed / total, 4) if total else 0.0,
            "document_indexed": indexed,
            "document_total": total,
        }
        report["jobs"] = {status: db.query(SemanticIndexJob).filter(SemanticIndexJob.status == status).count() for status in ("pending", "running", "retry_wait", "failed", "dead_letter", "succeeded")}
        report["outbox"] = {status: db.query(SemanticIndexOutbox).filter(SemanticIndexOutbox.status == status).count() for status in ("pending", "claimed", "retry_wait", "dead_letter", "completed")}
        report["evaluation"] = {
            "passed_profiles": db.query(SemanticEvaluationRun.profile_id).filter(SemanticEvaluationRun.status == "passed").distinct().count(),
            "last_passed_at": db.query(SemanticEvaluationRun.completed_at).filter(SemanticEvaluationRun.status == "passed").order_by(SemanticEvaluationRun.completed_at.desc()).first()[0] if db.query(SemanticEvaluationRun).filter(SemanticEvaluationRun.status == "passed").first() else None,
        }
        if report["indexes"]["active"] == 0:
            report["warnings"].append("No active semantic index is configured.")
        if report["evaluation"]["passed_profiles"] == 0:
            report["warnings"].append("No passed labeled evaluation is available; semantic quality is not certified.")
        if args.benchmark:
            report["benchmark"] = run_benchmark(db, args.benchmark.resolve())
        else:
            report["benchmark"] = {"status": "not_run", "evaluation_note": "Provide --benchmark JSONL to run a query benchmark."}

    report["ready_for_release"] = not report["blocking_issues"]
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["ready_for_release"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
