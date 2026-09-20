from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class SemanticProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider_kind: str = "embedding"
    provider_type: str = "openai_compatible"
    endpoint: str | None = None
    credential_ref: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SemanticProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    endpoint: str | None = Field(default=None, max_length=1000)
    credential_ref: str | None = Field(default=None, max_length=500)
    config_json: dict[str, Any] | None = None
    enabled: bool | None = None


class SemanticProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    embedding_provider_id: int | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int | None = None
    vector_backend: str = "zvec"
    retrieval_mode: str = "hybrid"
    is_default: bool = False
    indexed_field_allowlist: list[str] = Field(default_factory=list)


class SemanticProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    is_default: bool | None = None
    embedding_provider_id: int | None = None
    embedding_model: str | None = Field(default=None, min_length=1, max_length=200)
    embedding_dimensions: int | None = Field(default=None, ge=1)
    vector_backend: str | None = None
    retrieval_mode: str | None = None
    indexed_field_allowlist: list[str] | None = None
    keyword_weight: int | None = Field(default=None, ge=0)
    vector_weight: int | None = Field(default=None, ge=0)
    rrf_k: int | None = Field(default=None, ge=1)
    keyword_candidate_count: int | None = Field(default=None, ge=1)
    vector_candidate_count: int | None = Field(default=None, ge=1)
    result_top_k: int | None = Field(default=None, ge=1, le=100)
    template_version: str | None = Field(default=None, min_length=1, max_length=60)
    chunk_strategy_version: str | None = Field(default=None, min_length=1, max_length=60)
    distance_metric: str | None = None


class SemanticQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    database_id: int | None = None
    mode: str = "hybrid"
    top_k: int = Field(default=20, ge=1, le=100)
    profile_id: int | None = None
    include_explain: bool = False


class SemanticRebuildRequest(BaseModel):
    profile_id: int
    database_id: int | None = None
