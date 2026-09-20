from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class SemanticError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelIdentity:
    provider: str
    model: str
    dimensions: int
    endpoint: str = ""


@dataclass
class VectorDocument:
    document_id: str
    patent_id: int
    text: str
    vector: list[float]
    metadata: dict = field(default_factory=dict)


class EmbeddingProvider(Protocol):
    def model_identity(self) -> ModelIdentity: ...
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class VectorStore(Protocol):
    def upsert(self, documents: list[VectorDocument]) -> None: ...
    def delete(self, document_ids: list[str]) -> None: ...
    def dense_search(self, vector: list[float], limit: int) -> list[dict]: ...
    def count(self) -> int: ...
