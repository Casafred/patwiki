import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers

from app.api.attachments import router as attachments_router
from app.api.automation import router as automation_router
from app.api.dashboards import router as dashboards_router
from app.database import Base, get_db
from app.models import (
    Attachment,
    AutomationLog,
    AutomationRule,
    CustomField,
    CustomFieldType,
    Dashboard,
    Patent,
    PatentDatabase,
)
from app.services.attachment_service import AttachmentService
from app.services.automation_service import AutomationEngine
from app.services.dashboard_service import DashboardService
from app.services.patent_service import PatentService
from app.config import settings


class M5ApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.database = PatentDatabase(name="M5 测试库", code="M5_TEST")
        self.db.add(self.database)
        self.db.flush()
        self.patent = Patent(
            database_id=self.database.id,
            title="M5 测试专利",
            legal_status="pending",
            custom_fields={"cf_stage": "new"},
        )
        self.db.add_all([
            self.patent,
            CustomField(key="cf_stage", name="阶段", field_type=CustomFieldType.TEXT),
            CustomField(key="cf_result", name="自动化结果", field_type=CustomFieldType.TEXT),
            CustomField(key="cf_files", name="附件", field_type=CustomFieldType.ATTACHMENT),
        ])
        self.db.commit()

        self.temp_dir = TemporaryDirectory()
        self.previous_files_dir = settings.FILES_DIR
        settings.FILES_DIR = Path(self.temp_dir.name)

        app = FastAPI()
        app.include_router(automation_router)
        app.include_router(attachments_router)
        app.include_router(dashboards_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        settings.FILES_DIR = self.previous_files_dir
        self.temp_dir.cleanup()
        self.db.close()
        self.engine.dispose()

    def test_automation_field_import_and_schedule_triggers(self):
        field_rule = AutomationRule(
            database_id=self.database.id,
            name="字段变更规则",
            trigger_config={"type": "field_changed", "field": "custom_fields.cf_stage"},
            condition_config=[{"field": "custom_fields.cf_stage", "op": "==", "value": "ready"}],
            action_config=[{"type": "set_field", "field": "cf_result", "value": "已处理"}],
        )
        imported_rule = AutomationRule(
            database_id=self.database.id,
            name="导入规则",
            trigger_config={"type": "record_imported"},
            action_config=[{"type": "set_field", "field": "cf_result", "value": "已导入"}],
        )
        scheduled_rule = AutomationRule(
            database_id=self.database.id,
            name="定时规则",
            trigger_config={"type": "schedule", "schedule": "every:1", "interval_minutes": 1},
            action_config=[{"type": "set_field", "field": "cf_result", "value": "已巡检"}],
            last_executed_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=2),
        )
        self.db.add_all([field_rule, imported_rule, scheduled_rule])
        self.db.commit()

        PatentService.update_patent(self.db, self.patent, {"custom_fields": {"cf_stage": "ready"}})
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.custom_fields["cf_result"], "已处理")

        imported = AutomationEngine.on_event(self.db, "record_imported", patent_id=self.patent.id)
        self.assertTrue(any(item["status"] == "success" for item in imported))
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.custom_fields["cf_result"], "已导入")

        scheduled = AutomationEngine.run_scheduled(self.db, database_id=self.database.id)
        schedule_result = next(item for item in scheduled if item["rule_id"] == scheduled_rule.id)
        self.assertEqual(schedule_result["status"], "success", scheduled)
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.custom_fields["cf_result"], "已巡检")
        self.assertGreaterEqual(self.db.query(AutomationLog).count(), 3)

    def test_attachment_lifecycle_keeps_timestamp_and_file_safe(self):
        upload = UploadFile(
            file=BytesIO(b"%PDF-1.7 test"),
            filename="spec.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        metadata = AttachmentService.upload(
            self.db,
            self.database.id,
            self.patent.id,
            "cf_files",
            upload,
            uploaded_by="tester",
        )
        self.assertIsNotNone(metadata["uploaded_at"])
        attachment = self.db.query(Attachment).one()
        self.assertTrue(AttachmentService.path(attachment).exists())
        self.assertEqual(self.patent.custom_fields["cf_files"][0]["uploaded_at"], metadata["uploaded_at"])

        response = self.client.get(f"/attachments/{attachment.id}/download")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-1.7 test")
        self.assertEqual(self.client.delete(f"/attachments/{attachment.id}").status_code, 200)
        self.assertEqual(self.db.query(Attachment).count(), 0)

    def test_dashboard_card_data_and_api_lifecycle(self):
        dashboard = Dashboard(
            database_id=self.database.id,
            name="测试总览",
            layout=DashboardService.normalize_layout([
                {"type": "metric", "title": "专利数", "config": {"field": "id", "aggregation": "count"}},
                {"type": "bar", "title": "法律状态", "config": {"group_by": "legal_status"}},
            ]),
        )
        self.db.add(dashboard)
        self.db.commit()

        data = self.client.get(f"/dashboards/{dashboard.id}/data")
        self.assertEqual(data.status_code, 200)
        self.assertEqual(data.json()["total"], 1)
        self.assertEqual(data.json()["cards"][0]["data"]["value"], 1)
        self.assertEqual(data.json()["cards"][1]["data"]["items"][0]["value"], 1)

        created = self.client.post("/dashboards", json={"database_id": self.database.id, "name": "第二个仪表盘"})
        self.assertEqual(created.status_code, 200)
        dashboard_id = created.json()["id"]
        card = self.client.post(f"/dashboards/{dashboard_id}/cards", json={"type": "metric", "title": "总数"})
        self.assertEqual(card.status_code, 200)
        self.assertEqual(self.client.delete(f"/dashboards/{dashboard_id}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
