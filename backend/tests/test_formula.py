import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.formula import router
from app.api.meta import router as meta_router
from app.database import Base, get_db
from app.models import CustomField, CustomFieldType, FormulaDependency, Patent
from app.services.patent_service import PatentService


class FormulaApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            CustomField(key="score", name="评分", field_type=CustomFieldType.NUMBER),
            CustomField(key="label", name="标签", field_type=CustomFieldType.TEXT),
        ])
        self.patent = Patent(
            title="公式测试专利",
            applicant="PatWiki",
            legal_status="granted",
            custom_fields={"score": 3, "label": "初始"},
        )
        self.db.add(self.patent)
        self.db.commit()

        app = FastAPI()
        app.include_router(router)
        app.include_router(meta_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_formula_is_created_recalculated_and_incrementally_updated(self):
        created = self.client.post("/formula/fields", json={
            "key": "patent_label",
            "name": "专利标签",
            "expression": 'IF(legal_status == "granted", CONCAT(title, " / ", label), "未授权")',
            "return_type": "text",
        })
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["dependencies"], ["label", "legal_status", "title"])

        self.db.refresh(self.patent)
        self.assertEqual(self.patent.custom_fields["patent_label"], "公式测试专利 / 初始")

        PatentService.update_patent(self.db, self.patent, {"custom_fields": {"label": "更新后"}})
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.custom_fields["patent_label"], "公式测试专利 / 更新后")

    def test_formula_rejects_unsafe_expression_and_cycles(self):
        unsafe = self.client.post("/formula/validate", json={
            "expression": '__import__("os").system("echo bad")',
        })
        self.assertEqual(unsafe.status_code, 200)
        self.assertFalse(unsafe.json()["valid"])

        first = self.client.post("/formula/fields", json={
            "key": "formula_a",
            "name": "公式 A",
            "expression": "score + 1",
            "return_type": "number",
        })
        self.assertEqual(first.status_code, 200)
        second = self.client.post("/formula/fields", json={
            "key": "formula_b",
            "name": "公式 B",
            "expression": "formula_a + 1",
            "return_type": "number",
        })
        self.assertEqual(second.status_code, 200)

        cycle = self.client.put(f"/formula/fields/{first.json()['id']}", json={"expression": "formula_b + 1"})
        self.assertEqual(cycle.status_code, 400)
        self.assertIn("循环依赖", cycle.json()["detail"])

    def test_existing_field_can_convert_to_formula_and_dependents_recalculate(self):
        first = self.client.post("/formula/fields", json={
            "key": "formula_a",
            "name": "公式 A",
            "expression": "score + 1",
            "return_type": "number",
        })
        self.assertEqual(first.status_code, 200)
        second = self.client.post("/formula/fields", json={
            "key": "formula_b",
            "name": "公式 B",
            "expression": "formula_a + 1",
            "return_type": "number",
        })
        self.assertEqual(second.status_code, 200)
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.custom_fields["formula_b"], 5)

        changed = self.client.put(f"/formula/fields/{first.json()['id']}", json={"expression": "score + 10"})
        self.assertEqual(changed.status_code, 200)
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.custom_fields["formula_a"], 13)
        self.assertEqual(self.patent.custom_fields["formula_b"], 14)

        label = self.db.query(CustomField).filter(CustomField.key == "label").one()
        converted = self.client.put(f"/custom-fields/{label.id}", json={
            "field_type": "formula",
            "formula_config": {"expression": "title", "return_type": "text"},
        })
        self.assertEqual(converted.status_code, 200)
        self.assertEqual(converted.json()["field_type"], "formula")
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.custom_fields["label"], "公式测试专利")

        reverted = self.client.put(f"/custom-fields/{label.id}", json={
            "field_type": "text",
            "formula_config": {"expression": "title", "return_type": "text"},
        })
        self.assertEqual(reverted.status_code, 200)
        self.assertEqual(reverted.json()["field_type"], "text")
        self.db.refresh(label)
        self.assertIsNone(label.formula_config)
        self.assertEqual(self.db.query(FormulaDependency).filter(FormulaDependency.formula_field_key == "label").count(), 0)


if __name__ == "__main__":
    unittest.main()
