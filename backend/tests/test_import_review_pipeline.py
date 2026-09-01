import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Citation, ImportBatchStatus, ImportSourceRow, Patent, PatentDatabase, PatentHistory
from app.services.import_service import ImportService
from app.services.field_registry import get_all_fields_meta
from app.services.import_review_service import (
    apply_batch,
    list_batch_changes,
    review_batch,
    rollback_batch,
    stage_import,
)
from app.services.patent_identity_service import ensure_patent_identifiers


class ImportReviewPipelineTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.database = PatentDatabase(name="测试库")
        self.db.add(self.database)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _stage(self, csv_text: str, mapping: dict[str, str], artifact: Path):
        artifact.write_text(csv_text, encoding="utf-8-sig")
        return stage_import(
            self.db,
            content=csv_text.encode("utf-8-sig"),
            filename="input.csv",
            sheet_name=None,
            mapping=mapping,
            database_id=self.database.id,
            artifact_path=str(artifact),
        )

    def test_publication_number_is_required_even_when_application_exists(self):
        with self.assertRaisesRegex(Exception, "公开号"):
            stage_import(
                self.db,
                content="申请号,标题\nCN123,测试\n".encode(),
                filename="input.csv",
                sheet_name=None,
                mapping={"申请号": "application_number", "标题": "title"},
                database_id=self.database.id,
            )

    def test_rows_without_publication_are_retained_for_identity_repair(self):
        with TemporaryDirectory() as temp_dir:
            result = self._stage(
                "公开号,标题,线索\n,待补身份专利,来自邮件\n,,\n",
                {"公开号": "publication_number", "标题": "title", "线索": ""},
                Path(temp_dir) / "pending-identity.csv",
            )
            self.assertEqual(result["quarantined_count"], 0)
            self.assertEqual(result["retained_source_rows"], 1)
            self.assertEqual(result["row_reports"][0]["status"], "retained_source_row")
            self.assertEqual(result["row_reports"][1]["status"], "skipped_empty_row")
            self.assertEqual(self.db.query(Patent).count(), 0)

            source = self.db.query(ImportSourceRow).filter(
                ImportSourceRow.import_batch_id == result["batch_id"],
                ImportSourceRow.source_row == 2,
            ).one()
            self.assertEqual(source.resolution_status, "retained_source_row")
            observations = list_batch_changes(self.db, result["batch_id"])["items"]
            self.assertTrue(any(item["source_field_name"] == "标题" for item in observations))

            review_batch(self.db, result["batch_id"], default_action_name="adopt")
            applied = apply_batch(self.db, result["batch_id"])
            self.assertEqual(applied["created"], 0)
            self.assertEqual(applied["errors"], 0)
            self.assertEqual(self.db.query(Patent).count(), 0)

    def test_stage_does_not_change_existing_and_review_controls_apply_and_rollback(self):
        patent = Patent(
            database_id=self.database.id,
            publication_number="CN123456789A1",
            title="旧标题",
        )
        self.db.add(patent)
        self.db.flush()
        ensure_patent_identifiers(self.db, patent, source_system="test")
        self.db.commit()

        csv_text = "公开号,标题,备注来源\nCN123456789A1,新标题,来源备注\n"
        with TemporaryDirectory() as temp_dir:
            result = self._stage(
                csv_text,
                {"公开号": "publication_number", "标题": "title", "备注来源": ""},
                Path(temp_dir) / "input.csv",
            )
            self.assertEqual(result["status"], ImportBatchStatus.REVIEW_REQUIRED.value)
            self.db.refresh(patent)
            self.assertEqual(patent.title, "旧标题")
            batch_id = result["batch_id"]
            changes = list_batch_changes(self.db, batch_id)
            title = next(item for item in changes["items"] if item["canonical_field_key"] == "title")
            unknown = next(item for item in changes["items"] if item["source_field_name"] == "备注来源")
            review_batch(self.db, batch_id, items=[
                {"observation_id": title["id"], "action": "adopt"},
                {"observation_id": unknown["id"], "action": "keep_existing"},
            ])
            applied = apply_batch(self.db, batch_id)
            self.assertEqual(applied["updated"], 1)
            self.db.refresh(patent)
            self.assertEqual(patent.title, "新标题")
            self.assertTrue(self.db.query(PatentHistory).filter(
                PatentHistory.import_batch_id == batch_id,
                PatentHistory.source == "import",
            ).count())
            pending = {field["name"] for field in get_all_fields_meta(self.db) if field.get("is_temporary")}
            self.assertIn("备注来源", pending)
            rollback_batch(self.db, batch_id)
            self.db.refresh(patent)
            self.assertEqual(patent.title, "旧标题")

    def test_new_patent_uses_publication_anchor_and_unknown_value_is_visible(self):
        csv_text = "公开号,标题,人工字段\nJP01234567A1,日本专利,待确认\n"
        with TemporaryDirectory() as temp_dir:
            result = self._stage(
                csv_text,
                {"公开号": "publication_number", "标题": "title", "人工字段": ""},
                Path(temp_dir) / "input.csv",
            )
            batch_id = result["batch_id"]
            review_batch(self.db, batch_id)
            applied = apply_batch(self.db, batch_id)
            self.assertEqual(applied["created"], 1)
            patent = self.db.query(Patent).filter(Patent.database_id == self.database.id).one()
            self.assertEqual(patent.publication_number, "JP1234567A1")
            changes = list_batch_changes(self.db, batch_id)
            unknown = next(item for item in changes["items"] if item["source_field_name"] == "人工字段")
            self.assertEqual(unknown["patent_id"], patent.id)
            self.assertEqual(unknown["candidate_value"], "待确认")
            rollback_batch(self.db, batch_id)
            self.assertIsNone(self.db.query(Patent).filter(Patent.id == patent.id).first())

    def test_legacy_patent_without_identity_index_is_resolved_before_staging(self):
        patent = Patent(
            database_id=self.database.id,
            publication_number="CN123456789A1",
            title="旧库专利",
        )
        self.db.add(patent)
        self.db.commit()

        with TemporaryDirectory() as temp_dir:
            result = self._stage(
                "公开号,标题\nCN123456789A1,更新标题\n",
                {"公开号": "publication_number", "标题": "title"},
                Path(temp_dir) / "legacy.csv",
            )
            item = next(item for item in list_batch_changes(self.db, result["batch_id"])["items"] if item["canonical_field_key"] == "title")
            self.assertEqual(item["patent_id"], patent.id)

    def test_same_value_adoption_is_visible_in_wiki_history(self):
        patent = Patent(
            database_id=self.database.id,
            publication_number="CN123456789A1",
            title="稳定标题",
        )
        self.db.add(patent)
        self.db.flush()
        ensure_patent_identifiers(self.db, patent, source_system="test")
        self.db.commit()

        with TemporaryDirectory() as temp_dir:
            result = self._stage(
                "公开号,标题\nCN123456789A1,稳定标题\n",
                {"公开号": "publication_number", "标题": "title"},
                Path(temp_dir) / "same.csv",
            )
            changes = list_batch_changes(self.db, result["batch_id"])["items"]
            title = next(item for item in changes if item["canonical_field_key"] == "title")
            review_batch(self.db, result["batch_id"], items=[{
                "observation_id": title["id"], "action": "adopt",
            }])
            apply_batch(self.db, result["batch_id"])
            history = self.db.query(PatentHistory).filter(
                PatentHistory.import_batch_id == result["batch_id"],
                PatentHistory.field_key == "title",
            ).one()
            self.assertEqual(history.old_value, "稳定标题")
            self.assertEqual(history.new_value, "稳定标题")

    def test_duplicate_new_rows_share_one_patent_and_keep_each_source_history(self):
        with TemporaryDirectory() as temp_dir:
            result = self._stage(
                "公开编号,标题\nCN123456789A1,第一来源\nCN123456789A1,第二来源\n",
                {"公开编号": "publication_number", "标题": "title"},
                Path(temp_dir) / "duplicates.csv",
            )
            review_batch(self.db, result["batch_id"], default_action_name="adopt")
            applied = apply_batch(self.db, result["batch_id"])
            self.assertEqual(applied["created"], 1)
            self.assertEqual(self.db.query(Patent).filter(Patent.database_id == self.database.id).count(), 1)
            self.assertEqual(self.db.query(PatentHistory).filter(
                PatentHistory.import_batch_id == result["batch_id"],
                PatentHistory.field_key == "title",
            ).count(), 2)

    def test_relation_projection_keeps_raw_cell_and_links_only_existing_targets(self):
        current = Patent(
            database_id=self.database.id,
            publication_number="CN123456789A1",
            title="当前专利",
        )
        cited = Patent(
            database_id=self.database.id,
            publication_number="US123456789A1",
            title="已存在专利",
        )
        self.db.add_all([current, cited])
        self.db.flush()
        ensure_patent_identifiers(self.db, current, source_system="test")
        ensure_patent_identifiers(self.db, cited, source_system="test")
        self.db.commit()

        with TemporaryDirectory() as temp_dir:
            result = self._stage(
                "公开号,引用专利号\nCN123456789A1,US123456789A1 | EP999999999A1\n",
                {"公开号": "publication_number", "引用专利号": "cited_patents"},
                Path(temp_dir) / "relations.csv",
            )
            changes = list_batch_changes(self.db, result["batch_id"])["items"]
            relation = next(item for item in changes if item["canonical_field_key"] == "cited_patents")
            review_batch(self.db, result["batch_id"], items=[{
                "observation_id": relation["id"], "action": "adopt",
            }])
            applied = apply_batch(self.db, result["batch_id"])
            self.db.refresh(current)
            self.assertEqual(current.custom_fields["cited_patents"], "US123456789A1 | EP999999999A1")
            self.assertEqual(applied["citation_links"], 1)
            self.assertEqual(self.db.query(Citation).count(), 1)
            self.assertIsNone(self.db.query(Patent).filter(Patent.publication_number == "EP999999999A1").first())

    def test_publication_column_alias_is_auto_recognized_but_unknown_columns_remain_unmapped(self):
        mapping, issues = ImportService.suggest_mapping(["公开编号", "未来属性"], self.db)
        self.assertEqual(mapping["公开编号"], "publication_number")
        self.assertEqual(mapping["未来属性"], "")
        self.assertEqual(issues, [])

    def test_datetime_text_is_parsed_as_date(self):
        data, _ = ImportService._row_to_patent_data(
            {"公开号": "CN123456789A1", "申请日": "2005-04-04 00:00:00"},
            {"公开号": "publication_number", "申请日": "filing_date"},
            self.db,
        )
        self.assertEqual(data["filing_date"].isoformat(), "2005-04-04")

    def test_one_bad_field_does_not_quarantine_valid_fields_in_same_row(self):
        with TemporaryDirectory() as temp_dir:
            result = self._stage(
                "公开号,标题,申请日\nCN123456789A1,有效标题,not-a-date\n",
                {"公开号": "publication_number", "标题": "title", "申请日": "filing_date"},
                Path(temp_dir) / "partial.csv",
            )
            self.assertEqual(result["quarantined_count"], 0)
            self.assertEqual(result["field_errors"], 1)
            self.assertEqual(result["row_reports"][0]["status"], "new_review_with_field_errors")

            review_batch(self.db, result["batch_id"], default_action_name="adopt")
            applied = apply_batch(self.db, result["batch_id"])
            self.assertEqual(applied["created"], 1)
            patent = self.db.query(Patent).filter(Patent.database_id == self.database.id).one()
            self.assertEqual(patent.title, "有效标题")
            self.assertIsNone(patent.filing_date)
            changes = list_batch_changes(self.db, result["batch_id"])["items"]
            date_change = next(item for item in changes if item["canonical_field_key"] == "filing_date")
            self.assertEqual(date_change["field_resolution"], "quarantined")

    def test_existing_row_field_error_still_applies_other_valid_fields(self):
        patent = Patent(
            database_id=self.database.id,
            publication_number="CN223344556A1",
            title="旧标题",
        )
        self.db.add(patent)
        self.db.flush()
        ensure_patent_identifiers(self.db, patent, source_system="test")
        self.db.commit()

        with TemporaryDirectory() as temp_dir:
            result = self._stage(
                "公开号,标题,申请日,备注\nCN223344556A1,导入标题,not-a-date,有效备注\n",
                {
                    "公开号": "publication_number",
                    "标题": "title",
                    "申请日": "filing_date",
                    "备注": "notes",
                },
                Path(temp_dir) / "existing-partial.csv",
            )
            review_items = list_batch_changes(self.db, result["batch_id"])["items"]
            review_batch(self.db, result["batch_id"], items=[
                {"observation_id": item["id"], "action": "adopt"}
                for item in review_items
                if item["canonical_field_key"] in {"title", "filing_date", "notes"}
            ])

            # Simulate another edit after review. Only this reviewed field is
            # isolated; the valid notes value must still be applied.
            patent.title = "人工更新标题"
            self.db.commit()
            applied = apply_batch(self.db, result["batch_id"])

            self.db.refresh(patent)
            self.assertEqual(applied["updated"], 1)
            self.assertEqual(applied["errors"], 0)
            self.assertGreaterEqual(applied["field_errors"], 2)
            self.assertEqual(patent.title, "人工更新标题")
            self.assertEqual(patent.notes, "有效备注")
            self.assertIsNone(patent.filing_date)
            self.assertTrue(any(
                item["status"] == "field_conflict" and item["field"] == "title"
                for item in applied["field_error_details"]
            ))

    def test_unregistered_explicit_mapping_is_retained_without_blocking_valid_fields(self):
        """A future/manual column must not make the whole row unimportable."""
        csv_text = "公开号,标题,未来属性\nCN998877665A1,可导入标题,后续治理值\n"
        with TemporaryDirectory() as temp_dir:
            result = self._stage(
                csv_text,
                {
                    "公开号": "publication_number",
                    "标题": "title",
                    "未来属性": "cf_future_not_registered",
                },
                Path(temp_dir) / "future-column.csv",
            )
            self.assertEqual(result["errors"], 0)
            self.assertEqual(result["field_errors"], 0)
            self.assertEqual(len(result["mapping_warnings"]), 1)
            self.assertEqual(result["unmapped_retained"], 1)

            changes = list_batch_changes(self.db, result["batch_id"])["items"]
            title = next(item for item in changes if item["canonical_field_key"] == "title")
            unknown = next(item for item in changes if item["source_field_name"] == "未来属性")
            review_batch(self.db, result["batch_id"], items=[
                {"observation_id": title["id"], "action": "adopt"},
                {"observation_id": unknown["id"], "action": "keep_existing"},
            ])
            applied = apply_batch(self.db, result["batch_id"])

            self.assertEqual(applied["created"], 1)
            patent = self.db.query(Patent).filter(
                Patent.publication_number == "CN998877665A1",
            ).one()
            self.assertEqual(patent.title, "可导入标题")
            self.assertEqual(unknown["candidate_value"], "后续治理值")


if __name__ == "__main__":
    unittest.main()
