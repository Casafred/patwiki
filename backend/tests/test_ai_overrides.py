import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.ai.fields.engine import AIFieldEngine
from app.api.patents import router
from app.api.ai import router as ai_router
from app.database import Base, get_db
from app.models import AIFieldValue, AITask, CustomField, CustomFieldType, Patent, PatentHistory


class _FakeResponse:
    content = "重新生成的 AI 值"


class _FakeLLM:
    def __init__(self):
        self.calls = 0

    def invoke(self, prompt: str):
        self.calls += 1
        return _FakeResponse()


class AIOverrideApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.field = CustomField(
            key="ai_summary",
            name="AI 摘要",
            field_type=CustomFieldType.AI_FIELD,
            description="提炼专利摘要",
        )
        self.patent = Patent(title="测试专利", ai_fields={"ai_summary": "AI 原值"})
        self.db.add_all([self.field, self.patent])
        self.db.flush()
        self.db.add(AIFieldValue(
            patent_id=self.patent.id,
            field_key="ai_summary",
            value="AI 原值",
            input_hash="initial",
        ))
        self.db.commit()

        app = FastAPI()
        app.include_router(router)
        app.include_router(ai_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_override_lifecycle_and_history(self):
        initial = self.client.get(f"/patents/{self.patent.id}/ai-values")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()[0]["value"], "AI 原值")
        self.assertEqual(initial.json()[0]["generated_value"], "AI 原值")
        self.assertFalse(initial.json()[0]["is_overridden"])

        overridden = self.client.put(
            f"/patents/{self.patent.id}/ai-values",
            json={"field_key": "ai_summary", "value": "人工修订值"},
        )
        self.assertEqual(overridden.status_code, 200)
        self.assertEqual(overridden.json()["value"], "人工修订值")
        self.assertTrue(overridden.json()["is_overridden"])

        current = self.client.get(f"/patents/{self.patent.id}/ai-values").json()[0]
        self.assertEqual(current["value"], "人工修订值")
        self.assertEqual(current["generated_value"], "AI 原值")
        self.assertTrue(current["is_overridden"])

        fake_llm = _FakeLLM()
        with patch.object(AIFieldEngine, "_get_llm", return_value=(fake_llm, "test-model")):
            result, _ = AIFieldEngine(self.db).process_single(self.patent, self.field)
        self.assertEqual(result, "人工修订值")
        self.assertEqual(fake_llm.calls, 0)

        cleared = self.client.delete(
            f"/patents/{self.patent.id}/ai-values",
            params={"field_key": "ai_summary"},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["value"], "AI 原值")
        self.assertFalse(self.client.get(f"/patents/{self.patent.id}/ai-values").json()[0]["is_overridden"])

        history = self.db.query(PatentHistory).filter_by(patent_id=self.patent.id).all()
        self.assertEqual(len(history), 2)
        self.assertEqual({item.source for item in history}, {"manual"})

    def test_force_recalculate_replaces_generated_value_and_clears_override(self):
        self.client.put(
            f"/patents/{self.patent.id}/ai-values",
            json={"field_key": "ai_summary", "value": "人工修订值"},
        )

        fake_llm = _FakeLLM()
        with patch.object(AIFieldEngine, "_get_llm", return_value=(fake_llm, "test-model")):
            result, _ = AIFieldEngine(self.db).process_single(self.patent, self.field, force=True)

        self.assertEqual(result, "重新生成的 AI 值")
        self.assertEqual(fake_llm.calls, 1)
        value = self.db.query(AIFieldValue).filter_by(
            patent_id=self.patent.id,
            field_key="ai_summary",
        ).one()
        self.assertFalse(value.is_overridden)
        self.assertIsNone(value.overridden_value)
        self.assertEqual(value.value, "重新生成的 AI 值")
        self.assertEqual(self.patent.ai_fields["ai_summary"], "重新生成的 AI 值")

    def test_quick_analyze_prepare_failure_is_persisted_as_failed_task(self):
        response = self.client.post(
            "/ai/quick-analyze",
            json={
                "patent_ids": [self.patent.id],
                "input_fields": ["title"],
                "prompt": "提取摘要",
                "extractions": [{
                    "name": "摘要",
                    "target_field_key": "missing_field",
                }],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        task = response.json()
        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["errors"][0]["stage"], "prepare")
        persisted = self.db.query(AITask).filter(AITask.id == task["id"]).one()
        self.assertEqual(persisted.status, "failed")

    def test_standard_ai_missing_field_is_persisted_and_listed_as_failed_task(self):
        response = self.client.post(
            "/ai/process",
            json={"patent_ids": [self.patent.id], "field_key": "missing_field"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        task = response.json()
        self.assertEqual(task["status"], "failed")
        self.assertIsInstance(task["errors"], list)
        listed = self.client.get("/ai/tasks").json()
        listed_task = next(item for item in listed if item["id"] == task["id"])
        self.assertEqual(listed_task["status"], "failed")
        self.assertEqual(listed_task["errors"][0]["stage"], "prepare")

    def test_quick_analyze_parse_failure_is_failed_without_writing_empty_value(self):
        target = CustomField(
            key="cf_quick_result",
            name="快速结果",
            field_type=CustomFieldType.TEXT,
        )
        self.db.add(target)
        task = AITask(
            task_type="quick_analyze",
            total_items=1,
            status="pending",
        )
        self.db.add(task)
        self.db.commit()
        class InvalidLLM:
            def invoke(self, _prompt):
                return type("Response", (), {"content": "这不是 JSON"})()

        with patch.object(AIFieldEngine, "_get_llm", return_value=(InvalidLLM(), "test-model")):
            AIFieldEngine(self.db).quick_analyze_batch(
                task.id, [self.patent.id], ["title"], "提取摘要",
                [{"name": "摘要", "target_field_key": "cf_quick_result"}],
            )
        self.db.refresh(self.patent)
        persisted = self.db.query(AITask).filter(AITask.id == task.id).one()
        self.assertEqual(persisted.status, "failed")
        self.assertEqual(persisted.failed_count, 1)
        self.assertEqual(persisted.errors[0]["patent_id"], self.patent.id)
        self.assertIsNone((self.patent.custom_fields or {}).get("cf_quick_result"))


if __name__ == "__main__":
    unittest.main()
