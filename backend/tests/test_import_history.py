import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.imports import router
from app.database import Base, get_db
from app.models import ImportBatch, ImportBatchStatus


class ImportHistoryApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.batch = ImportBatch(
            filename="patents.xlsx",
            status=ImportBatchStatus.COMPLETED,
            total_rows=10,
            processed_rows=10,
            inserted_count=7,
            updated_count=2,
            skipped_count=1,
            duplicate_count=2,
            error_count=0,
            errors=None,
        )
        self.db.add(self.batch)
        self.db.commit()

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_list_and_get_batch(self):
        response = self.client.get("/import/batches", params={"status": "completed"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["filename"], "patents.xlsx")
        self.assertIn(response.json()[0]["status"].lower(), {"completed"})
        self.assertEqual(response.json()[0]["skipped_count"], 1)

        detail = self.client.get(f"/import/batches/{self.batch.id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["inserted_count"], 7)

    def test_rejects_unknown_status(self):
        response = self.client.get("/import/batches", params={"status": "unknown"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
