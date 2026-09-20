from __future__ import annotations

from pathlib import Path

from app.search.contracts import SemanticError, VectorDocument


class ZvecVectorStore:
    """Thin adapter: business services never import the Zvec SDK directly."""

    def __init__(self, path: Path, dimensions: int):
        if not dimensions:
            raise SemanticError("SEMANTIC_DIMENSION_MISMATCH", "Zvec index requires embedding dimensions")
        try:
            import zvec
        except Exception as exc:
            raise SemanticError("SEMANTIC_BACKEND_UNAVAILABLE", "Zvec is not available in this installation") from exc
        self.zvec = zvec
        self.path = path
        if path.exists():
            self.collection = zvec.open(str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            schema = zvec.CollectionSchema("patwiki_semantic", vectors=zvec.VectorSchema(
                "embedding", zvec.DataType.VECTOR_FP32, dimensions,
            ))
            self.collection = zvec.create_and_open(str(path), schema)

    @staticmethod
    def _storage_id(document_id: str) -> str:
        # Zvec document IDs are intentionally conservative. The public/stable
        # document ID remains unchanged in SQLite state; only its index key is encoded.
        patent_id = document_id.split(":", 1)[0]
        return f"p{patent_id}_summary_0"

    @staticmethod
    def _patent_id(storage_id: str) -> int:
        return int(storage_id.split("_", 1)[0].removeprefix("p"))

    def upsert(self, documents: list[VectorDocument]) -> None:
        try:
            statuses = self.collection.upsert([self.zvec.Doc(self._storage_id(doc.document_id), vectors={"embedding": doc.vector}) for doc in documents])
            if any(not status.ok() for status in statuses):
                raise SemanticError("SEMANTIC_BACKEND_UNAVAILABLE", "Zvec rejected an index upsert")
        except SemanticError:
            raise
        except Exception as exc:
            raise SemanticError("SEMANTIC_BACKEND_UNAVAILABLE", "Zvec index upsert failed") from exc

    def delete(self, document_ids: list[str]) -> None:
        if not document_ids:
            return
        try:
            self.collection.delete([self._storage_id(document_id) for document_id in document_ids])
        except Exception as exc:
            raise SemanticError("SEMANTIC_BACKEND_UNAVAILABLE", "Zvec index deletion failed") from exc

    def dense_search(self, vector: list[float], limit: int) -> list[dict]:
        try:
            query = self.zvec.Query("embedding", vector=vector)
            docs = self.collection.query(queries=query, topk=limit)
            return [{"document_id": doc.id, "patent_id": self._patent_id(doc.id), "score": float(doc.score or 0), "text": "", "metadata": {}} for doc in docs]
        except Exception as exc:
            raise SemanticError("SEMANTIC_BACKEND_UNAVAILABLE", "Zvec query failed") from exc

    def count(self) -> int:
        try:
            return int(self.collection.stats().doc_count)
        except Exception:
            return 0

    def close(self) -> None:
        self.collection.close()
