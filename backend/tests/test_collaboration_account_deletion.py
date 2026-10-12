from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
import app.models
from app.models import User
from app.models.collaboration_sync import CollaborationCredential, CollaborationSession, UserRoleAssignment
from app.api.collaboration_sync import delete_account, router


@pytest.mark.parametrize("second_admin", [False, True])
def test_delete_current_admin_preserves_history_and_requires_replacement(second_admin):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            user = User(username="admin", role="admin", is_active=True)
            db.add(user)
            db.flush()
            user_id = user.id
            db.add(CollaborationCredential(user_id=user_id, login_name="admin", password_hash="test", active=True))
            db.add(UserRoleAssignment(user_id=user_id, role_code="system_admin"))
            db.flush()
            db.add(CollaborationSession(user_id=user_id, token_hash="a" * 64, expires_at=datetime.now() + timedelta(hours=1)))
            if second_admin:
                other = User(username="replacement", role="admin", is_active=True)
                db.add(other)
                db.flush()
                db.add(CollaborationCredential(user_id=other.id, login_name="replacement", password_hash="test", active=True))
                db.add(UserRoleAssignment(user_id=other.id, role_code="system_admin"))
            db.commit()
            if second_admin:
                assert delete_account(user_id, user, db)["success"]
                assert db.get(CollaborationCredential, user_id) is None
                assert not db.query(CollaborationSession).filter_by(user_id=user_id).count()
                assert db.get(User, user_id) is not None
                assert not db.get(User, user_id).is_active
                assert db.query(UserRoleAssignment).filter_by(user_id=user_id).one().valid_to is not None
            else:
                with pytest.raises(HTTPException) as error:
                    delete_account(user_id, user, db)
                assert error.value.status_code == 409
                assert db.get(CollaborationCredential, user_id) is not None
                assert db.query(CollaborationSession).filter_by(user_id=user_id).count() == 1
    finally:
        engine.dispose()


def test_delete_account_route_is_registered_once():
    assert len([route for route in router.routes if route.path.endswith("/accounts/{target_user_id}") and "DELETE" in route.methods]) == 1
