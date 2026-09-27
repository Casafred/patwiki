"""Department collaboration and offline package synchronization models.

These tables deliberately live beside the existing local-first models.  A
package is an auditable capability boundary; it is never treated as a second
SQLite database and it never contains local connector credentials.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class CollaborationCredential(Base):
    __tablename__ = "collaboration_credentials"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    login_name = Column(String(100), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    failed_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime)


class CollaborationSession(Base):
    __tablename__ = "collaboration_sessions"

    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("collaboration_credentials.user_id"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class TrustedSyncDevice(Base):
    __tablename__ = "collaboration_trusted_devices"

    fingerprint = Column(String(64), primary_key=True)
    name = Column(String(200), nullable=False)
    public_key = Column(String(100), nullable=False)
    revoked_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class OrganizationUnit(Base):
    __tablename__ = "collaboration_organization_units"

    id = Column(Integer, primary_key=True, index=True)
    unit_uid = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    unit_type = Column(String(30), nullable=False, default="department")
    team_type = Column(String(30), nullable=True)
    parent_id = Column(Integer, ForeignKey("collaboration_organization_units.id", ondelete="SET NULL"), nullable=True, index=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class UserRoleAssignment(Base):
    __tablename__ = "collaboration_user_role_assignments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_code = Column(String(40), nullable=False)
    unit_id = Column(Integer, ForeignKey("collaboration_organization_units.id", ondelete="SET NULL"), nullable=True, index=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    assigned_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class UserResponsibility(Base):
    __tablename__ = "collaboration_user_responsibilities"
    __table_args__ = (
        UniqueConstraint("user_id", "scope_type", "scope_uid", "team_type", "valid_from", name="uq_collab_user_scope_role"),
        Index("ix_collab_responsibility_scope", "scope_type", "scope_uid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_type = Column(String(30), nullable=False)
    scope_uid = Column(String(100), nullable=False)
    team_type = Column(String(30), nullable=False)
    unit_id = Column(Integer, ForeignKey("collaboration_organization_units.id", ondelete="SET NULL"), nullable=True, index=True)
    responsibility_level = Column(String(30), nullable=False, default="owner")
    can_edit = Column(Boolean, nullable=False, default=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    assigned_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class CollaborationEdge(Base):
    __tablename__ = "collaboration_edges"
    __table_args__ = (UniqueConstraint(
        "source_user_id", "target_user_id", "scope_type", "scope_uid", "relation_type",
        name="uq_collaboration_edge_scope",
    ),)

    id = Column(Integer, primary_key=True, index=True)
    source_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_type = Column(String(30), nullable=False)
    scope_uid = Column(String(100), nullable=False)
    relation_type = Column(String(40), nullable=False, default="same_category")
    default_access = Column(String(20), nullable=False, default="viewer")
    can_request_edit = Column(Boolean, nullable=False, default=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class PermissionGrant(Base):
    __tablename__ = "collaboration_permission_grants"

    id = Column(Integer, primary_key=True, index=True)
    grant_uid = Column(String(80), unique=True, nullable=False, index=True)
    subject_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    subject_label = Column(String(200), nullable=True)
    granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scope_type = Column(String(30), nullable=False, default="package")
    scope_uid = Column(String(100), nullable=False)
    field_scope = Column(JSON, nullable=False, default=list)
    scope_json = Column(JSON, nullable=False, default=dict)
    actions = Column(JSON, nullable=False, default=list)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    password_digest = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class SyncWorkspace(Base):
    __tablename__ = "collaboration_sync_workspaces"

    id = Column(Integer, primary_key=True, index=True)
    workspace_uid = Column(String(80), unique=True, nullable=False, index=True)
    node_uid = Column(String(80), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(200), nullable=False, default="本机协作空间")
    format_version = Column(Integer, nullable=False, default=1)
    public_key = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class SyncChannel(Base):
    __tablename__ = "collaboration_sync_channels"

    id = Column(Integer, primary_key=True, index=True)
    channel_uid = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    scope_json = Column(JSON, nullable=False, default=dict)
    member_policy = Column(String(30), nullable=False, default="explicit")
    checkpoint_sequence = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SyncPackage(Base):
    __tablename__ = "collaboration_sync_packages"
    __table_args__ = (
        Index("ix_collab_sync_package_status", "status"),
        Index("ix_collab_sync_package_created", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    package_uid = Column(String(80), unique=True, nullable=False, index=True)
    package_type = Column(String(30), nullable=False, default="snapshot")
    direction = Column(String(20), nullable=False, default="outbox")
    path = Column(String(1000), nullable=False)
    file_hash = Column(String(128), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="created")
    access = Column(String(20), nullable=False, default="viewer")
    manifest_json = Column(JSON, nullable=False, default=dict)
    signature_status = Column(String(30), nullable=False, default="not_signed")
    error_message = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    applied_at = Column(DateTime, nullable=True)


class SyncPackageMember(Base):
    __tablename__ = "collaboration_sync_package_members"
    __table_args__ = (
        UniqueConstraint("package_id", "user_id", name="uq_collab_package_member"),
    )

    id = Column(Integer, primary_key=True, index=True)
    package_id = Column(Integer, ForeignKey("collaboration_sync_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    subject_label = Column(String(200), nullable=True)
    access = Column(String(20), nullable=False, default="viewer")
    field_scope = Column(JSON, nullable=False, default=list)
    grant_id = Column(Integer, ForeignKey("collaboration_permission_grants.id", ondelete="SET NULL"), nullable=True)


class SyncPackageRecord(Base):
    """Validated read-only evidence; never a second canonical Patent row."""

    __tablename__ = "collaboration_sync_package_records"
    __table_args__ = (
        UniqueConstraint("package_id", "entity_uid", name="uq_collab_package_entity"),
        Index("ix_collab_package_record_entity", "entity_uid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    package_id = Column(Integer, ForeignKey("collaboration_sync_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    entity_uid = Column(String(100), nullable=False)
    record_version = Column(Integer, nullable=False, default=1)
    scope_json = Column(JSON, nullable=False, default=dict)
    payload_json = Column(JSON, nullable=False, default=dict)
    field_provenance = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, server_default=func.now())


class SyncCheckpoint(Base):
    __tablename__ = "collaboration_sync_checkpoints"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("collaboration_sync_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    node_uid = Column(String(80), nullable=False, index=True)
    sequence = Column(Integer, nullable=False, default=0)
    package_id = Column(Integer, ForeignKey("collaboration_sync_packages.id", ondelete="SET NULL"), nullable=True)
    ack_at = Column(DateTime, nullable=True)


class SyncEntityState(Base):
    __tablename__ = "collaboration_sync_entity_states"
    __table_args__ = (
        UniqueConstraint("entity_uid", "channel_id", name="uq_collab_entity_channel"),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_uid = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    channel_id = Column(Integer, ForeignKey("collaboration_sync_channels.id", ondelete="CASCADE"), nullable=False)
    last_version = Column(Integer, nullable=False, default=0)
    last_hash = Column(String(128), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SyncEntityFieldState(Base):
    """Last accepted remote value used as the three-way merge base."""

    __tablename__ = "collaboration_sync_entity_field_states"
    __table_args__ = (
        UniqueConstraint("origin_node_uid", "entity_uid", "field_key", name="uq_collab_entity_field_origin"),
        Index("ix_collab_entity_field_entity", "entity_uid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    origin_node_uid = Column(String(80), nullable=False, index=True)
    entity_uid = Column(String(100), nullable=False)
    field_key = Column(String(200), nullable=False)
    last_value = Column(JSON, nullable=True)
    last_version = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SyncChange(Base):
    __tablename__ = "collaboration_sync_changes"

    id = Column(Integer, primary_key=True, index=True)
    change_uid = Column(String(80), unique=True, nullable=False, index=True)
    package_id = Column(Integer, ForeignKey("collaboration_sync_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_uid = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    field_key = Column(String(200), nullable=True)
    base_value = Column(JSON, nullable=True)
    remote_value = Column(JSON, nullable=True)
    operation = Column(String(30), nullable=False, default="upsert")
    created_at = Column(DateTime, server_default=func.now())


class SyncConflict(Base):
    __tablename__ = "collaboration_sync_conflicts"

    id = Column(Integer, primary_key=True, index=True)
    conflict_uid = Column(String(80), unique=True, nullable=False, index=True)
    package_id = Column(Integer, ForeignKey("collaboration_sync_packages.id", ondelete="CASCADE"), nullable=True, index=True)
    origin_node_uid = Column(String(80), nullable=True, index=True)
    entity_uid = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    field_key = Column(String(200), nullable=False)
    base_value = Column(JSON, nullable=True)
    local_value = Column(JSON, nullable=True)
    remote_value = Column(JSON, nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    decision = Column(String(30), nullable=True)
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class SyncTombstone(Base):
    __tablename__ = "collaboration_sync_tombstones"

    id = Column(Integer, primary_key=True, index=True)
    entity_uid = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    deleted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime, server_default=func.now())
    base_version = Column(Integer, nullable=False, default=0)


class SyncAuditEvent(Base):
    __tablename__ = "collaboration_sync_audit_events"
    __table_args__ = (Index("ix_collab_audit_created", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(50), nullable=False)
    package_id = Column(Integer, ForeignKey("collaboration_sync_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    scope_json = Column(JSON, nullable=False, default=dict)
    result = Column(String(30), nullable=False, default="success")
    detail_json = Column(JSON, nullable=False, default=dict)
    device_uid = Column(String(80), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
