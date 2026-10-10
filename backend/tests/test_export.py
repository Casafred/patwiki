import unittest
from datetime import date, datetime
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
from app.services.export_service import ExportService
from app.services.view_service import ViewService


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

    def test_excel_export_can_limit_to_explicit_selected_patent_ids(self):
        selected_id = self.db.query(Patent).filter(Patent.title == "授权专利").one().id
        response = self.client.post("/export/excel", json={
            "database_id": self.database_id,
            "patent_ids": [selected_id],
            "field_keys": ["title"],
        })
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        rows = list(workbook["专利数据"].iter_rows(values_only=True))
        self.assertEqual(rows, [("标题",), ("授权专利",)])

    def test_empty_explicit_selection_does_not_fall_back_to_database(self):
        response = self.client.post("/export/csv", json={
            "database_id": self.database_id,
            "patent_ids": [],
            "field_keys": ["title"],
        })
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        self.assertEqual(content, "标题\r\n")

    def test_relation_projection_columns_are_exported_as_raw_source_values(self):
        patent = Patent(
            title="关系导出专利",
            database_id=self.database_id,
            custom_fields={
                "family_members": "US100000020A;CN100000020A",
                "cited_patents": "EP100000020A1 | JP100000020A1",
                "citing_patents": "WO100000020A1",
            },
        )
        self.db.add(patent)
        self.db.commit()

        response = self.client.post("/export/csv", json={
            "database_id": self.database_id,
            "field_keys": ["title", "family_members", "cited_patents", "citing_patents"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        content = response.content.decode("utf-8-sig")
        self.assertIn("同族专利号,引用专利号,被引用专利号", content)
        self.assertIn("US100000020A;CN100000020A", content)
        self.assertIn("EP100000020A1 | JP100000020A1", content)
        self.assertIn("WO100000020A1", content)

    def test_system_work_file_templates_are_listed_and_used_by_export(self):
        ViewService.ensure_default_business_views(self.db, self.database_id)
        templates = ExportService.ensure_default_templates(self.db, self.database_id)
        self.assertEqual(
            {template.template_key for template in templates},
            {
                "risk_meeting_excel",
                "ip_application_control_excel",
                "patent_analysis_work_file",
                "daily_patent_accumulation_csv",
                "company_filing_category_excel",
                "ip_risk_control_excel",
                "product_category_master_excel",
                "daily_patent_accumulation_excel",
            },
        )

        listed = self.client.get("/export/templates", params={"database_id": self.database_id})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 8)

        csv_template = next(item for item in listed.json() if item["output_format"] == "csv")
        response = self.client.post("/export/csv", json={
            "database_id": self.database_id,
            "template_id": csv_template["id"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        self.assertIn("标题", response.content.decode("utf-8-sig"))

    def test_replenishment_includes_missing_family_and_document_versions_read_only(self):
        from app.models import PatentFamily
        from app.services.replenishment_service import ReplenishmentService

        family = PatentFamily(family_id="REPLENISH_TEST")
        other = PatentDatabase(name="其他库", code="OTHER_REPLENISH")
        self.db.add_all([family, other])
        self.db.flush()
        complete = {key: "完整信息" for key in ReplenishmentService.MAIN_FIELDS}
        complete.update(legal_status="granted", patent_type="invention", country="CN",
                        filing_date=date(2020, 1, 1), publication_date=date(2021, 1, 1))
        self.db.add_all([
            Patent(**complete, publication_number="CN111111111A", database_id=self.database_id,
                   family_id=family.id, custom_fields={"family_members": "US222222222A1; US222222222A1; garbage; CN202012345678.9"},
                   publication_versions={
                       "CN111111111A": {"kind": "publication", "fields": {
                           **complete, "filing_date": "2020-01-01", "publication_date": "2021-01-01"}},
                       "CN111111111B": {"kind": "grant", "data_available": False, "fields": {"title": "不能算完整"}},
                   }),
            Patent(title="待补全", publication_number="JP03333333A", database_id=self.database_id),
            Patent(**{**complete, "application_number": "EP2020123456"},
                   publication_number="EP444444444A1", database_id=other.id, family_id=family.id),
            Patent(title="无关库", publication_number="US555555555A1", database_id=other.id),
            Patent(title="已删除", publication_number="CN666666666A", database_id=self.database_id,
                   deleted_at=datetime(2025, 1, 1)),
        ])
        self.db.commit()
        count_before = self.db.query(Patent).count()
        response = self.client.post("/export/replenishment", json={"database_id": self.database_id})
        self.assertEqual(response.status_code, 200, response.text if response.status_code != 200 else "")
        sheet = load_workbook(BytesIO(response.content))["补库清单"]
        rows = list(sheet.iter_rows(values_only=True))
        headers = rows[0]
        by_number = {row[0]: dict(zip(headers, row)) for row in rows[1:]}
        self.assertEqual(set(by_number), {"CN111111111B", "JP3333333A", "EP444444444A1", "US222222222A1"})
        for number in by_number:
            self.assertEqual(by_number[number]["标题"], "缺失")
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertEqual(sheet.auto_filter.ref, sheet.dimensions)
        self.assertEqual(self.db.query(Patent).count(), count_before)

    def test_replenishment_reports_only_missing_fields_and_respects_membership(self):
        from app.models.database_membership import PatentDatabaseMembership
        other = PatentDatabase(name="来源库", code="REPLENISH_SOURCE")
        self.db.add(other)
        self.db.flush()
        patent = Patent(title="已知标题", publication_number="CN777777777A", database_id=other.id,
                        applicant="  ", legal_status="unknown")
        self.db.add(patent)
        self.db.flush()
        self.db.add(PatentDatabaseMembership(patent_id=patent.id, database_id=self.database_id))
        self.db.commit()
        response = self.client.post("/export/replenishment", json={"database_id": self.database_id})
        self.assertEqual(response.status_code, 200)
        rows = list(load_workbook(BytesIO(response.content))["补库清单"].iter_rows(values_only=True))
        row = dict(zip(rows[0], rows[1]))
        self.assertEqual(row["公开号"], "CN777777777A")
        self.assertIsNone(row["标题"])
        self.assertEqual(row["申请人"], "缺失")
        self.assertEqual(row["法律状态"], "缺失")

    def test_replenishment_rejects_invalid_database_and_empty_inventory(self):
        self.assertEqual(self.client.post("/export/replenishment", json={"database_id": 999999}).status_code, 400)
        self.assertEqual(self.client.post("/export/replenishment", json={"database_id": self.database_id}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
