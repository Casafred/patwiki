import unittest
from io import BytesIO

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.core.exceptions import BadRequestException
from app.models import CustomField, CustomFieldType, Patent, PatentDatabase
from app.services.field_registry import get_all_fields_meta
from app.services.import_service import ImportService
from app.services.relation_service import parse_patent_numbers, process_family_members


class ImportPipelineTest(unittest.TestCase):
    def test_family_numbers_accept_common_delimiters_and_dedupe(self):
        raw = " US12304034B2 | CN209954561U；EP3468749B1 / US12304034B2\\CN209954561U\n"
        self.assertEqual(parse_patent_numbers(raw), [
            "US12304034B2",
            "CN209954561U",
            "EP3468749B1",
        ])

    def test_csv_preview_is_case_insensitive_and_keeps_headers(self):
        content = "标题,同族列\n设备,US12304034B2 | CN209954561U\n".encode("utf-8-sig")
        frame, columns = ImportService.parse_excel(content, "patents.CSV")
        self.assertEqual(columns, ["标题", "同族列"])
        self.assertEqual(frame.iloc[0]["同族列"], "US12304034B2 | CN209954561U")

    def test_xlsx_preview_and_invalid_uploads_return_actionable_errors(self):
        output = BytesIO()
        pd.DataFrame({"标题": ["设备"]}).to_excel(output, index=False)
        frame, columns = ImportService.parse_excel(output.getvalue(), "patents.XLSX")
        self.assertEqual(columns, ["标题"])
        self.assertEqual(frame.iloc[0]["标题"], "设备")

        with self.assertRaisesRegex(BadRequestException, "仅支持"):
            ImportService.parse_excel(b"data", "patents.pdf")
        with self.assertRaisesRegex(BadRequestException, "上传文件为空"):
            ImportService.parse_excel(b"", "patents.xlsx")

    def test_family_column_mapping_includes_export_variants(self):
        from app.services.import_service import STANDARD_FIELD_MAPPINGS

        self.assertEqual(STANDARD_FIELD_MAPPINGS["同族列"], "family_members")
        self.assertEqual(STANDARD_FIELD_MAPPINGS["family members"], "family_members")

    def test_family_members_are_created_and_linked_in_database_scope(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            database = PatentDatabase(name="测试库")
            current = Patent(
                title="主专利",
                application_number="US12304034B2",
                country="US",
                database=database,
            )
            db.add_all([database, current])
            db.commit()

            result = process_family_members(
                db,
                current,
                parse_patent_numbers("CN209954561U | EP3468749B1"),
                database_id=database.id,
            )
            db.commit()

            self.assertIsNotNone(result["family_id"])
            members = db.query(Patent).filter(
                Patent.database_id == database.id,
                Patent.family_id == current.family_id,
            ).all()
            self.assertEqual(len(members), 3)
            self.assertEqual(
                {member.application_number or member.publication_number for member in members},
                {"US12304034B2", "CN209954561U", "EP3468749B1"},
            )
        finally:
            db.close()
            engine.dispose()

    def test_mapping_validation_preserves_every_source_column(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            field = CustomField(
                key="cf_formula",
                name="计算结果",
                field_type=CustomFieldType.FORMULA,
                is_active=True,
            )
            db.add(field)
            db.commit()

            issues = ImportService.validate_mapping(
                ["标题", "未映射列", "公式列", "附件列"],
                {
                    "标题": "title",
                    "公式列": "cf_formula",
                    "附件列": "attachments",
                },
                db,
            )
            self.assertEqual({issue["column"] for issue in issues}, {"未映射列", "公式列", "附件列"})
            self.assertIn("attachments", {field["key"] for field in get_all_fields_meta(db)})
        finally:
            db.close()
            engine.dispose()

    def test_invalid_dates_are_reported_instead_of_silently_dropped(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            with self.assertRaisesRegex(ValueError, "日期值无法识别"):
                ImportService._row_to_patent_data(
                    {"标题": "测试", "申请日": "not-a-date"},
                    {"标题": "title", "申请日": "filing_date"},
                    db,
                )
        finally:
            db.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
