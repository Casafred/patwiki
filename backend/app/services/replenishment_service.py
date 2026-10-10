"""Read-only, document-level inventory of missing patent facts."""
from io import BytesIO

import pandas as pd
from sqlalchemy.orm import selectinload

from app.models import Patent, PatentDatabase
from app.services.export_service import ExportService, MAX_EXPORT_ROWS
from app.services.field_registry import get_system_field_meta
from app.services.patent_database_scope import in_database
from app.services.patent_identity_service import normalize_publication_number
from app.services.publication_version_service import seed_versions
from app.services.relation_service import parse_patent_numbers


class ReplenishmentService:
    MAIN_FIELDS = (
        "title", "application_number", "abstract", "claims", "description_full",
        "applicant", "inventor", "filing_date", "publication_date", "country",
        "patent_type", "legal_status", "ipc_main",
    )
    FAMILY_FIELDS = (
        "family_members", "family_patents", "family_publication_numbers",
        "同族专利号", "同族公开号",
    )

    @staticmethod
    def _has_fact(value):
        value = getattr(value, "value", value)
        if value is None:
            return False
        if isinstance(value, str):
            value = value.strip()
            if not value or value in {"待补全", "未知", "unknown", "缺失"}:
                return False
        return True

    @classmethod
    def collect(cls, db, database_id=None):
        if database_id is not None and not db.get(PatentDatabase, database_id):
            raise ValueError("数据库不存在")
        query = db.query(Patent).filter(Patent.deleted_at.is_(None))
        if database_id is not None:
            query = query.filter(in_database(database_id))
        patents = query.options(selectinload(Patent.identifiers)).limit(MAX_EXPORT_ROWS + 1).all()
        if len(patents) > MAX_EXPORT_ROWS:
            raise ValueError("当前库专利超过 200,000 条，暂不支持一键补库")

        facts = {}

        def include(raw_number):
            number = normalize_publication_number(raw_number)
            if number:
                facts.setdefault(number, set())
                if len(facts) > MAX_EXPORT_ROWS:
                    raise ValueError("补库清单超过 200,000 条，暂不支持导出")
            return number

        def include_relations(patent):
            for key in cls.FAMILY_FIELDS:
                for number in parse_patent_numbers((patent.custom_fields or {}).get(key)):
                    include(number)

        for patent in patents:
            include_relations(patent)
            for identifier in patent.identifiers:
                if identifier.identifier_type in {"publication", "grant"}:
                    include(identifier.normalized_value)
            for raw_number, document in seed_versions(patent).items():
                number = include(raw_number)
                if not number or not document.get("data_available", True):
                    continue
                values = document.get("fields") or {}
                facts[number].update(
                    key for key in cls.MAIN_FIELDS if cls._has_fact(values.get(key))
                    and not (patent.title == "待补全" and key in {"country", "patent_type"})
                )

        # Family members outside this library are candidates, but their facts
        # do not count as information entered in the current library.
        family_ids = query.with_entities(Patent.family_id).filter(Patent.family_id.isnot(None))
        members = db.query(Patent).filter(
            Patent.deleted_at.is_(None), Patent.family_id.in_(family_ids),
        ).options(selectinload(Patent.identifiers)).yield_per(1000)
        for member in members:
            include_relations(member)
            for number in seed_versions(member):
                include(number)
            for identifier in member.identifiers:
                if identifier.identifier_type in {"publication", "grant"}:
                    include(identifier.normalized_value)

        return [
            {"publication_number": number,
             "missing_fields": [key for key in cls.MAIN_FIELDS if key not in present]}
            for number, present in sorted(facts.items()) if len(present) < len(cls.MAIN_FIELDS)
        ]

    @classmethod
    def export_excel(cls, db, database_id=None):
        entries = cls.collect(db, database_id)
        if not entries:
            raise ValueError("当前库及其同族暂无需要补全的公开号")
        labels = [(get_system_field_meta(key) or {"name": "说明书全文"})["name"]
                  for key in cls.MAIN_FIELDS]
        rows = [[entry["publication_number"], *(
            "缺失" if key in entry["missing_fields"] else "" for key in cls.MAIN_FIELDS
        )] for entry in entries]
        dataframe = pd.DataFrame(rows, columns=["公开号", *labels])
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            dataframe.to_excel(writer, index=False, sheet_name="补库清单")
            sheet = writer.book["补库清单"]
            ExportService._format_sheet(sheet, dataframe)
            sheet.column_dimensions["A"].width = 25
            for column in list(sheet.columns)[1:]:
                sheet.column_dimensions[column[0].column_letter].width = 16
        return output.getvalue()
