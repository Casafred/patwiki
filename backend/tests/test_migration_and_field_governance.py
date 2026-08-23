import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.database import Base
import app.models  # noqa: F401 - imported for model registration side effects
from app.services.field_governance_service import governance_summary, seed_registry_baseline
from app.services.import_service import ImportService
from app.services.migration_service import (
    MigrationError,
    SchemaOperation,
    get_integrity_report,
    run_pending_migrations,
)


class MigrationAndFieldGovernanceTest(unittest.TestCase):
    def _engine(self, path: Path):
        return create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False},
        )

    def test_empty_database_migrates_repeats_and_enables_foreign_keys(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine = self._engine(root / "empty.db")
            try:
                first = run_pending_migrations(engine, backup_dir=root / "backups", operator="test")
                second = run_pending_migrations(engine, backup_dir=root / "backups", operator="test")
                report = get_integrity_report(engine)
                self.assertEqual(first["status"], "completed")
                self.assertEqual(second["status"], "noop")
                self.assertEqual(first["integrity_after"], "ok")
                self.assertEqual(report["integrity"], "ok")
                self.assertTrue(report["foreign_keys"])
            finally:
                engine.dispose()

    def test_completed_version_rejects_checksum_drift(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine = self._engine(root / "checksum.db")
            operation = SchemaOperation(
                operation_id="test:stable",
                kind="column",
                table="patents",
                name="stable_probe",
                sql="ALTER TABLE patents ADD COLUMN stable_probe TEXT",
            )
            try:
                run_pending_migrations(
                    engine,
                    backup_dir=root / "backups",
                    operations=(operation,),
                    migration_version="test-checksum",
                    operator="test",
                )
                changed_operation = SchemaOperation(
                    operation_id="test:changed",
                    kind="column",
                    table="patents",
                    name="stable_probe",
                    sql="ALTER TABLE patents ADD COLUMN stable_probe INTEGER",
                )
                with self.assertRaisesRegex(MigrationError, "checksum drift"):
                    run_pending_migrations(
                        engine,
                        backup_dir=root / "backups",
                        operations=(changed_operation,),
                        migration_version="test-checksum",
                        operator="test",
                    )
            finally:
                engine.dispose()

    def test_failed_existing_database_is_restored_and_failure_is_queryable(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database_path = root / "legacy.db"
            raw = sqlite3.connect(database_path)
            raw.execute("CREATE TABLE legacy_probe (id INTEGER PRIMARY KEY, value TEXT)")
            raw.execute("INSERT INTO legacy_probe(value) VALUES ('keep')")
            raw.commit()
            raw.close()

            engine = self._engine(database_path)
            failing_operation = SchemaOperation(
                operation_id="test:forced-failure",
                kind="column",
                table="patents",
                name="forced_failure",
                sql="ALTER TABLE patents DOES_NOT_EXIST",
            )
            try:
                with self.assertRaises(MigrationError) as raised:
                    run_pending_migrations(
                        engine,
                        backup_dir=root / "backups",
                        operations=(failing_operation,),
                        migration_version="test-failure",
                        operator="test",
                    )
                self.assertEqual(raised.exception.report["status"], "restored")
                with engine.connect() as connection:
                    self.assertEqual(
                        connection.execute(text("SELECT value FROM legacy_probe")).scalar(),
                        "keep",
                    )
                    self.assertEqual(
                        connection.execute(text(
                            "SELECT COUNT(*) FROM sqlite_master "
                            "WHERE type = 'table' AND name = 'patents'"
                        )).scalar(),
                        0,
                    )
                    statuses = connection.execute(text(
                        "SELECT status FROM migration_runs "
                        "WHERE migration_version = 'test-failure'"
                    )).scalars().all()
                    self.assertEqual(statuses, ["restored"])
                    self.assertEqual(connection.execute(text("PRAGMA foreign_keys")).scalar(), 1)
                self.assertEqual(len(list((root / "backups").glob("*.db"))), 1)
            finally:
                engine.dispose()

    def test_field_governance_baseline_is_complete_and_idempotent(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine = self._engine(root / "governance.db")
            try:
                run_pending_migrations(engine, backup_dir=root / "backups", operator="test")
                db = Session(engine)
                try:
                    first = seed_registry_baseline(db)
                    second = seed_registry_baseline(db)
                    summary = governance_summary(db)
                    self.assertTrue(first["seeded"])
                    self.assertFalse(second["seeded"])
                    self.assertEqual(summary["source_table_count"], 31)
                    self.assertEqual(summary["canonical_field_count"], 140)
                    self.assertEqual(summary["source_mapping_count"], 357)
                    self.assertEqual(
                        summary["mapping_status_counts"]["mapped"],
                        84,
                    )

                    mapping, issues = ImportService.suggest_mapping(
                        ["公开号", "产品品类", "完全未知列"],
                        db,
                    )
                    self.assertEqual(mapping["公开号"], "publication_number")
                    self.assertEqual(mapping["产品品类"], "")
                    self.assertEqual(mapping["完全未知列"], "")
                    self.assertEqual(issues, [])
                finally:
                    db.close()
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
