import unittest
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.form import router as form_router
from app.api.views import router as views_router
from app.database import Base, get_db
from app.models import CustomField, CustomFieldType, Patent, PatentDatabase, PatentHistory, PatentView


class FormGanttApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        database = PatentDatabase(name="视图测试库", code="VIEW_TEST")
        self.db.add(database)
        self.db.flush()
        self.database_id = database.id
        self.db.add(CustomField(
            key="cf_owner_note",
            name="负责人备注",
            field_type=CustomFieldType.TEXT,
        ))
        self.db.flush()
        self.form_view = PatentView(
            name="录入表单",
            database_id=database.id,
            layout_type="form",
            form_config={
                "layout": "two_column",
                "sections": [{"title": "基本信息", "fields": [
                    {"key": "title", "required": True, "col_span": 2},
                    {"key": "applicant"},
                    {"key": "filing_date"},
                    {"key": "cf_owner_note"},
                ]}],
            },
        )
        self.gantt_view = PatentView(
            name="申请周期",
            database_id=database.id,
            layout_type="gantt",
            gantt_config={
                "start_field": "filing_date",
                "end_field": "grant_date",
                "title_field": "title",
                "group_by_field": "applicant",
                "bar_color_field": "risk_level",
                "bar_color_map": {"high": "#dc2626"},
            },
        )
        self.db.add_all([self.form_view, self.gantt_view])
        self.db.flush()
        self.db.add_all([
            Patent(
                title="已授权专利",
                applicant="甲公司",
                database_id=database.id,
                filing_date=date(2024, 1, 10),
                grant_date=date(2025, 3, 20),
                risk_level="high",
                custom_fields={"cf_owner_note": "旧备注", "cf_unlisted": "保留值"},
            ),
            Patent(
                title="缺少结束日期",
                applicant="甲公司",
                database_id=database.id,
                filing_date=date(2024, 2, 1),
            ),
        ])
        self.db.commit()

        app = FastAPI()
        app.include_router(views_router)
        app.include_router(form_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_form_submission_share_and_public_submission(self):
        definition = self.client.get(f"/views/{self.form_view.id}/form")
        self.assertEqual(definition.status_code, 200)
        self.assertEqual(definition.json()["config"]["sections"][0]["fields"][0]["key"], "title")

        created = self.client.post(f"/views/{self.form_view.id}/form/submit", json={
            "data": {"title": "表单新增专利", "filing_date": "2026-01-02", "applicant": "乙公司"},
        })
        self.assertEqual(created.status_code, 200)
        patent_id = created.json()["patent_id"]
        patent = self.db.query(Patent).filter(Patent.id == patent_id).one()
        self.assertEqual(patent.filing_date, date(2026, 1, 2))

        existing_patent = self.db.query(Patent).filter(Patent.title == "已授权专利").one()
        edited = self.client.post(f"/views/{self.form_view.id}/form/submit", json={
            "patent_id": existing_patent.id,
            "data": {"title": "表单编辑专利", "cf_owner_note": "新备注"},
        })
        self.assertEqual(edited.status_code, 200)
        self.db.refresh(existing_patent)
        self.assertEqual(existing_patent.custom_fields["cf_owner_note"], "新备注")
        self.assertEqual(existing_patent.custom_fields["cf_unlisted"], "保留值")

        missing = self.client.post(f"/views/{self.form_view.id}/form/submit", json={"data": {}})
        self.assertEqual(missing.status_code, 400)
        self.assertIn("必填", missing.json()["detail"])

        link = self.client.post(f"/views/{self.form_view.id}/form/share", json={"expires_days": 2})
        self.assertEqual(link.status_code, 200)
        token = link.json()["token"]
        public_definition = self.client.get(f"/form/shared/{token}")
        self.assertEqual(public_definition.status_code, 200)
        self.assertTrue(public_definition.json()["public"])

        public_submit = self.client.post(f"/form/shared/{token}/submit", json={
            "data": {"title": "公开提交专利", "applicant": "丙公司"},
        })
        self.assertEqual(public_submit.status_code, 200)

    def test_gantt_data_skips_incomplete_rows_and_updates_dates(self):
        data = self.client.get(f"/views/{self.gantt_view.id}/gantt")
        self.assertEqual(data.status_code, 200)
        payload = data.json()
        self.assertEqual(payload["returned"], 1)
        item = payload["groups"][0]["items"][0]
        self.assertEqual(item["color"], "#dc2626")
        self.assertEqual(payload["time_range"]["start"], "2024-01-10")

        updated = self.client.post(f"/views/{self.gantt_view.id}/gantt/update-dates", json={
            "patent_id": item["id"],
            "new_start": "2024-02-01",
            "new_end": "2025-04-01",
        })
        self.assertEqual(updated.status_code, 200)
        patent = self.db.query(Patent).filter(Patent.id == item["id"]).one()
        self.assertEqual(patent.filing_date, date(2024, 2, 1))
        self.assertEqual(patent.grant_date, date(2025, 4, 1))
        self.assertGreaterEqual(self.db.query(PatentHistory).filter(PatentHistory.patent_id == patent.id).count(), 2)


if __name__ == "__main__":
    unittest.main()
