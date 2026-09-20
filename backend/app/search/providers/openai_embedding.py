from __future__ import annotations

import os

from openai import OpenAI

from app.search.contracts import ModelIdentity, SemanticError


def resolve_credential(reference: str | None) -> str:
    if not reference:
        raise SemanticError("SEMANTIC_PROVIDER_AUTH_FAILED", "Embedding provider requires a credential reference")
    if reference.startswith("env://"):
        value = os.environ.get(reference.removeprefix("env://"))
    elif reference.startswith("keyring://"):
        try:
            import keyring
            service, account = reference.removeprefix("keyring://").split("/", 1)
            value = keyring.get_password(service, account)
        except Exception as exc:
            raise SemanticError("SEMANTIC_PROVIDER_AUTH_FAILED", "Configured keyring credential is unavailable") from exc
    else:
        raise SemanticError("SEMANTIC_PROVIDER_AUTH_FAILED", "Credential reference must use env:// or keyring://")
    if not value:
        raise SemanticError("SEMANTIC_PROVIDER_AUTH_FAILED", "Configured embedding credential is unavailable")
    return value


class OpenAICompatibleEmbeddingProvider:
    def __init__(self, *, endpoint: str | None, credential_ref: str | None, model: str, dimensions: int | None):
        self.endpoint = endpoint or None
        self.model = model
        self.dimensions = dimensions
        self.client = OpenAI(api_key=resolve_credential(credential_ref), base_url=self.endpoint)

    def model_identity(self) -> ModelIdentity:
        if not self.dimensions:
            raise SemanticError("SEMANTIC_DIMENSION_MISMATCH", "Profile must declare embedding dimensions before indexing")
        return ModelIdentity("openai_compatible", self.model, self.dimensions, self.endpoint or "")

    def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            request = {"model": self.model, "input": texts}
            if self.dimensions:
                request["dimensions"] = self.dimensions
            response = self.client.embeddings.create(**request)
        except Exception as exc:
            raise SemanticError("SEMANTIC_PROVIDER_UNAVAILABLE", "Embedding provider request failed") from exc
        vectors = [list(item.embedding) for item in response.data]
        if len(vectors) != len(texts) or not vectors:
            raise SemanticError("SEMANTIC_PROVIDER_UNAVAILABLE", "Embedding provider returned an incomplete batch")
        expected = self.dimensions or len(vectors[0])
        if any(len(vector) != expected for vector in vectors):
            raise SemanticError("SEMANTIC_DIMENSION_MISMATCH", "Embedding provider returned unexpected dimensions")
        self.dimensions = expected
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]
