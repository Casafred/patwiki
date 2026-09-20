from __future__ import annotations

import httpx

from app.search.contracts import RerankDocument, RerankResult, SemanticError
from app.search.providers.openai_embedding import resolve_credential


class OpenAICompatibleRerankProvider:
    """Adapter for providers exposing a Cohere-style rerank JSON endpoint."""

    def __init__(self, *, endpoint: str | None, credential_ref: str | None, model: str, timeout_seconds: float = 20.0):
        if not endpoint:
            raise SemanticError("SEMANTIC_PROVIDER_UNAVAILABLE", "Rerank provider endpoint is required")
        self.endpoint = endpoint
        self.model = model
        self.headers = {"Authorization": f"Bearer {resolve_credential(credential_ref)}"}
        self.timeout = timeout_seconds

    def rerank(self, query: str, documents: list[RerankDocument], top_n: int) -> list[RerankResult]:
        if not documents:
            return []
        payload = {"model": self.model, "query": query, "documents": [item.text for item in documents], "top_n": min(top_n, len(documents))}
        try:
            response = httpx.post(self.endpoint, json=payload, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            raise SemanticError("SEMANTIC_RERANK_UNAVAILABLE", "Rerank provider request failed") from exc
        raw_results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(raw_results, list):
            raise SemanticError("SEMANTIC_RERANK_INVALID_RESPONSE", "Rerank provider returned no results")
        output: list[RerankResult] = []
        seen: set[str] = set()
        for rank, raw in enumerate(raw_results, start=1):
            if not isinstance(raw, dict) or not isinstance(raw.get("index"), int):
                raise SemanticError("SEMANTIC_RERANK_INVALID_RESPONSE", "Rerank provider returned an invalid result")
            index = raw["index"]
            if index < 0 or index >= len(documents):
                raise SemanticError("SEMANTIC_RERANK_INVALID_RESPONSE", "Rerank provider returned an out-of-range document")
            document = documents[index]
            if document.document_id in seen:
                raise SemanticError("SEMANTIC_RERANK_INVALID_RESPONSE", "Rerank provider returned duplicate documents")
            seen.add(document.document_id)
            try:
                score = float(raw.get("relevance_score", raw.get("score", 0.0)))
            except (TypeError, ValueError) as exc:
                raise SemanticError("SEMANTIC_RERANK_INVALID_RESPONSE", "Rerank provider returned an invalid score") from exc
            output.append(RerankResult(document.document_id, document.patent_id, score, rank))
        return output
