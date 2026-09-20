from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from app.models import Patent

TEMPLATE_VERSION = "patent-summary-v1"
CHUNK_STRATEGY_VERSION = "claims-description-v1"


@dataclass(frozen=True)
class SemanticDocument:
    document_id: str
    patent_id: int
    text: str
    content_hash: str
    metadata: dict


def _value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(sorted(str(item).strip() for item in value if str(item).strip()))
    return str(value).strip()


class SemanticDocumentBuilder:
    """Build the Phase-1 patent summary without mutating the source record."""

    @classmethod
    def build_summary(cls, patent: Patent, allowlist: list[str] | None = None) -> SemanticDocument:
        fields = [
            ("TITLE", patent.title), ("ABSTRACT", patent.abstract),
            ("APPLICANT", patent.applicant or patent.assignee), ("INVENTOR", patent.inventor),
            ("CLASSIFICATION", " ".join(filter(None, [patent.ipc_main, patent.ipc_all, patent.cpc_main, patent.cpc_all]))),
            ("LEGAL_STATUS", patent.legal_status),
            ("TECHNICAL_FIELDS", "\n".join(filter(None, [_value(patent.technical_problem), _value(patent.technical_solution), _value(patent.technical_effect), _value(patent.module)]))),
        ]
        for key in sorted(allowlist or []):
            value = (patent.custom_fields or {}).get(key, (patent.ai_fields or {}).get(key))
            if _value(value):
                fields.append((f"FIELD:{key}", _value(value)))
        text = "\n".join(f"[{name}]\n{_value(value)}" for name, value in fields if _value(value))
        metadata = {"document_type": "patent_summary", "database_id": patent.database_id}
        source = json.dumps({"template": TEMPLATE_VERSION, "text": text, "metadata": metadata}, ensure_ascii=False, sort_keys=True)
        return SemanticDocument(f"{patent.id}:patent_summary:0", patent.id, text, hashlib.sha256(source.encode("utf-8")).hexdigest(), metadata)

    @classmethod
    def build_documents(
        cls,
        patent: Patent,
        allowlist: list[str] | None = None,
        *,
        chunk_strategy_version: str = "summary-v1",
        max_chars: int = 1800,
        overlap_chars: int = 200,
        max_chunks_per_section: int = 64,
    ) -> list[SemanticDocument]:
        documents = [cls.build_summary(patent, allowlist)]
        if chunk_strategy_version != CHUNK_STRATEGY_VERSION:
            return documents
        for section, value in (("claims", patent.claims), ("description", patent.description_full)):
            for chunk_index, text in enumerate(cls._chunk_text(_value(value), max_chars, overlap_chars, prefer_numbered=section == "claims")[:max_chunks_per_section]):
                if not text:
                    continue
                document_id = f"{patent.id}:patent_{section}:{chunk_index}"
                metadata = {
                    "document_type": f"patent_{section}",
                    "database_id": patent.database_id,
                    "parent_document_id": f"{patent.id}:patent_summary:0",
                    "chunk_index": chunk_index,
                    "chunk_strategy_version": chunk_strategy_version,
                }
                source = json.dumps({"text": text, "metadata": metadata}, ensure_ascii=False, sort_keys=True)
                documents.append(SemanticDocument(document_id, patent.id, text, hashlib.sha256(source.encode("utf-8")).hexdigest(), metadata))
        return documents

    @staticmethod
    def _chunk_text(text: str, max_chars: int, overlap_chars: int, *, prefer_numbered: bool = False) -> list[str]:
        if not text:
            return []
        max_chars = max(200, max_chars)
        overlap_chars = max(0, min(overlap_chars, max_chars // 3))
        if prefer_numbered:
            numbered = [part.strip() for part in re.split(r"(?=\d+[.)][ \t]+)", text) if part.strip()]
            paragraphs = numbered or [text]
        else:
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n+|\r\n\s*\r\n+", text) if part.strip()]
        if not paragraphs:
            paragraphs = [text]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            pieces = [paragraph[index:index + max_chars] for index in range(0, len(paragraph), max_chars - overlap_chars)] if len(paragraph) > max_chars else [paragraph]
            for piece in pieces:
                if prefer_numbered:
                    chunks.append(piece)
                    continue
                if current and len(current) + 1 + len(piece) <= max_chars:
                    current = f"{current}\n{piece}"
                else:
                    if current:
                        chunks.append(current)
                    current = piece
        if current:
            chunks.append(current)
        return chunks
