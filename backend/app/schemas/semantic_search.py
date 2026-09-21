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
    rerank_provider_id: int | None = None
    rerank_model: str | None = None
    rerank_enabled: bool = False
    rerank_top_n: int = Field(default=20, ge=1, le=100)
    quality_gate_enabled: bool = False
    quality_thresholds: dict[str, float] = Field(default_factory=dict)
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
    rerank_provider_id: int | None = None
    rerank_model: str | None = Field(default=None, min_length=1, max_length=200)
    rerank_enabled: bool | None = None
    rerank_top_n: int | None = Field(default=None, ge=1, le=100)
    quality_gate_enabled: bool | None = None
    quality_thresholds: dict[str, float] | None = None
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


class SemanticEvaluationDatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=60)
    description: str | None = None


class SemanticEvaluationCaseCreate(BaseModel):
    case_key: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=2000)
    database_id: int | None = None
    relevant_patent_ids: list[int] = Field(min_length=1)
    notes: str | None = None


class SemanticEvaluationCaseUpdate(BaseModel):
    case_key: str | None = Field(default=None, min_length=1, max_length=100)
    query: str | None = Field(default=None, min_length=1, max_length=2000)
    database_id: int | None = None
    relevant_patent_ids: list[int] | None = Field(default=None, min_length=1)
    notes: str | None = None
    enabled: bool | None = None


class SemanticEvaluationRunRequest(BaseModel):
    dataset_id: int
    profile_id: int
    mode: str = "hybrid"
    top_k: int = Field(default=10, ge=1, le=100)
    index_id: int | None = None


class SemanticProviderTestRequest(BaseModel):
    profile_id: int | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200)
