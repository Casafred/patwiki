"""Business acceptance regressions for department aggregation and publication."""
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import base64
import hashlib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models
from app.database import Base
from app.models import User, Patent, PatentDatabase, PatentDatabaseMembership, DatabaseMembership
from app.models.collaboration_sync import SyncPackage, SyncPackageRecord, SyncEntityFieldState, SyncAggregationBatch
from app.services import collaboration_sync_service as sync
from app.services.collaboration_update_service import pooled_requests, save_sharing_preference
from app.services.collaboration_package_codec import decode


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def setup_records(db):
    user = User(username="admin")
    database = PatentDatabase(name="Department", kind="department_master")
    db.add_all([user, database])
    db.flush()
    patent = Patent(title="Original", notes="Private note", database_id=database.id, entity_uid="pat_" + "a" * 32,
        publication_number="CN123456789A")
    db.add(patent)
    db.commit()
    return user, database, patent


def package(db, user, patent, suffix, title, package_type="snapshot"):
    item = SyncPackage(package_uid="pkg_" + suffix * 32, direction="inbox", path="unused", file_hash=suffix,
        created_by=user.id, status="imported", package_type=package_type,
        manifest_json={"origin_node_uid": "node_" + suffix * 32, "created_at": "2026-10-01T00:00:00",
            "databases": [{"database_uid": "db_" + "d" * 32, "name": "Master"}],
            "update_requests": [{"entity_uid": patent.entity_uid, "fields": ["legal_status"]}]})
    db.add(item)
    db.flush()
    row = SyncPackageRecord(package_id=item.id, entity_type="patent", entity_uid=patent.entity_uid,
        payload_json={"title": title}, record_version=1)
    db.add(row)
    db.add(SyncEntityFieldState(origin_node_uid=item.manifest_json["origin_node_uid"], entity_uid=patent.entity_uid,
        field_key="title", last_value="Original", last_version=1))
    db.commit()
    return item, row


def test_simultaneous_member_changes_keep_master_until_reviewed(db):
    user, database, patent = setup_records(db)
    first, _ = package(db, user, patent, "b", "Alice")
    second, _ = package(db, user, patent, "c", "Bob")
    with patch.object(sync, "roles", return_value={"system_admin"}):
        batch = sync.create_aggregation_batch(db, user.id, "Weekly", database.id, [first.package_uid, second.package_uid])
        preview = sync.preview_aggregation_batch(db, user.id, batch["batch_uid"])
        assert len(preview["preview"]["conflicts"]) == 2
        sync.submit_aggregation_batch(db, user.id, batch["batch_uid"], SimpleNamespace(edit_password=None, decisions=[]))
    assert patent.title == "Original"
    assert first.status == second.status == "partially_applied"
    batch_row = db.query(SyncAggregationBatch).one()
    requests = pooled_requests(db, batch_row)
    assert len(requests) == 1
    assert len(requests[0]["sources"]) == 2


def test_publication_preserves_private_fields_and_unsubmitted_edit(db):
    user, database, patent = setup_records(db)
    item, row = package(db, user, patent, "b", "Published", "department_publication")
    row.payload_json = {"title": "Published", "notes": "Remote private note", "risk_description": "Remote judgement"}
    patent.title = "Local edit"
    db.commit()
    with patch.object(sync, "roles", return_value={"system_admin"}):
        result = sync.apply_package(db, user.id, item.package_uid,
            SimpleNamespace(database_id=database.id, edit_password=None, decisions=[]))
    assert result["pending_conflicts"] == 1
    assert patent.title == "Local edit"
    assert patent.notes == "Private note"
    assert patent.risk_description is None


def test_personal_exit_does_not_delete_department_record(db):
    user, database, patent = setup_records(db)
    item, row = package(db, user, patent, "b", "Original")
    row.entity_type = "patent_tombstone"
    row.payload_json = {}
    row.field_provenance = {"deletion_scope": "library_exit", "base_version": 1}
    db.commit()
    with patch.object(sync, "roles", return_value={"system_admin"}):
        result = sync.apply_package(db, user.id, item.package_uid,
            SimpleNamespace(database_id=database.id, edit_password=None, decisions=[]))
    assert result["status"] == "applied"
    assert patent.deleted_at is None
    assert patent.database_id == database.id


def test_saved_scopes_require_permission_and_safe_fields(db):
    user, database, _ = setup_records(db)
    db.add(DatabaseMembership(user_id=user.id, database_id=database.id, role="owner"))
    db.commit()
    request = SimpleNamespace(shared_database_ids=[database.id], update_database_ids=[database.id], update_fields=["legal_status"])
    assert save_sharing_preference(db, user.id, request)["update_fields"] == ["legal_status"]
    request.update_fields = ["notes"]
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        save_sharing_preference(db, user.id, request)


def test_export_delta_roundtrip_uses_saved_checkpoint_and_no_recipient_accounts(db, tmp_path):
    user, database, patent = setup_records(db)
    (tmp_path / "outbox").mkdir()
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    signer = {"private_key": private.private_bytes_raw(), "public_key": base64.b64encode(public).decode(),
        "fingerprint": hashlib.sha256(public).hexdigest()}
    request = SimpleNamespace(database_ids=[database.id], patent_ids=None, product_ids=None,
        fields=["title"], recipient_names=[], include_attachments=False, password="export-password", expires_days=30, mode="full")
    with patch.object(sync, "roles", return_value={"system_admin"}), patch.object(sync, "workspace_dir", return_value=tmp_path), patch.object(sync, "device_signing_identity", return_value=signer):
        first = sync.export_package(db, user.id, request)
        request.mode = "delta"
        second = sync.export_package(db, user.id, request)
        assert second["count"] == 0
        patent.title = "Changed"
        db.commit()
        third = sync.export_package(db, user.id, request)
        manifest, permissions, records = decode(Path(third["path"]).read_bytes(), request.password)
    assert manifest["export_mode"] == "delta"
    assert manifest["base_package_uid"] == second["package_uid"]
    assert len(records) == 1
    assert records[0]["payload"]["title"] == "Changed"
    assert permissions["recipients"] == []
