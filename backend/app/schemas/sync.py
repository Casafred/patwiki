"""API schemas for external patent synchronization."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConnectorCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    transport: str = "api"
    provider_type: str = "demo"
    endpoint: str | None = None
    capabilities_json: dict[str, Any] = Field(default_factory=dict)
    config_json: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ConnectorUpdate(BaseModel):
    name: str | None = None
    endpoint: str | None = None
    capabilities_json: dict[str, Any] | None = None
    config_json: dict[str, Any] | None = None
    enabled: bool | None = None


class CredentialCreate(BaseModel):
    credential_ref: str = Field(min_length=1, max_length=500)
    credential_type: str = "api_key"
    label: str | None = None


class SavedQueryCreate(BaseModel):
    database_id: int
    name: str = Field(min_length=1, max_length=200)
    query_json: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SavedQueryUpdate(BaseModel):
    name: str | None = None
    query_json: dict[str, Any] | None = None
    enabled: bool | None = None


class SubscriptionCreate(BaseModel):
    database_id: int
    connector_id: int
    name: str = Field(min_length=1, max_length=200)
    saved_query_id: int | None = None
    mode: str = "query"
    scope_json: dict[str, Any] = Field(default_factory=dict)
    schedule_json: dict[str, Any] = Field(default_factory=dict)
    review_policy: str = "safe_auto_apply"
    enabled: bool = True


class SubscriptionUpdate(BaseModel):
    name: str | None = None
    saved_query_id: int | None = None
    scope_json: dict[str, Any] | None = None
    schedule_json: dict[str, Any] | None = None
    review_policy: str | None = None
    enabled: bool | None = None


class RunRequest(BaseModel):
    trigger: str = "manual"
    max_pages: int = Field(default=100, ge=1, le=1000)


class PatentRefreshRequest(BaseModel):
    connector_id: int
    identifier_type: str = "publication"
    identifier: str = Field(min_length=1, max_length=300)
    database_id: int | None = None
    review_policy: str = "safe_auto_apply"


class ObservationDecisionRequest(BaseModel):
    decision: str
    decided_by: str = "local-user"
    reason: str | None = None


class WatchEventUpdate(BaseModel):
    status: str = "acknowledged"
    acknowledged_by: str = "local-user"


class SyncUpdatePreviewRequest(BaseModel):
    connector_id: int
    database_id: int
    patent_ids: list[int] = Field(min_length=1, max_length=500)
    fields: list[str] | None = None


class SyncUpdateItemChoice(BaseModel):
    item_id: int
    fields: list[str] = Field(default_factory=list)


class SyncUpdateConfirmRequest(BaseModel):
    selected_items: list[SyncUpdateItemChoice] = Field(default_factory=list)
    confirmed_by: str = "local-user"
