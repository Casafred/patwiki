"""专利身份解析、索引和冲突检测。

规则：
* Patent 的三个号码字段仍是兼容投影，身份索引是独立可追溯事实；
* 规范化只用于匹配，永远不覆盖 raw_value；
* 一个输入行的多个号码命中多个 Patent 时必须隔离，不能猜测合并；
* 同族关系只建立关联，不参与身份合并。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.models import Patent, PatentIdentifier


OFFICIAL_IDENTIFIER_TYPES = ("application", "publication", "grant")
_KIND_CODE_RE = re.compile(r"(?P<kind>[A-Z]{1,3}\d{0,2})$")
_JURISDICTION_RE = re.compile(r"^(?P<jurisdiction>[A-Z]{2})(?P<body>.+)$")
_SEPARATOR_RE = re.compile(r"[\s\-_/:.,，、;；()（）\[\]{}]+")


class PatentIdentityConflict(ValueError):
    """一个身份事实已经属于其他 Patent。"""

    def __init__(self, message: str, *, identifier: Optional[str] = None, patent_ids: Iterable[int] = ()):
        super().__init__(message)
        self.identifier = identifier
        self.patent_ids = sorted(set(patent_ids))


@dataclass(frozen=True)
class IdentifierSpec:
    identifier_namespace: str
    identifier_type: str
    raw_value: str
    normalized_value: str
    jurisdiction_code: Optional[str]
    kind_code: Optional[str]


def _clean_identifier(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    value = unicodedata.normalize("NFKC", str(raw_value)).strip().upper()
    # 分隔符只属于展示格式；来源原文在 raw_value、ImportSourceRow 和 FieldObservation 中保留。
    return _SEPARATOR_RE.sub("", value)


def _parse_parts(normalized: str, default_jurisdiction: Optional[str]) -> tuple[str, Optional[str], Optional[str]]:
    jurisdiction = None
    body = normalized
    match = _JURISDICTION_RE.match(normalized)
    if match:
        jurisdiction = match.group("jurisdiction")
        body = match.group("body")
    elif default_jurisdiction:
        jurisdiction = _clean_identifier(default_jurisdiction)[:10] or None
        if jurisdiction and normalized and not normalized.startswith(jurisdiction):
            normalized = jurisdiction + normalized
            body = normalized[len(jurisdiction):]

    kind_code = None
    kind_match = _KIND_CODE_RE.search(body)
    if kind_match and any(char.isdigit() for char in kind_match.group("kind")):
        kind_code = kind_match.group("kind")
    return normalized, jurisdiction, kind_code


def normalize_identifier(raw_value: Any, default_jurisdiction: Optional[str] = None) -> str:
    """返回仅用于比较的规范化号码，不改变来源字符串。"""
    normalized = _clean_identifier(raw_value)
    if not normalized:
        return ""
    normalized, _, _ = _parse_parts(normalized, default_jurisdiction)
    # 纯短数字通常是表内序号，不能伪造为官方身份。
    if normalized.isdigit() and len(normalized) < 4:
        return ""
    return normalized


def parse_identifier(
    raw_value: Any,
    identifier_type: str,
    default_jurisdiction: Optional[str] = None,
    *,
    identifier_namespace: str = "official",
) -> Optional[IdentifierSpec]:
    """解析一个号码；无法形成稳定身份时返回 None。"""
    if identifier_type not in (*OFFICIAL_IDENTIFIER_TYPES, "external"):
        raise ValueError(f"不支持的专利身份类型：{identifier_type}")
    raw = "" if raw_value is None else str(raw_value).strip()
    normalized = normalize_identifier(raw, default_jurisdiction)
    if not raw or not normalized:
        return None
    normalized, jurisdiction, kind_code = _parse_parts(normalized, default_jurisdiction)
    if identifier_type == "external":
        jurisdiction = jurisdiction or None
    return IdentifierSpec(
        identifier_namespace=identifier_namespace,
        identifier_type=identifier_type,
        raw_value=raw,
        normalized_value=normalized,
        jurisdiction_code=jurisdiction,
        kind_code=kind_code,
    )


def identifier_specs_from_values(
    values: dict[str, Any],
    default_jurisdiction: Optional[str] = None,
    *,
    identifier_namespace: str = "official",
) -> list[IdentifierSpec]:
    specs: list[IdentifierSpec] = []
    for identifier_type in OFFICIAL_IDENTIFIER_TYPES:
        spec = parse_identifier(
            values.get(identifier_type) or values.get(f"{identifier_type}_number"),
            identifier_type,
            default_jurisdiction,
            identifier_namespace=identifier_namespace,
        )
        if spec:
            specs.append(spec)
    return specs


def _specs_for_patent(patent: Patent) -> list[IdentifierSpec]:
    return identifier_specs_from_values(
        {
            "application": patent.application_number,
            "publication": patent.publication_number,
            "grant": patent.grant_number,
        },
        patent.country,
    )


def find_patents_by_identifiers(db: Session, specs: Iterable[IdentifierSpec]) -> list[Patent]:
    patent_ids: set[int] = set()
    for spec in specs:
        rows = db.query(PatentIdentifier).filter(
            PatentIdentifier.identifier_namespace == spec.identifier_namespace,
            PatentIdentifier.identifier_type == spec.identifier_type,
            PatentIdentifier.normalized_value == spec.normalized_value,
            PatentIdentifier.jurisdiction_code == spec.jurisdiction_code,
        ).all()
        patent_ids.update(row.patent_id for row in rows)
    if not patent_ids:
        return []
    return db.query(Patent).filter(Patent.id.in_(sorted(patent_ids))).order_by(Patent.id).all()


def _add_raw_value(identifier: PatentIdentifier, raw_value: str) -> None:
    values = list(identifier.raw_values or [])
    if identifier.raw_value and identifier.raw_value not in values:
        values.insert(0, identifier.raw_value)
    if raw_value and raw_value not in values:
        values.append(raw_value)
    identifier.raw_values = values
    # 首次写入的 raw_value 作为稳定展示值，原始别名在 raw_values 中累计。


def ensure_patent_identifiers(
    db: Session,
    patent: Patent,
    *,
    additional_specs: Iterable[IdentifierSpec] = (),
    source_system: Optional[str] = None,
    source_timestamp: Optional[datetime] = None,
) -> list[PatentIdentifier]:
    """为专利补建/更新身份索引，并在跨记录冲突时抛出异常。"""
    specs_by_key: dict[tuple[str, str, Optional[str], str], IdentifierSpec] = {}
    for spec in [*_specs_for_patent(patent), *additional_specs]:
        key = (spec.identifier_namespace, spec.identifier_type, spec.jurisdiction_code, spec.normalized_value)
        specs_by_key[key] = spec

    result: list[PatentIdentifier] = []
    for key, spec in specs_by_key.items():
        existing = db.query(PatentIdentifier).filter(
            PatentIdentifier.identifier_namespace == spec.identifier_namespace,
            PatentIdentifier.identifier_type == spec.identifier_type,
            PatentIdentifier.jurisdiction_code == spec.jurisdiction_code,
            PatentIdentifier.normalized_value == spec.normalized_value,
        ).first()
        if existing and existing.patent_id != patent.id:
            raise PatentIdentityConflict(
                f"专利身份 {spec.raw_value} 已属于专利 {existing.patent_id}，当前记录 {patent.id} 不能自动合并",
                identifier=spec.normalized_value,
                patent_ids=(existing.patent_id, patent.id),
            )
        if existing:
            _add_raw_value(existing, spec.raw_value)
            if source_system:
                existing.source_system = source_system
            if source_timestamp:
                existing.source_timestamp = source_timestamp
            result.append(existing)
            continue

        identifier = PatentIdentifier(
            patent_id=patent.id,
            identifier_namespace=spec.identifier_namespace,
            identifier_type=spec.identifier_type,
            raw_value=spec.raw_value,
            raw_values=[spec.raw_value],
            normalized_value=spec.normalized_value,
            jurisdiction_code=spec.jurisdiction_code,
            kind_code=spec.kind_code,
            source_system=source_system,
            source_timestamp=source_timestamp,
            is_primary=not result,
        )
        db.add(identifier)
        result.append(identifier)
    db.flush()
    return result


def backfill_patent_identifiers(db: Session) -> dict[str, Any]:
    """把历史 Patent 号码补建到索引；冲突记录返回给治理/诊断层，不自动合并。"""
    indexed = 0
    conflicts: list[dict[str, Any]] = []
    for patent in db.query(Patent).order_by(Patent.id).all():
        try:
            with db.begin_nested():
                before = db.query(PatentIdentifier).filter(PatentIdentifier.patent_id == patent.id).count()
                ensure_patent_identifiers(db, patent, source_system="legacy_backfill")
                after = db.query(PatentIdentifier).filter(PatentIdentifier.patent_id == patent.id).count()
            if after > before:
                indexed += after - before
        except PatentIdentityConflict as exc:
            conflicts.append({
                "patent_id": patent.id,
                "identifier": exc.identifier,
                "patent_ids": exc.patent_ids,
            })
    return {"indexed": indexed, "conflicts": conflicts}


def list_patent_identifiers(db: Session, patent_id: int) -> list[PatentIdentifier]:
    return db.query(PatentIdentifier).filter(
        PatentIdentifier.patent_id == patent_id,
    ).order_by(
        PatentIdentifier.is_primary.desc(),
        PatentIdentifier.identifier_type,
        PatentIdentifier.id,
    ).all()
