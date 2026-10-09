"""Document-specific facts under one application Wiki."""
from copy import deepcopy
from datetime import date, datetime
from types import SimpleNamespace
import json
import re

from app.models import Patent, PatentHistory
from sqlalchemy import String
from app.services.patent_identity_service import normalize_publication_number

DOCUMENT_FIELDS = {
    "application_number", "publication_number", "grant_number", "title", "abstract", "claims",
    "description_full", "applicant", "inventor", "assignee", "agent", "filing_date",
    "publication_date", "grant_date", "priority_date", "priority_number", "priority_country",
    "country", "patent_type", "legal_status", "legal_status_date", "legal_status_details",
    "ipc_main", "ipc_all", "cpc_main", "cpc_all",
}


def document_kind(number):
    match = re.search(r"([A-Z])\d?$", number or "")
    return "grant" if match and match[1] in {"B", "C", "E", "S", "Y"} else "publication"


def serial(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return getattr(value, "value", value)


def seed_versions(patent):
    versions = deepcopy(patent.publication_versions or {})
    number = normalize_publication_number(patent.publication_number or patent.grant_number)
    if number and number not in versions:
        versions[number] = {"kind": document_kind(number), "fields": {
            key: serial(getattr(patent, key, None)) for key in DOCUMENT_FIELDS
        }, "source": "legacy_current", "data_available": True}
    grant = normalize_publication_number(patent.grant_number)
    if grant and grant not in versions:
        versions[grant] = {"kind": "grant", "fields": {"publication_number": grant,
            "grant_number": grant, "application_number": patent.application_number, "country": patent.country},
            "source": "identifier_only", "data_available": False}
    return versions


def save_document(patent, values, *, number=None, source="manual", db=None, batch_id=None):
    number = normalize_publication_number(number or values.get("publication_number") or values.get("grant_number"))
    if not number:
        return
    versions = seed_versions(patent)
    old = versions.get(number)
    fields = dict((old or {}).get("fields") or {})
    fields.update({key: serial(value) for key, value in values.items() if key in DOCUMENT_FIELDS})
    fields["publication_number"] = number
    if document_kind(number) == "grant":
        fields["grant_number"] = number
    new = {"kind": document_kind(number), "fields": fields, "source": source,
           "data_available": bool(fields.get("title")), "batch_id": batch_id}
    versions[number] = new
    patent.publication_versions = versions
    if db is not None and (old or {}).get("fields") != fields:
        db.add(PatentHistory(patent_id=patent.id, field_key=f"publication_versions.{number}",
            field_display_name=number, old_value=json.dumps(old, ensure_ascii=False) if old else None,
            new_value=json.dumps(new, ensure_ascii=False), source="document_version", import_batch_id=batch_id))


def project_document(patent, number, versions=None):
    versions = versions if versions is not None else seed_versions(patent)
    document = versions.get(number)
    if not document:
        return patent
    values = {column.key: getattr(patent, column.key) for column in Patent.__table__.columns}
    for key in DOCUMENT_FIELDS:
        values[key] = document["fields"].get(key)
        if values[key] is not None and key.endswith("_date"):
            values[key] = date.fromisoformat(str(values[key])[:10])
        enum_type = getattr(Patent.__table__.c[key].type, "enum_class", None)
        if enum_type and values[key] is not None:
            values[key] = enum_type(values[key])
    values["title"] = values.get("title") or patent.title
    for key in ("tags", "projects", "family", "family_size", "family_key", "database_ids", "database_names"):
        values[key] = getattr(patent, key, None)
    values["database_ids"] = values["database_ids"] or []
    values["database_names"] = values["database_names"] or []
    values.update(publication_versions=versions, document_number=number, document_kind=document["kind"],
                  row_key=f"{patent.id}:{number}", version_data_available=document.get("data_available", True))
    return SimpleNamespace(**values)


def present_patents(patents, config, *, group_by_family=False, expanded_families=()):
    rows = []
    for patent in patents:
        versions = seed_versions(patent)
        if not versions:
            rows.append(patent)
            continue
        numbers = sorted(versions, key=lambda number: (
            versions[number]["kind"] != config.get("preferred_version", "grant"),
            str(versions[number]["fields"].get("publication_date") or ""), number))
        if config.get("application_mode", "merged") == "merged":
            numbers = numbers[:1]
        rows.extend(project_document(patent, number, versions) for number in numbers)
    if group_by_family and config.get("family_representative"):
        groups = {}
        for row in rows:
            groups.setdefault(("family", row.family_id) if row.family_id else ("patent", row.id), []).append(row)
        countries = config.get("country_order", ["CN", "US", "EP", "JP", "DE", "CA", "AU"])
        ranks = {country: index for index, country in enumerate(countries)}
        result = []
        for key, members in groups.items():
            if key[0] == "patent":
                result.extend(members)
                continue
            if key[0] == "family" and key[1] in expanded_families:
                result.extend(members)
                continue
            def rank(row):
                raw_date = row.publication_date or (row.grant_date if getattr(row, "document_kind", None) == "grant" else None)
                try:
                    ordinal = date.fromisoformat(str(raw_date)[:10]).toordinal() if raw_date else None
                except ValueError:
                    ordinal = None
                date_rank = (ordinal if config.get("representative_date") == "earliest" else -ordinal) if ordinal is not None else float("inf")
                return ranks.get(row.country, len(ranks)), date_rank, row.id, getattr(row, "document_number", "")
            result.append(min(members, key=rank))
        return result
    return rows


def backfill_versions(db):
    from app.models import ImportSourceRow, FieldObservation, PatentIdentifier
    for patent in db.query(Patent).filter(Patent.publication_versions.is_(None) |
            (Patent.publication_versions.cast(String) == "null") | (Patent.publication_versions == {})).all():
        patent.publication_versions = seed_versions(patent)
        rows = db.query(ImportSourceRow).filter(ImportSourceRow.patent_id == patent.id, ImportSourceRow.resolution_status == "resolved").order_by(ImportSourceRow.id).all()
        for row in rows:
            observations = db.query(FieldObservation).filter(FieldObservation.source_row_id == row.id, FieldObservation.canonical_field_key.in_(DOCUMENT_FIELDS), FieldObservation.field_resolution == "mapped").order_by(FieldObservation.id).all()
            values = {item.canonical_field_key: item.candidate_value for item in observations if item.candidate_value is not None and item.final_decision not in {"ignore", "quarantine"}}
            if values.get("publication_number") or values.get("grant_number"):
                save_document(patent, values, source="retained_import", batch_id=row.import_batch_id)
        versions = dict(patent.publication_versions or {})
        for identifier in db.query(PatentIdentifier).filter(PatentIdentifier.patent_id == patent.id, PatentIdentifier.identifier_type.in_(["publication", "grant"])).all():
            number = normalize_publication_number(identifier.normalized_value)
            if number and number not in versions:
                versions[number] = {"kind": document_kind(number), "fields": {"publication_number": number, "application_number": patent.application_number, "country": patent.country}, "source": "identifier_only", "data_available": False}
        patent.publication_versions = versions
    db.commit()


def matches_document_filters(row, filters):
    from app.services.patent_service import _parse_filter_condition, FILTER_EMPTY_TOKEN
    for key, condition in filters.items():
        parsed = _parse_filter_condition(condition)
        if not parsed:
            continue
        operator, expected = parsed
        actual = str(serial(getattr(row, key, None)) or "").lower()
        expected_text = str(expected or "").lower()
        checks = {"contains": expected_text in actual, "eq": actual == expected_text,
            "starts_with": actual.startswith(expected_text), "ends_with": actual.endswith(expected_text),
            "is_empty": not actual, "is_not_empty": bool(actual)}
        if operator == "in":
            options = expected if isinstance(expected, list) else [expected]
            if not any(actual == ("" if item is None or item == FILTER_EMPTY_TOKEN else str(item).lower()) for item in options):
                return False
        elif not checks.get(operator, True):
            return False
    return True
