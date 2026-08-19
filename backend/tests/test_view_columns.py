import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.views import router as view_router
from app.database import Base, get_db
from app.models import Patent, PatentDatabase
from app.services.view_service import ViewService


class ViewColumnConfigTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        app = FastAPI()
        app.include_router(view_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_column_config_is_persisted_per_view_without_changing_patent_data(self):
        database = PatentDatabase(name="视图列测试库")
        patent = Patent(
            title="主数据不应被视图配置改写",
            publication_number="CN123456789A1",
            database=database,
        )
        self.db.add_all([database, patent])
        self.db.commit()

        views = ViewService.ensure_default_business_views(self.db, database.id)
        risk_view = next(view for view in views if view.template_key == "risk_meeting_statistics")
        other_view = next(view for view in views if view.template_key == "daily_patent_accumulation")
        original_title = patent.title

        response = self.client.put(
            f"/views/{risk_view.id}",
            json={
                "column_config": [
                    {"key": "title", "visible": True, "width": 420, "order": 0},
                    {"key": "future_manual_field", "visible": False, "width": 180, "order": 1},
                    {"key": "publication_number", "visible": True, "width": 180, "order": 2},
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["column_config"][1]["key"], "future_manual_field")

        stored = self.client.get(f"/views/{risk_view.id}")
        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json()["column_config"][0]["width"], 420)
        self.assertEqual(stored.json()["column_config"][1]["visible"], False)

        other = self.client.get(f"/views/{other_view.id}")
        self.assertEqual(other.status_code, 200)
        self.assertNotEqual(other.json()["column_config"], stored.json()["column_config"])
        self.db.refresh(patent)
        self.assertEqual(patent.title, original_title)

    def test_duplicate_keys_are_rejected(self):
        database = PatentDatabase(name="视图列校验库")
        self.db.add(database)
        self.db.commit()
        view = ViewService.ensure_default_business_views(self.db, database.id)[0]

        response = self.client.put(
            f"/views/{view.id}",
            json={
                "column_config": [
                    {"key": "title", "visible": True, "order": 0},
                    {"key": "title", "visible": False, "order": 1},
                ]
            },
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
