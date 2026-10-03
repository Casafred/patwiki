import base64
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
import app.models
from app.models import User
from app.models.collaboration_sync import CollaborationCredential, CollaborationEnrollment
from app.services.collaboration_identity_service import PASSWORDS, roles
from app.services.collaboration_enrollment_service import import_enrollment
from app.services.collaboration_package_codec import json_bytes


def test_employee_enrollment_updates_preserve_password_and_reject_other_issuer():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    private = Ed25519PrivateKey.generate()
    now = datetime(2026, 10, 2, 0, 0)
    payload = {"format": "patwiki.employee-config", "version": 1, "department_code": "IP",
        "employee_no": "E001", "user_uid": "user_" + "a" * 32, "username": "alice", "display_name": "Alice",
        "role": "member", "active": True, "password_hash": PASSWORDS.hash("initial-password"),
        "issued_at": now.isoformat(), "issuer_public_key": base64.b64encode(private.public_key().public_bytes_raw()).decode()}
    def signed(value, key=private):
        return json.dumps({"payload": value, "signature": base64.b64encode(key.sign(json_bytes(value))).decode()}).encode()
    with Session(engine) as db, patch("app.services.collaboration_enrollment_service.utc_now_naive", return_value=now + timedelta(days=3)):
        result = import_enrollment(db, signed(payload))
        assert result["status"] == "configured"
        user = db.query(User).one()
        assert roles(db, user.id) == {"member"}
        credential = db.get(CollaborationCredential, user.id)
        credential.password_hash = PASSWORDS.hash("changed-password")
        db.commit()
        update = {**payload, "active": False, "issued_at": (now + timedelta(days=1)).isoformat()}
        import_enrollment(db, signed(update))
        assert PASSWORDS.verify(credential.password_hash, "changed-password")
        assert not credential.active
        assert import_enrollment(db, signed(payload))["status"] == "already_processed"
        assert not credential.active
        other_key = Ed25519PrivateKey.generate()
        invalid = {**payload, "issued_at": (now + timedelta(days=2)).isoformat(),
            "issuer_public_key": base64.b64encode(other_key.public_key().public_bytes_raw()).decode()}
        with pytest.raises(HTTPException) as error:
            import_enrollment(db, signed(invalid, other_key))
        assert error.value.status_code == 403
        assert db.query(CollaborationEnrollment).count() == 1
    engine.dispose()
