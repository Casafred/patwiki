import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Patent, PatentDatabase, PatentView, PatentHistory, Tag
from app.services.patent_service import PatentService
from app.services.view_service import ViewService
from app.core.exceptions import BadRequestException


class BulkCommandTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.source_db = PatentDatabase(name="批量源库", code="BULK_SOURCE")
        self.target_db = PatentDatabase(name="批量目标库", code="BULK_TARGET")
        self.db.add_all([self.source_db, self.target_db])
        self.db.flush()
        self.source_view = PatentView(name="源视图", database_id=self.source_db.id)
        self.target_view = PatentView(name="目标视图", database_id=self.source_db.id)
        self.db.add_all([self.source_view, self.target_view])
        self.db.flush()
        self.patent = Patent(
            title="批量命令测试专利",
            publication_number="CNBULK0001A",
            database_id=self.source_db.id,
            view_id=self.source_view.id,
            custom_fields={"manual_note": "保留"},
        )
        self.other_patent = Patent(
            title="第二条批量命令测试专利",
            publication_number="CNBULK0002A",
            database_id=self.source_db.id,
            view_id=self.source_view.id,
        )
        self.db.add_all([self.patent, self.other_patent])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_bulk_commands_are_atomic_and_keep_identity_rules(self):
        with self.assertRaises(BadRequestException):
            PatentService.bulk_move_database(
                self.db, [self.patent.id, 999999], self.target_db.id,
            )
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.database_id, self.source_db.id)

        moved = PatentService.bulk_move_view(
            self.db, [self.patent.id, self.other_patent.id], self.target_view.id,
        )
        self.assertEqual(moved, 2)
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.view_id, self.target_view.id)

        moved = PatentService.bulk_move_database(
            self.db, [self.patent.id, self.other_patent.id], self.target_db.id,
        )
        self.assertEqual(moved, 2)
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.database_id, self.target_db.id)
        self.assertIsNone(self.patent.view_id)

        copies = PatentService.bulk_duplicate(
            self.db, [self.patent.id], target_database_id=self.target_db.id,
        )
        self.assertEqual(len(copies), 1)
        copy = copies[0]
        self.assertIsNone(copy.application_number)
        self.assertIsNone(copy.publication_number)
        self.assertEqual(copy.duplicate_of, self.patent.id)
        self.assertIn("工作副本", copy.notes)
        self.assertEqual(copy.custom_fields["manual_note"], "保留")

    def test_bulk_update_and_tag_commands_are_atomic_and_audited(self):
        with self.assertRaises(BadRequestException):
            PatentService.bulk_update(
                self.db, [self.patent.id, self.other_patent.id],
                {"risk_level": "high"},
            )
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.title, "批量命令测试专利")

        tag = Tag(name="批量审计标签")
        self.db.add(tag)
        self.db.commit()
        changed = PatentService.bulk_tag(
            self.db, [self.patent.id, self.other_patent.id], [tag.id], mode="add",
        )
        self.assertEqual(changed, 2)
        history = self.db.query(PatentHistory).filter(
            PatentHistory.patent_id == self.patent.id,
            PatentHistory.field_key == "tags",
        ).one()
        self.assertEqual(history.source, "bulk")

    def test_risk_view_adds_product_and_project_projections_without_overwriting_choices(self):
        views = ViewService.ensure_default_business_views(self.db, self.source_db.id)
        risk_view = next(view for view in views if view.template_key == "ip_risk_control")
        initial_keys = {item["key"] for item in risk_view.column_config}
        self.assertIn("product_id", initial_keys)
        self.assertIn("projects", initial_keys)

        risk_view.column_config = [{"key": "title", "visible": True, "width": 500, "order": 0}]
        self.db.add(risk_view)
        self.db.commit()
        ViewService.ensure_default_business_views(self.db, self.source_db.id)
        self.db.refresh(risk_view)
        keys = {item["key"] for item in risk_view.column_config}
        self.assertEqual(risk_view.column_config[0]["width"], 500)
        self.assertIn("product_id", keys)
        self.assertIn("projects", keys)


if __name__ == "__main__":
    unittest.main()
