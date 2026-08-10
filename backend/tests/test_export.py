import unittest
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.export import router
from app.database import Base, get_db
from app.models import Patent, PatentDatabase


class ExportApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        database = PatentDatabase(name="导出测试库", code="EXPORT_TEST")
        self.db.add(database)
        self.db.flush()
        self.db.add_all([
            Patent(title="授权专利", legal_status="granted", database_id=database.id),
            Patent(title="待审专利", legal_status="pending", database_id=database.id),
        ])
        self.db.commit()
        self.database_id = database.id

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_csv_exports_selected_filtered_fields_with_bom(self):
        response = self.client.post("/export/csv", json={
            "database_id": self.database_id,
            "field_keys": ["title", "legal_status"],
            "filters": {"legal_status": {"eq": "granted"}},
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        content = response.content.decode("utf-8-sig")
        self.assertIn("标题,法律状态", content)
        self.assertIn("授权专利,授权", content)
        self.assertNotIn("待审专利", content)

    def test_excel_exports_selected_fields_and_freezes_header(self):
        response = self.client.post("/export/excel", json={
            "database_id": self.database_id,
            "field_keys": ["title"],
        })
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook["专利数据"]
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertEqual(sheet["A1"].value, "标题")
        self.assertEqual(sheet.max_row, 3)


if __name__ == "__main__":
    unittest.main()
