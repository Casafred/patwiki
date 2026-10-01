import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
import app.models
from app.models import Patent, PatentDatabase, PatentHistory, SyncEntityFieldState, SyncPackage, SyncPackageRecord, SyncUidMapping
from app.services import collaboration_sync_service as sync


class CollaborationSyncTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.database = PatentDatabase(name="Sync", code="SYNC")
        self.patent = Patent(database=self.database, entity_uid="pat_local", title="Local", publication_number="CN123456789A")
        self.package = SyncPackage(package_uid="pkg_test", path="unused", file_hash="hash", direction="inbox",
                                   manifest_json={"origin_node_uid": "node_remote", "created_at": "2026-10-01T00:00:00Z"})
        self.db.add_all([self.patent, self.package])
        self.db.flush()
        self.row = SyncPackageRecord(package_id=self.package.id, entity_type="patent", entity_uid="pat_remote",
                                     payload_json={"title": "Remote", "publication_number": "CN123456789A"})
        self.db.add(self.row)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_confirmed_uid_alias_resolves_later_package_without_numbers(self):
        resolved = sync._batch_local_patents(self.db, [self.row], "node_remote")
        self.assertEqual(resolved[self.row.id].id, self.patent.id)
        self.assertEqual(self.db.query(SyncUidMapping).count(), 0)
        sync._save_uid_mapping(self.db, self.package, self.row, self.patent)
        self.db.commit()
        self.row.payload_json = {"title": "Next"}
        self.db.flush()
        resolved = sync._batch_local_patents(self.db, [self.row], "node_remote")
        self.assertEqual(resolved[self.row.id].id, self.patent.id)
        self.assertIsNone(sync._batch_local_patents(self.db, [self.row], "node_other")[self.row.id])

    def test_alias_does_not_hide_number_identity_conflict(self):
        sync._save_uid_mapping(self.db, self.package, self.row, self.patent)
        self.db.add(Patent(title="Other", entity_uid="pat_other", publication_number="CN999999999A"))
        self.row.payload_json = {"title": "Remote", "publication_number": "CN999999999A"}
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            sync._batch_local_patents(self.db, [self.row], "node_remote")
        self.assertEqual(error.exception.status_code, 409)

    def test_lower_row_version_in_newer_package_uses_field_baseline(self):
        sync._save_uid_mapping(self.db, self.package, self.row, self.patent)
        sync._save_baseline(self.db, "node_remote", self.row, "title", "Local", 100, self.package)
        self.db.commit()
        state = self.db.query(SyncEntityFieldState).one()
        self.assertEqual(state.accepted_package_uid, "pkg_test")
        self.assertEqual(state.source_exported_at, datetime(2026, 10, 1))
        self.package.manifest_json = {"origin_node_uid": "node_remote", "created_at": "2026-10-02T00:00:00Z"}
        self.row.record_version = 1
        self.row.payload_json = {"title": "Remote"}
        with patch.object(sync, "roles", return_value={"system_admin"}):
            plans, conflicts = sync._merge_plan(self.db, 1, self.package, self.database, [self.row], None)
        self.assertEqual(plans[0]["updates"], {"title": "Remote"})
        self.assertEqual(conflicts, [])
        self.package.manifest_json = {"origin_node_uid": "node_remote", "created_at": "2026-09-30T00:00:00Z"}
        with patch.object(sync, "roles", return_value={"system_admin"}), self.assertRaises(HTTPException):
            sync._merge_plan(self.db, 1, self.package, self.database, [self.row], None)

    def test_duplicate_import_returns_processed_without_adding_records(self):
        with patch.object(sync, "_validated_import", return_value=({"package_id": "pkg_test"}, {}, [{}])), patch.object(sync, "audit"):
            result = sync.import_package(self.db, 1, b"duplicate", "password")
        self.assertEqual(result["status"], "already_processed")
        self.assertEqual(self.db.query(SyncPackageRecord).count(), 1)

    def test_history_change_uids_are_stable_and_unique(self):
        rows = [PatentHistory(patent_id=self.patent.id, field_key="title", new_value=value) for value in ("A", "B")]
        self.db.add_all(rows)
        self.db.commit()
        ids = [row.change_uid for row in rows]
        self.assertTrue(all(ids))
        self.assertEqual(len(set(ids)), 2)
        self.db.expire_all()
        self.assertEqual([row.change_uid for row in rows], ids)
