"""Versioned, recoverable SQLite schema migration service.

The application is local-first, so a migration must be understandable and
recoverable on the user's actual database file.  This service intentionally
keeps the compatibility operations explicit instead of hiding them behind a
best-effort ``ALTER TABLE`` loop.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import getpass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterable, Sequence

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database import Base
from app.models.system import MigrationIssue, MigrationRun


CURRENT_MIGRATION_VERSION = "2026-08-23.0"
KEY_TABLES = (
    "patents",
    "patent_identifiers",
    "import_batches",
    "import_source_rows",
    "field_observations",
    "governance_decisions",
    "source_table_definitions",
    "field_definitions",
    "source_field_mappings",
)


@dataclass(frozen=True)
class SchemaOperation:
    operation_id: str
    kind: str
    table: str
    name: str
    sql: str


def _column(table: str, name: str, sql: str) -> SchemaOperation:
    return SchemaOperation(f"column:{table}.{name}", "column", table, name, sql)


def _index(table: str, name: str, column: str) -> SchemaOperation:
    return SchemaOperation(
        f"index:{table}.{name}",
        "index",
        table,
        name,
        f"CREATE INDEX {name} ON {table} ({column})",
    )


# Compatibility changes that were previously hidden in database.py.  New
# tables and model-defined indexes are handled by Base.metadata.create_all;
# these entries cover columns/indexes that create_all cannot add to an old DB.
SCHEMA_OPERATIONS: tuple[SchemaOperation, ...] = (
    _column("patents", "database_id", "ALTER TABLE patents ADD COLUMN database_id INTEGER REFERENCES patent_databases(id)"),
    _column("field_definitions", "source_timestamp", "ALTER TABLE field_definitions ADD COLUMN source_timestamp DATETIME"),
    _column("patent_projects", "relation_type", "ALTER TABLE patent_projects ADD COLUMN relation_type VARCHAR(20)"),
    _column("patent_projects", "risk_level", "ALTER TABLE patent_projects ADD COLUMN risk_level VARCHAR(20)"),
    _column("patent_projects", "document_role", "ALTER TABLE patent_projects ADD COLUMN document_role VARCHAR(50)"),
    _column("patent_projects", "relevance_score", "ALTER TABLE patent_projects ADD COLUMN relevance_score INTEGER"),
    _column("patent_projects", "importance", "ALTER TABLE patent_projects ADD COLUMN importance VARCHAR(20)"),
    _column("patent_projects", "assigned_to_id", "ALTER TABLE patent_projects ADD COLUMN assigned_to_id INTEGER REFERENCES people(id)"),
    _column("patent_projects", "linked_at", "ALTER TABLE patent_projects ADD COLUMN linked_at DATETIME"),
    _column("patent_databases", "owner_id", "ALTER TABLE patent_databases ADD COLUMN owner_id INTEGER REFERENCES users(id)"),
    _column("patent_histories", "source_view_id", "ALTER TABLE patent_histories ADD COLUMN source_view_id INTEGER REFERENCES patent_views(id)"),
    _column("patent_histories", "source_view_name", "ALTER TABLE patent_histories ADD COLUMN source_view_name VARCHAR(200)"),
    _column("patent_views", "layout_type", "ALTER TABLE patent_views ADD COLUMN layout_type VARCHAR(30) DEFAULT 'table'"),
    _column("patent_views", "group_by_config", "ALTER TABLE patent_views ADD COLUMN group_by_config JSON"),
    _column("patent_views", "conditional_formatting", "ALTER TABLE patent_views ADD COLUMN conditional_formatting JSON"),
    _column("patent_views", "kanban_config", "ALTER TABLE patent_views ADD COLUMN kanban_config JSON"),
    _column("patent_views", "form_config", "ALTER TABLE patent_views ADD COLUMN form_config JSON"),
    _column("patent_views", "gantt_config", "ALTER TABLE patent_views ADD COLUMN gantt_config JSON"),
    _column("patent_views", "template_key", "ALTER TABLE patent_views ADD COLUMN template_key VARCHAR(100)"),
    _column("custom_fields", "link_config", "ALTER TABLE custom_fields ADD COLUMN link_config JSON"),
    _column("custom_fields", "lookup_config", "ALTER TABLE custom_fields ADD COLUMN lookup_config JSON"),
    _column("custom_fields", "rollup_config", "ALTER TABLE custom_fields ADD COLUMN rollup_config JSON"),
    _column("custom_fields", "formula_config", "ALTER TABLE custom_fields ADD COLUMN formula_config JSON"),
    _column("patents", "view_id", "ALTER TABLE patents ADD COLUMN view_id INTEGER REFERENCES patent_views(id)"),
    _column("people", "user_id", "ALTER TABLE people ADD COLUMN user_id INTEGER REFERENCES users(id)"),
    _column("users", "department_id", "ALTER TABLE users ADD COLUMN department_id INTEGER REFERENCES departments(id)"),
    _column("users", "employee_no", "ALTER TABLE users ADD COLUMN employee_no VARCHAR(50)"),
    _column("users", "group_id", "ALTER TABLE users ADD COLUMN group_id INTEGER REFERENCES departments(id)"),
    _column("users", "product_line_id", "ALTER TABLE users ADD COLUMN product_line_id INTEGER REFERENCES product_lines(id)"),
    _column("users", "organization_role", "ALTER TABLE users ADD COLUMN organization_role VARCHAR(100)"),
    _column("departments", "code", "ALTER TABLE departments ADD COLUMN code VARCHAR(50)"),
    _column("departments", "department_type", "ALTER TABLE departments ADD COLUMN department_type VARCHAR(30) DEFAULT 'other'"),
    _column("departments", "parent_id", "ALTER TABLE departments ADD COLUMN parent_id INTEGER REFERENCES departments(id)"),
    _column("product_lines", "department_id", "ALTER TABLE product_lines ADD COLUMN department_id INTEGER REFERENCES departments(id)"),
    _column("import_batches", "source_table_title", "ALTER TABLE import_batches ADD COLUMN source_table_title VARCHAR(500)"),
    _column("import_batches", "worksheet_name", "ALTER TABLE import_batches ADD COLUMN worksheet_name VARCHAR(200)"),
    _column("import_batches", "source_system", "ALTER TABLE import_batches ADD COLUMN source_system VARCHAR(200)"),
    _column("import_batches", "mapping_version", "ALTER TABLE import_batches ADD COLUMN mapping_version VARCHAR(100)"),
    _column("import_batches", "file_hash", "ALTER TABLE import_batches ADD COLUMN file_hash VARCHAR(128)"),
    _column("import_batches", "artifact_path", "ALTER TABLE import_batches ADD COLUMN artifact_path VARCHAR(1000)"),
    _column("patent_histories", "import_batch_id", "ALTER TABLE patent_histories ADD COLUMN import_batch_id INTEGER REFERENCES import_batches(id)"),
    _column("patent_histories", "source_table_title", "ALTER TABLE patent_histories ADD COLUMN source_table_title VARCHAR(500)"),
    _column("patent_histories", "source_row", "ALTER TABLE patent_histories ADD COLUMN source_row INTEGER"),
    _column("patent_histories", "source_field_name", "ALTER TABLE patent_histories ADD COLUMN source_field_name VARCHAR(500)"),
    _column("import_source_rows", "candidate_patent_ids", "ALTER TABLE import_source_rows ADD COLUMN candidate_patent_ids JSON"),
    _column("governance_decisions", "mapping_version", "ALTER TABLE governance_decisions ADD COLUMN mapping_version VARCHAR(100)"),
    _column("governance_decisions", "decision_batch_id", "ALTER TABLE governance_decisions ADD COLUMN decision_batch_id VARCHAR(64)"),
    _column("governance_decisions", "before_field_resolution", "ALTER TABLE governance_decisions ADD COLUMN before_field_resolution VARCHAR(30)"),
    _column("governance_decisions", "before_final_decision", "ALTER TABLE governance_decisions ADD COLUMN before_final_decision VARCHAR(30)"),
    _column("governance_decisions", "before_proposed_action", "ALTER TABLE governance_decisions ADD COLUMN before_proposed_action VARCHAR(30)"),
    _column("governance_decisions", "before_canonical_field_key", "ALTER TABLE governance_decisions ADD COLUMN before_canonical_field_key VARCHAR(200)"),
    _column("governance_decisions", "before_decided_by", "ALTER TABLE governance_decisions ADD COLUMN before_decided_by VARCHAR(100)"),
    _column("governance_decisions", "before_decided_at", "ALTER TABLE governance_decisions ADD COLUMN before_decided_at DATETIME"),
    _column("governance_decisions", "patent_id", "ALTER TABLE governance_decisions ADD COLUMN patent_id INTEGER"),
    _column("governance_decisions", "patent_field_key", "ALTER TABLE governance_decisions ADD COLUMN patent_field_key VARCHAR(200)"),
    _column("governance_decisions", "patent_value_before", "ALTER TABLE governance_decisions ADD COLUMN patent_value_before TEXT"),
    _column("governance_decisions", "patent_value_after", "ALTER TABLE governance_decisions ADD COLUMN patent_value_after TEXT"),
    _column("governance_decisions", "patent_value_changed", "ALTER TABLE governance_decisions ADD COLUMN patent_value_changed BOOLEAN DEFAULT 0"),
    _index("patents", "ix_patents_database_id", "database_id"),
    _index("patent_databases", "ix_patent_databases_owner_id", "owner_id"),
    _index("patent_histories", "ix_patent_histories_source_view_id", "source_view_id"),
    _index("patents", "ix_patents_view_id", "view_id"),
    _index("people", "ix_people_user_id", "user_id"),
    _index("users", "ix_users_department_id", "department_id"),
    _index("users", "ix_users_employee_no", "employee_no"),
    _index("users", "ix_users_group_id", "group_id"),
    _index("users", "ix_users_product_line_id", "product_line_id"),
    _index("departments", "ix_departments_parent_id", "parent_id"),
    _index("product_lines", "ix_product_lines_department_id", "department_id"),
    _index("import_batches", "ix_import_batches_file_hash", "file_hash"),
    _index("patent_histories", "ix_patent_histories_import_batch_id", "import_batch_id"),
    _index("governance_decisions", "ix_governance_decisions_decision_batch_id", "decision_batch_id"),
    _index("governance_decisions", "ix_governance_decisions_patent_id", "patent_id"),
    _index("governance_reversals", "ix_governance_reversals_decision_batch_id", "decision_batch_id"),
)


class MigrationError(RuntimeError):
    """Raised when startup cannot safely complete a migration."""

    def __init__(self, message: str, report: dict | None = None):
        super().__init__(message)
        self.report = report or {}


def migration_checksum(operations: Sequence[SchemaOperation] = SCHEMA_OPERATIONS) -> str:
    payload = [asdict(operation) for operation in operations]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _sqlite_path(bind: Engine) -> Path | None:
    if bind.dialect.name != "sqlite":
        return None
    database = bind.url.database
    if not database or database == ":memory:":
        return None
    return Path(database).resolve()


def _enable_foreign_keys(bind: Engine) -> None:
    """Set the pragma immediately as well as on future pooled connections."""
    if bind.dialect.name != "sqlite":
        return
    raw_connection = bind.raw_connection()
    try:
        cursor = raw_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
    finally:
        raw_connection.close()


def _has_schema_gaps(bind: Engine, operations: Iterable[SchemaOperation]) -> bool:
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if any(table_name not in tables for table_name in Base.metadata.tables):
        return True
    for operation in operations:
        if operation.table not in tables:
            return True
        if operation.kind == "column":
            columns = {item["name"] for item in inspector.get_columns(operation.table)}
            if operation.name not in columns:
                return True
        elif operation.kind == "index":
            indexes = {item["name"] for item in inspector.get_indexes(operation.table)}
            if operation.name not in indexes:
                return True
    return False


def _integrity_check(bind: Engine) -> str:
    with bind.connect() as connection:
        result = connection.execute(text("PRAGMA integrity_check")).scalar()
    value = str(result or "unknown")
    if value.lower() != "ok":
        raise MigrationError(f"SQLite integrity_check failed: {value}")
    return value


def _table_counts(bind: Engine) -> dict[str, int]:
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    counts: dict[str, int] = {}
    with bind.connect() as connection:
        for table_name in KEY_TABLES:
            if table_name in tables:
                counts[table_name] = int(connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)
    return counts


def _ensure_ledger_tables(bind: Engine) -> None:
    MigrationRun.__table__.create(bind=bind, checkfirst=True)
    MigrationIssue.__table__.create(bind=bind, checkfirst=True)


def _backup_database(bind: Engine, backup_dir: Path, version: str) -> Path | None:
    source_path = _sqlite_path(bind)
    if source_path is None or not source_path.exists() or source_path.stat().st_size == 0:
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"patwiki-migration-{version}-{stamp}.db"
    bind.dispose()
    source = sqlite3.connect(str(source_path))
    target = sqlite3.connect(str(backup_path))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup_path


def _restore_database(bind: Engine, backup_path: Path) -> None:
    database_path = _sqlite_path(bind)
    if database_path is None:
        raise RuntimeError("SQLite backup restore requires a file-backed database")
    bind.dispose()
    source = sqlite3.connect(str(backup_path))
    target = sqlite3.connect(str(database_path))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def _record_start(bind: Engine, version: str, checksum: str, operator: str, backup_path: Path | None) -> int:
    factory = sessionmaker(bind=bind)
    db = factory()
    try:
        run = MigrationRun(
            migration_version=version,
            checksum=checksum,
            app_version=settings.APP_VERSION,
            operator=operator,
            status="started",
            backup_path=str(backup_path) if backup_path else None,
        )
        db.add(run)
        db.commit()
        return run.id
    finally:
        db.close()


def _record_restored_failure(
    bind: Engine,
    version: str,
    checksum: str,
    operator: str,
    backup_path: Path | None,
    error: str,
    counts_before: dict[str, int],
    integrity_before: str,
) -> int:
    _ensure_ledger_tables(bind)
    factory = sessionmaker(bind=bind)
    db = factory()
    try:
        run = MigrationRun(
            migration_version=version,
            checksum=checksum,
            app_version=settings.APP_VERSION,
            operator=operator,
            status="restored" if backup_path else "failed",
            backup_path=str(backup_path) if backup_path else None,
            integrity_before=integrity_before,
            table_counts_before=counts_before,
            error=error,
            completed_at=datetime.utcnow(),
        )
        db.add(run)
        db.flush()
        db.add(MigrationIssue(
            migration_run_id=run.id,
            entity="database",
            issue_type="migration_failure",
            detail=error,
        ))
        db.commit()
        return run.id
    finally:
        db.close()


def _apply_operations(bind: Engine, operations: Iterable[SchemaOperation]) -> None:
    with bind.begin() as connection:
        for operation in operations:
            inspector = inspect(connection)
            if operation.table not in inspector.get_table_names():
                raise RuntimeError(f"migration target table does not exist: {operation.table}")
            if operation.kind == "column":
                columns = {item["name"] for item in inspector.get_columns(operation.table)}
                if operation.name in columns:
                    continue
            elif operation.kind == "index":
                indexes = {item["name"] for item in inspector.get_indexes(operation.table)}
                if operation.name in indexes:
                    continue
            else:
                raise RuntimeError(f"unsupported migration operation: {operation.kind}")
            connection.execute(text(operation.sql))


def _run_noop(bind: Engine, version: str, expected_checksum: str) -> dict:
    with bind.connect() as connection:
        run = connection.execute(text(
            "SELECT migration_version, checksum, status, completed_at "
            "FROM migration_runs WHERE migration_version = :version "
            "AND status = 'completed' ORDER BY id DESC LIMIT 1"
        ), {"version": version}).mappings().first()
    if run and run["checksum"] != expected_checksum:
        raise MigrationError(
            "Migration checksum drift detected for completed version "
            f"{version}: stored={run['checksum']} expected={expected_checksum}",
            {
                "status": "checksum_mismatch",
                "migration_version": version,
                "stored_checksum": run["checksum"],
                "expected_checksum": expected_checksum,
            },
        )
    return {
        "status": "noop",
        "migration_version": version,
        "checksum": expected_checksum,
        "last_completed": dict(run) if run else None,
    }


def run_pending_migrations(
    bind: Engine,
    *,
    backup_dir: Path | None = None,
    operations: Sequence[SchemaOperation] = SCHEMA_OPERATIONS,
    migration_version: str = CURRENT_MIGRATION_VERSION,
    operator: str | None = None,
) -> dict:
    """Run the current schema migration and return an auditable report.

    ``Base.metadata.create_all`` is intentionally inside the guarded operation
    after the backup and ledger start record.  SQLAlchemy uses it only for new
    tables; all compatibility changes remain explicit and fail loudly.
    """
    if bind.dialect.name != "sqlite":
        raise MigrationError("PatWiki migration safety platform currently supports SQLite only")

    _enable_foreign_keys(bind)
    checksum = migration_checksum(operations)
    operator = operator or os.environ.get("PATWIKI_MIGRATION_OPERATOR") or getpass.getuser()
    backup_dir = backup_dir or settings.BACKUPS_DIR
    has_gaps = _has_schema_gaps(bind, operations)

    # An old database may not have the ledger table yet, so inspect before
    # querying it.  A completed ledger run plus no schema gaps is a true no-op.
    tables = set(inspect(bind).get_table_names())
    completed_current_version = False
    if "migration_runs" in tables:
        with bind.connect() as connection:
            completed_current_version = bool(connection.execute(text(
                "SELECT 1 FROM migration_runs WHERE migration_version = :version "
                "AND status = 'completed' LIMIT 1"
            ), {"version": migration_version}).scalar())
    if not has_gaps and completed_current_version:
        return _run_noop(bind, migration_version, checksum)

    integrity_before = _integrity_check(bind)
    counts_before = _table_counts(bind)
    # A new version can contain data work even when the compatibility schema is
    # already complete, so every not-yet-completed version gets a backup.
    backup_required = has_gaps or not completed_current_version
    backup_path = _backup_database(bind, backup_dir, migration_version) if backup_required else None
    run_id = None
    try:
        _ensure_ledger_tables(bind)
        run_id = _record_start(bind, migration_version, checksum, operator, backup_path)

        Base.metadata.create_all(bind=bind)
        _apply_operations(bind, operations)
        integrity_after = _integrity_check(bind)
        counts_after = _table_counts(bind)

        db = sessionmaker(bind=bind)()
        try:
            run = db.query(MigrationRun).filter(MigrationRun.id == run_id).one()
            run.status = "completed"
            run.integrity_before = integrity_before
            run.integrity_after = integrity_after
            run.table_counts_before = counts_before
            run.table_counts_after = counts_after
            run.completed_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()
        return {
            "status": "completed",
            "migration_version": migration_version,
            "checksum": checksum,
            "backup_path": str(backup_path) if backup_path else None,
            "integrity_before": integrity_before,
            "integrity_after": integrity_after,
            "table_counts_before": counts_before,
            "table_counts_after": counts_after,
            "run_id": run_id,
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        restored = False
        if backup_path:
            try:
                _restore_database(bind, backup_path)
                _enable_foreign_keys(bind)
                restored = True
            except Exception as restore_exc:
                error = f"{error}; restore failed: {type(restore_exc).__name__}: {restore_exc}"
        try:
            failure_run_id = _record_restored_failure(
                bind,
                migration_version,
                checksum,
                operator,
                backup_path,
                error,
                counts_before,
                integrity_before,
            )
        except Exception as record_exc:
            error = f"{error}; failure record failed: {type(record_exc).__name__}: {record_exc}"
            failure_run_id = None
        report = {
            "status": "restored" if restored else "failed",
            "migration_version": migration_version,
            "checksum": checksum,
            "backup_path": str(backup_path) if backup_path else None,
            "run_id": failure_run_id or run_id,
            "error": error,
        }
        raise MigrationError(f"PatWiki database migration failed: {error}", report) from exc


def list_migration_runs(db: Session, limit: int = 50) -> list[dict]:
    rows = db.query(MigrationRun).order_by(MigrationRun.id.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "migration_version": row.migration_version,
            "checksum": row.checksum,
            "app_version": row.app_version,
            "operator": row.operator,
            "status": row.status,
            "backup_path": row.backup_path,
            "integrity_before": row.integrity_before,
            "integrity_after": row.integrity_after,
            "table_counts_before": row.table_counts_before,
            "table_counts_after": row.table_counts_after,
            "error": row.error,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }
        for row in rows
    ]


def get_integrity_report(bind: Engine) -> dict:
    _enable_foreign_keys(bind)
    with bind.connect() as connection:
        foreign_keys = bool(connection.execute(text("PRAGMA foreign_keys")).scalar())
    return {
        "database": str(_sqlite_path(bind) or bind.url),
        "integrity": _integrity_check(bind),
        "table_counts": _table_counts(bind),
        "foreign_keys": foreign_keys,
    }
