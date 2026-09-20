from __future__ import annotations

import json
import math
from pathlib import Path

from app.search.contracts import SemanticError, VectorDocument


class JsonLocalVectorStore:
    """Small, rebuildable local store used until Zvec passes the project PoC."""

    def __init__(self, path: Path, dimensions: int | None = None):
        self.path = path
        self.dimensions = dimensions
        self._documents: dict[str, dict] = {}
        if path.exists():
            self._documents = json.loads(path.read_text(encoding="utf-8")).get("documents", {})

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({"documents": self._documents}, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.path)

    def upsert(self, documents: list[VectorDocument]) -> None:
        for doc in documents:
            if not doc.vector or any(not math.isfinite(x) for x in doc.vector):
                raise SemanticError("SEMANTIC_INVALID_VECTOR", "Embedding response contains an invalid vector")
            if self.dimensions and len(doc.vector) != self.dimensions:
                raise SemanticError("SEMANTIC_DIMENSION_MISMATCH", "Embedding dimensions do not match the index")
            self.dimensions = self.dimensions or len(doc.vector)
            self._documents[doc.document_id] = {"patent_id": doc.patent_id, "text": doc.text, "vector": doc.vector, "metadata": doc.metadata}
        self._save()

    def delete(self, document_ids: list[str]) -> None:
        for document_id in document_ids:
            self._documents.pop(document_id, None)
        self._save()

    def dense_search(self, vector: list[float], limit: int) -> list[dict]:
        if self.dimensions and len(vector) != self.dimensions:
            raise SemanticError("SEMANTIC_DIMENSION_MISMATCH", "Query dimensions do not match the index")
        norm = math.sqrt(sum(x * x for x in vector))
        if not norm:
            return []
        matches = []
        for document_id, item in self._documents.items():
            other = item["vector"]
            other_norm = math.sqrt(sum(x * x for x in other))
            score = sum(x * y for x, y in zip(vector, other)) / (norm * other_norm) if other_norm else 0.0
            matches.append({"document_id": document_id, "patent_id": item["patent_id"], "score": score, "text": item["text"], "metadata": item["metadata"]})
        return sorted(matches, key=lambda item: (-item["score"], item["document_id"]))[:limit]

    def count(self) -> int:
        return len(self._documents)
