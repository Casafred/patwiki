from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.models import Patent

TEMPLATE_VERSION = "patent-summary-v1"


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
