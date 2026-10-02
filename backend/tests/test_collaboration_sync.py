import unittest
import io
import tempfile
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
import app.models
from app.models import DatabaseMembership, User, Patent, PatentDatabase, PatentHistory, SyncAggregationBatch, SyncEntityFieldState, SyncPackage, SyncPackageRecord, SyncUidMapping
from app.services import collaboration_sync_service as sync
from app.services.collaboration_package_codec import encrypt_v3_stream, decrypt_v3_stream, encode, decode, decode_stream, V3_CHUNK_BYTES
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import hashlib


class CollaborationSyncTest(unittest.TestCase):
    def test_v3_chunk_roundtrip_and_tampering(self):
        from cryptography.exceptions import InvalidTag
        content = b'x' * (V3_CHUNK_BYTES + 123)
        encrypted = io.BytesIO()
        encrypt_v3_stream(io.BytesIO(content), encrypted, 'test-password-123')
        restored = io.BytesIO()
        decrypt_v3_stream(io.BytesIO(encrypted.getvalue()), restored, 'test-password-123')
        self.assertEqual(restored.getvalue(), content)
        damaged = bytearray(encrypted.getvalue())
        damaged[-1] ^= 1
        with self.assertRaises(InvalidTag):
            decrypt_v3_stream(io.BytesIO(damaged), io.BytesIO(), 'test-password-123')

    def test_signed_v3_package_roundtrip(self):
        private = Ed25519PrivateKey.generate()
        private_bytes = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        fingerprint = hashlib.sha256(public).hexdigest()
        manifest = {"package_id": "pkg_" + "a" * 32, "profile": "patent-snapshot-v1", "package_type": "snapshot",
                    "created_at": "2026-10-01T00:00:00", "expires_at": "2026-11-01T00:00:00", "created_by": {},
                    "origin_node_uid": "node_" + "b" * 32, "fields": ["title"], "count": 1, "databases": [],
                    "signature_status": "signed", "signer_fingerprint": fingerprint}
        permissions = {"access": "viewer", "recipients": ["alice"], "fields": ["title"], "can_edit": False, "can_redistribute": False}
        record = {"entity_type": "patent", "entity_uid": "pat_" + "c" * 32, "record_version": 1,
                  "origin_node_uid": manifest["origin_node_uid"], "scope": {}, "payload": {"title": "Device"}}
        raw = encode(manifest, permissions, [record], "test-password-123", private_bytes)
        decoded_manifest, _, decoded_records = decode(raw, "test-password-123", {fingerprint: public})
        self.assertEqual(decoded_manifest["signature_status"], "trusted")
        self.assertEqual(decoded_records[0]["payload"], {"title": "Device"})
        streamed = []
        stream_manifest, _, collected = decode_stream(io.BytesIO(raw), "test-password-123",
            {fingerprint: public}, streamed.append)
        self.assertEqual(stream_manifest["signature_status"], "trusted")
        self.assertEqual(collected, [])
        self.assertEqual(streamed, decoded_records)
        legacy_manifest = dict(manifest, signature_status="not_signed", signer_fingerprint=None)
        legacy_raw = encode(legacy_manifest, permissions, [record], "test-password-123")
        streamed.clear()
        decode_stream(io.BytesIO(legacy_raw), "test-password-123", record_handler=streamed.append)
        self.assertEqual(streamed[0]["payload"], {"title": "Device"})
        user = User(username="alice", display_name="Alice", role="member")
        self.db.add(user)
        self.db.commit()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "inbox").mkdir()
            with patch.object(sync, "workspace_dir", return_value=root):
                preview = sync.process_package_stream(self.db, user.id, io.BytesIO(raw), "test-password-123", inspect=True)
                self.assertEqual(len(preview["sample"]), 1)
                self.assertEqual(self.db.query(SyncPackageRecord).count(), 1)
                result = sync.process_package_stream(self.db, user.id, io.BytesIO(raw), "test-password-123")
                self.assertEqual(result["status"], "imported")
                self.assertEqual(self.db.query(SyncPackageRecord).count(), 2)
                result = sync.process_package_stream(self.db, user.id, io.BytesIO(raw), "test-password-123")
                self.assertEqual(result["status"], "already_processed")
                self.assertEqual(self.db.query(SyncPackageRecord).count(), 2)

    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.database = PatentDatabase(name="Sync", code="SYNC", kind="department_master")
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

    def test_delete_record_has_explicit_plan_and_requires_target_permission(self):
        self.row.entity_type = "patent_tombstone"
        self.row.entity_uid = self.patent.entity_uid
        self.row.payload_json = {}
        self.db.commit()
        with patch.object(sync, "roles", return_value={"system_admin"}):
            plans, conflicts = sync._merge_plan(self.db, 1, self.package, self.database, [self.row], None)
        self.assertEqual(plans[0]["operation"], "delete")
        self.assertEqual(conflicts, [])
        with patch.object(sync, "roles", return_value={"member"}), self.assertRaises(HTTPException):
            sync._merge_plan(self.db, 1, self.package, self.database, [self.row], None)

    def test_member_database_permission_controls_export_without_legacy_grant(self):
        user = User(username="exporter", role="member")
        self.db.add(user)
        self.db.flush()
        membership = DatabaseMembership(user_id=user.id, database_id=self.database.id, role="editor")
        self.db.add(membership)
        self.db.commit()
        request = SimpleNamespace(database_ids=[self.database.id], patent_ids=None, product_ids=None,
            fields=["title"], include_attachments=False, recipient_names=["alice"])
        self.assertIn(self.database.id, sync._owned_export_databases(self.db, user.id))
        with patch.object(sync, "roles", return_value={"member"}):
            sync._validate_export_scope(self.db, user.id, request, ["title"], [self.database])
            records = sync._records(self.db, user.id, request, ["title"], [self.database], "node_local")
        self.assertEqual(len(records), 1)
        membership.role = "viewer"
        self.db.commit()
        with patch.object(sync, "roles", return_value={"member"}), self.assertRaises(HTTPException):
            sync._validate_export_scope(self.db, user.id, request, ["title"], [self.database])

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

    def test_aggregation_batch_collects_packages_and_previews_categories(self):
        with patch.object(sync, "roles", return_value={"system_admin"}), patch.object(
            sync, "_merge_plan", return_value=([
                {"patent": self.patent, "updates": {"title": "Next"}, "conflicts": []},
                {"patent": None, "updates": {}, "conflicts": []},
            ], []),
        ):
            created = sync.create_aggregation_batch(self.db, 1, "第1周汇总", self.database.id, [self.package.package_uid])
            preview = sync.preview_aggregation_batch(self.db, 1, created["batch_uid"])
        self.assertEqual(preview["status"], "open")
        self.assertEqual(preview["preview"]["auto_merge"], 1)
        self.assertEqual(preview["preview"]["new"], 1)
        self.assertEqual(self.db.query(SyncAggregationBatch).count(), 1)
