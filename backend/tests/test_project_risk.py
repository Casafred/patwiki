import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.project_risk import router
from app.api.patents import router as patents_router
from app.database import Base, get_db
from app.core.exceptions import BadRequestException
from app.models import Patent, PatentDatabase, Project, PatentProjectLink, RelationType
from app.schemas.schemas import PatentCreate
from app.services.merge_service import merge_patent_data
from app.services.patent_service import PatentService


class ProjectRiskTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        app = FastAPI()
        app.include_router(router)
        app.include_router(patents_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _seed(self):
        database = PatentDatabase(name="风险上下文测试库")
        project = Project(name="美国项目", code="US-001")
        patent = Patent(
            title="涉及产品结构的风险专利",
            publication_number="US1234567A1",
            database=database,
        )
        self.db.add_all([database, project, patent])
        self.db.commit()
        return database, project, patent

    def test_solution_version_is_append_only_after_confirmation(self):
        database, project, _ = self._seed()
        response = self.client.post(
            f"/projects/{project.id}/solution-versions",
            json={
                "database_id": database.id,
                "name": "下模前结构方案",
                "project_stage": "TR1",
                "source_type": "meeting",
                "source_description": "研发评审会议记录",
                "changes": [{
                    "feature_name": "散热结构",
                    "after_description": "改为双通道结构",
                    "impact_description": "可能影响成本和装配",
                }],
                "regions": [{"region_code": "US", "region_name": "美国"}],
            },
        )
        self.assertEqual(response.status_code, 200)
        version = response.json()
        self.assertEqual(version["version_no"], "v1")
        self.assertEqual(version["changes"][0]["feature_name"], "散热结构")
        self.assertEqual(version["regions"][0]["region_code"], "US")

        confirmed = self.client.post(
            f"/solution-versions/{version['id']}/confirm",
            json={"confirmed_by": "检索师"},
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["status"], "confirmed")

        update = self.client.put(
            f"/solution-versions/{version['id']}",
            json={"change_summary": "不应覆盖历史版本"},
        )
        self.assertEqual(update.status_code, 409)

        second_response = self.client.post(
            f"/projects/{project.id}/solution-versions",
            json={"database_id": database.id, "name": "方案 B", "project_stage": "TR2"},
        )
        second_confirmed = self.client.post(
            f"/solution-versions/{second_response.json()['id']}/confirm",
            json={"confirmed_by": "分析师"},
        )
        self.assertEqual(second_confirmed.status_code, 200)
        old = self.client.get(f"/solution-versions/{version['id']}")
        self.assertEqual(old.json()["status"], "superseded")

    def test_patent_projects_can_be_added_and_removed_from_detail_scope(self):
        database, project, patent = self._seed()
        other_project = Project(name="国内项目", code="CN-001")
        self.db.add(other_project)
        self.db.commit()

        added = self.client.put(
            f"/patents/{patent.id}/projects",
            json={
                "links": [
                    {"project_id": project.id, "relation_type": "risk", "notes": "美国风险排查"},
                    {"project_id": other_project.id},
                ],
            },
        )
        self.assertEqual(added.status_code, 200, added.text)
        self.assertEqual({item["id"] for item in added.json()["projects"]}, {project.id, other_project.id})

        listed = self.client.get(f"/patents/{patent.id}/projects")
        self.assertEqual({item["id"] for item in listed.json()}, {project.id, other_project.id})
        risk_link = next(item for item in listed.json() if item["id"] == project.id)
        self.assertEqual(risk_link["relation_type"], "risk")
        self.assertEqual(risk_link["notes"], "美国风险排查")

        before_ids = {item.project_id for item in self.db.query(PatentProjectLink).filter_by(patent_id=patent.id).all()}
        invalid = self.client.put(
            f"/patents/{patent.id}/projects",
            json={"project_ids": [project.id, 999999]},
        )
        self.assertEqual(invalid.status_code, 400)
        after_ids = {item.project_id for item in self.db.query(PatentProjectLink).filter_by(patent_id=patent.id).all()}
        self.assertEqual(after_ids, before_ids)

        removed = self.client.put(
            f"/patents/{patent.id}/projects",
            json={"project_ids": [project.id]},
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual([item["id"] for item in removed.json()["projects"]], [project.id])
        preserved = self.client.get(f"/patents/{patent.id}/projects").json()[0]
        self.assertEqual(preserved["relation_type"], "risk")
        self.assertEqual(preserved["notes"], "美国风险排查")

    def test_risk_case_keeps_assessment_versions_and_review_history(self):
        database, project, patent = self._seed()
        version_response = self.client.post(
            f"/projects/{project.id}/solution-versions",
            json={"database_id": database.id, "name": "方案 A", "project_stage": "TR1"},
        )
        version_id = version_response.json()["id"]
        response = self.client.post(
            "/risk-cases",
            json={
                "database_id": database.id,
                "title": "美国专利涉及当前方案",
                "trigger_reason": "月度竞对新公开专利跟踪发现命中方案特征",
                "current_gate": "TR1",
                "patent_links": [{"patent_id": patent.id}],
                "solution_links": [{"solution_version_id": version_id}],
                "regions": [{"region_code": "US", "region_name": "美国"}],
            },
        )
        self.assertEqual(response.status_code, 200)
        risk_case = response.json()
        self.assertEqual(len(risk_case["patent_links"]), 1)
        self.assertEqual(risk_case["solution_links"][0]["solution_version_id"], version_id)

        first = self.client.post(
            f"/risk-cases/{risk_case['id']}/assessments",
            json={
                "assessment_stage": "TR1",
                "solution_version_id": version_id,
                "jurisdiction_code": "US",
                "preliminary_assessment": "初步判断存在风险",
                "analysis_confirmation": "分析师确认需要规避评估",
                "decision": "avoid",
                "risk_level": "high",
                "gate_impact": "review_required",
                "decision_basis": "基于权利要求特征和当前方案对比，需先进行规避评估",
                "assessed_by": "检索师",
                "confirmed_by": "分析师",
                "decided_by": "分析组负责人",
                "decision_at": "2026-08-19T10:00:00",
            },
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["current_risk_level"], "high")
        self.assertEqual(len(first.json()["assessments"]), 1)
        self.assertIsNotNone(first.json()["assessments"][0]["confirmed_at"])

        second = self.client.post(
            f"/risk-cases/{risk_case['id']}/assessments",
            json={
                "assessment_stage": "TR1",
                "solution_version_id": version_id,
                "jurisdiction_code": "US",
                "decision": "continue_with_risk",
                "risk_level": "high",
                "gate_impact": "continue_with_risk",
                "decision_basis": "规避负面影响过大，会议决定承担风险继续",
                "leadership_confirmation": "部门领导确认",
                "assessed_by": "分析师",
                "confirmed_by": "部门领导",
                "decided_by": "部门领导",
                "decision_at": "2026-08-19T11:00:00",
            },
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual([item["version_no"] for item in second.json()["assessments"]], [2, 1])
        self.assertEqual(second.json()["current_decision"], "continue_with_risk")

        review = self.client.post(
            f"/risk-cases/{risk_case['id']}/reviews",
            json={
                "trigger_type": "shipment_region_changed",
                "trigger_description": "出货地可能从美国扩展到加拿大",
                "review_outcome": "待确认加拿大保护范围后重新评估",
                "next_review_condition": "确认加拿大同族法律状态",
                "reviewed_by": "检索师",
            },
        )
        self.assertEqual(review.status_code, 200)
        self.assertEqual(len(review.json()["reviews"]), 1)

        listed = self.client.get(f"/risk-cases?database_id={database.id}&patent_id={patent.id}")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

    def test_legacy_risk_projection_is_not_a_direct_write_path(self):
        database, _, patent = self._seed()
        with self.assertRaises(BadRequestException):
            PatentService.update_patent(self.db, patent, {"risk_level": "high"})
        with self.assertRaises(BadRequestException):
            PatentService.create_patent(
                self.db,
                PatentCreate(title="不应直接携带正式风险结论", database_id=database.id, risk_level="high"),
            )
        merged = merge_patent_data(patent, {"risk_level": "high", "title": "更新标题"})
        self.assertNotIn("risk_level", merged)
        self.assertEqual(merged["title"], "更新标题")


if __name__ == "__main__":
    unittest.main()
