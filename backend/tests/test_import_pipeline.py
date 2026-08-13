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

    def test_mapping_validation_allows_skipped_columns_and_proposed_keys(self):
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
                ["标题", "跳过列", "公式列", "附件列", "提议列"],
                {
                    "标题": "title",
                    "公式列": "cf_formula",
                    "附件列": "attachments",
                    "提议列": "cf_proposed_abc123",
                },
                db,
            )
            # 跳过列（空目标）和提议的 cf_ key 都不应阻断导入
            self.assertEqual({issue["column"] for issue in issues}, {"公式列", "附件列"})
            self.assertIn("attachments", {field["key"] for field in get_all_fields_meta(db)})
        finally:
            db.close()
            engine.dispose()

    def test_priority_number_mapping_validates_after_system_field_registration(self):
        # 回归：'优先权号' -> 'priority_number' 之前因 priority_number 未注册到
        # SYSTEM_FIELD_KEYS 而被 validate_mapping 误判为"目标字段不存在"，
        # 导致整批导入被阻断。
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            issues = ImportService.validate_mapping(
                ["标题", "优先权号", "优先权国家", "优先权日", "CPC分类号", "风险描述"],
                {
                    "标题": "title",
                    "优先权号": "priority_number",
                    "优先权国家": "priority_country",
                    "优先权日": "priority_date",
                    "CPC分类号": "cpc_main",
                    "风险描述": "risk_description",
                },
                db,
            )
            self.assertEqual(issues, [])
        finally:
            db.close()
            engine.dispose()

    def test_suggest_mapping_does_not_fuzzy_match_family_columns(self):
        # "同族备注" 不能因为名字里带"同族"就被塞进同族关系映射，
        # 应当作为普通自定义字段（cf_ 提议）呈现。
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            mapping, issues = ImportService.suggest_mapping(
                ["同族专利号", "同族备注", "同族申请日", "标题"],
                db,
            )
            self.assertEqual(mapping["同族专利号"], "family_members")
            self.assertEqual(mapping["标题"], "title")
            # 同族备注 / 同族申请日 应是 cf_ 提议，而非 family_members
            self.assertTrue(mapping["同族备注"].startswith("cf_"))
            self.assertTrue(mapping["同族申请日"].startswith("cf_"))
            self.assertNotEqual(mapping["同族备注"], "family_members")
            self.assertNotEqual(mapping["同族申请日"], "family_members")
            # 预览阶段不应实际写库
            self.assertEqual(db.query(CustomField).count(), 0)
            self.assertEqual(issues, [])
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
