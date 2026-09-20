"""Vector-store implementations selected only at the infrastructure boundary."""
from pathlib import Path

from app.search.contracts import SemanticError
from app.search.vector.json_local import JsonLocalVectorStore
from app.search.vector.zvec_store import ZvecVectorStore


def open_vector_store(backend: str, root: Path, dimensions: int | None):
    if backend == "zvec":
        return ZvecVectorStore(root / "zvec", dimensions or 0)
    if backend == "json_local":
        return JsonLocalVectorStore(root / "index.json", dimensions)
    raise SemanticError("SEMANTIC_BACKEND_UNAVAILABLE", f"Unsupported vector backend: {backend}")
