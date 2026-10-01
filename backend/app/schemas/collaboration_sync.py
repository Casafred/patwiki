"""Strict requests for the authenticated collaboration subsystem."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Role = Literal["system_admin", "department_leader", "group_leader", "member", "viewer"]
Team = Literal["writing", "retrieval", "analysis"]


class LoginRequest(RequestModel):
    username: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.@-]+$")
    password: str = Field(min_length=10, max_length=200)


class BootstrapRequest(LoginRequest):
    setup_token: str = Field(min_length=32, max_length=200)
    display_name: str = Field(min_length=1, max_length=100)


class AccountRequest(LoginRequest):
    display_name: str = Field(min_length=1, max_length=100)
    role: Role = "member"
    unit_id: int | None = None


class UnitRequest(RequestModel):
    name: str = Field(min_length=1, max_length=100)
    team_type: Team
    parent_id: int | None = None


class PeerRequest(RequestModel):
    name: str = Field(min_length=1, max_length=100)
    public_key: str = Field(min_length=40, max_length=100)


class ExportRequest(RequestModel):
    database_ids: list[int] = Field(min_length=1, max_length=500)
    patent_ids: list[int] | None = Field(default=None, max_length=20000)
    product_ids: list[int] | None = Field(default=None, max_length=500)
    fields: list[str] = Field(min_length=1, max_length=200)
    recipient_names: list[str] = Field(min_length=1, max_length=100)
    include_attachments: bool = False
    password: str = Field(min_length=10, max_length=200)
    expires_days: int = Field(default=30, ge=1, le=365)


class ActiveRequest(RequestModel):
    active: bool


class AccountRoleRequest(RequestModel):
    role: Role
    unit_id: int | None = None


class PasswordRequest(RequestModel):
    current_password: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class ResponsibilityRequest(RequestModel):
    user_id: int
    product_id: int
    team_type: Team
    unit_id: int
    level: Literal["owner", "backup", "reviewer"] = "owner"


class LibraryGrantRequest(RequestModel):
    user_id: int
    database_id: int
    product_ids: list[int] = Field(default_factory=list, max_length=500)
    fields: list[str] = Field(min_length=1, max_length=100)
    actions: list[Literal["export", "apply"]] = Field(default_factory=lambda: ["export"], min_length=1, max_length=2)
    edit_password: str | None = Field(default=None, min_length=10, max_length=200)
    expires_days: int = Field(default=90, ge=1, le=365)


class SyncConflictDecision(RequestModel):
    entity_uid: str = Field(pattern=r"^pat_[a-f0-9]{32}$")
    field_key: str = Field(min_length=1, max_length=200)
    choice: Literal["local", "remote"]


class ApplyPackageRequest(RequestModel):
    database_id: int
    edit_password: str | None = Field(default=None, min_length=10, max_length=200)
    decisions: list[SyncConflictDecision] = Field(default_factory=list, max_length=20000)


class AggregationBatchCreateRequest(RequestModel):
    name: str = Field(min_length=1, max_length=200)
    target_database_id: int
    package_uids: list[str] = Field(default_factory=list, max_length=500)


class AggregationBatchSubmitRequest(RequestModel):
    edit_password: str | None = Field(default=None, min_length=10, max_length=200)
    decisions: list[SyncConflictDecision] = Field(default_factory=list, max_length=20000)


class AggregationPublishRequest(RequestModel):
    recipient_names: list[str] = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=200)
    fields: list[str] = Field(default_factory=lambda: ["title", "publication_number", "application_number", "legal_status"])
    expires_days: int = Field(default=30, ge=1, le=365)
