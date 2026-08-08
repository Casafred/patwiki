import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.search import router
from app.database import Base, get_db
from app.models import Patent, PatentDatabase


class SearchSuggestApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        db_one = PatentDatabase(name="库一", code="db-one")
        db_two = PatentDatabase(name="库二", code="db-two")
        self.db.add_all([db_one, db_two])
        self.db.flush()
        self.db.add_all([
            Patent(
                title="智能传感器控制方法",
                application_number="CN202410001234.5",
                applicant="甲科技",
                category="传感器",
                database_id=db_one.id,
            ),
            Patent(
                title="智能传感器结构",
                application_number="CN202410009999.1",
                applicant="乙科技",
                category="结构",
                database_id=db_two.id,
            ),
        ])
        self.db.commit()

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.database_id = db_one.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_suggests_distinct_values_and_respects_database(self):
        response = self.client.get("/search/suggest", params={"q": "智能", "database_id": self.database_id})
        self.assertEqual(response.status_code, 200)
        values = response.json()
        self.assertTrue(values)
        self.assertEqual(values[0]["kind"], "title")
        self.assertEqual(values[0]["patent_title"], "智能传感器控制方法")
        self.assertTrue(all(item["patent_title"] != "智能传感器结构" for item in values))

    def test_empty_query_returns_empty_list(self):
        response = self.client.get("/search/suggest", params={"q": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])


if __name__ == "__main__":
    unittest.main()
