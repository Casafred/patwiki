import unittest
from copy import deepcopy
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.models  # noqa: F401
from app.models import (
    ConnectorDefinition,
    ExternalSnapshot,
    LegalStatusEvent,
    Patent,
    PatentDatabase,
    PatentHistory,
    SyncRecord,
    SyncUpdateBatch,
)
from app.services.sync_update_service import SyncUpdateService


class ExplicitSyncUpdateTest(unittest.TestCase):
    def test_family_alias_confirms_relation_projection_without_creating_patents(self):
        member = Patent(title="Family member", publication_number="US11712787B2", database_id=self.database.id)
        self.db.add(member)
        records = deepcopy(self.connector.config_json["records"])
        records[0]["fields"]["family_members"] = "US11712787B2, US20200130150A1"
        self.connector.config_json = {"records": records}
        self.db.commit()
        batch = SyncUpdateService.preview(self.db, self.connector, self.database.id, [self.patent.id], ["mcp_family_members"])
        self.assertEqual(batch.selected_fields, ["family_members"])
        self.assertIsNone(self.patent.family_id)
        SyncUpdateService.confirm(self.db, batch, [{"item_id": batch.items[0].id, "fields": ["family_members"]}], "tester")
        self.assertEqual(self.db.query(Patent).count(), 2)
        self.assertEqual(self.patent.family_id, member.family_id)
        self.assertIsNotNone(self.patent.family_id)
        self.assertEqual(self.patent.custom_fields["family_members"], "US11712787B2, US20200130150A1")
        self.assertNotIn("mcp_family_members", self.patent.custom_fields)
        self.assertEqual(self.db.query(PatentHistory).filter(PatentHistory.field_key == "family_members").count(), 1)

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.database = PatentDatabase(name="覆盖更新测试库", code="UPDATE_TEST")
        self.db.add(self.database)
        self.db.flush()
        self.connector = ConnectorDefinition(
            code="demo-explicit-update",
            name="Demo Explicit Update",
            provider_type="demo",
            config_json={
                "records": [{
                    "external_record_id": "demo-update-1",
                    "identifiers": [{"identifier_type": "publication", "raw_value": "CN123456789A1", "jurisdiction_code": "CN"}],
                    "fields": {
                        "publication_number": "CN123456789A1",
                        "title": "外部最新标题",
                        "applicant": "外部申请人",
                        "publication_date": "2026-01-01",
                        "legal_status": "granted",
                    },
                    "legal_events": [{
                        "provider_event_id": "update-event-1",
                        "event_code": "GRANT",
                        "event_date": "2026-02-01",
                        "status": "granted",
                        "jurisdiction_code": "CN",
                    }],
                }],
            },
        )
        self.db.add(self.connector)
        self.patent = Patent(
            title="人工维护标题",
            publication_number="CN123456789A1",
            applicant="旧申请人",
            database_id=self.database.id,
        )
        self.db.add(self.patent)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_preview_does_not_write_and_confirm_overwrites_same_row_with_history(self):
        batch = SyncUpdateService.preview(
            self.db,
            self.connector,
            self.database.id,
            [self.patent.id],
            ["title", "applicant", "legal_status"],
        )
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.title, "人工维护标题")
        self.assertEqual(self.db.query(Patent).count(), 1)
        self.assertEqual(batch.items[0].status, "ready")
        self.assertEqual(set(batch.items[0].changed_fields), {"title", "applicant", "legal_status"})
        self.assertEqual(self.db.query(ExternalSnapshot).count(), 1)

        SyncUpdateService.confirm(self.db, batch, [{
            "item_id": batch.items[0].id,
            "fields": ["title", "legal_status"],
        }], "tester")
        self.db.refresh(self.patent)
        self.assertEqual(self.db.query(Patent).count(), 1)
        self.assertEqual(self.patent.title, "外部最新标题")
        self.assertEqual(self.patent.applicant, "旧申请人")
        self.assertEqual(self.patent.legal_status.value, "granted")
        self.assertEqual(self.db.query(SyncUpdateBatch).one().status, "confirmed")
        self.assertEqual(self.db.query(SyncRecord).one().outcome, "updated")
        self.assertEqual(self.db.query(PatentHistory).filter(PatentHistory.source == "external_sync_update").count(), 1)
        self.assertEqual(self.db.query(PatentHistory).filter(PatentHistory.field_key == "legal_status").count(), 1)
        self.assertEqual(self.db.query(LegalStatusEvent).count(), 1)

    def test_unmatched_provider_record_cannot_create_patent(self):
        self.patent.publication_number = "CN999999999A1"
        self.db.commit()
        batch = SyncUpdateService.preview(self.db, self.connector, self.database.id, [self.patent.id], ["title"])
        self.assertEqual(batch.items[0].status, "not_found")
        self.assertEqual(self.db.query(Patent).count(), 1)

    def test_confirm_rechecks_preview_value_before_overwrite(self):
        batch = SyncUpdateService.preview(self.db, self.connector, self.database.id, [self.patent.id], ["title"])
        self.patent.title = "用户后来修改的标题"
        self.db.commit()
        with self.assertRaises(Exception):
            SyncUpdateService.confirm(self.db, batch, [{"item_id": batch.items[0].id, "fields": ["title"]}], "tester")
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.title, "用户后来修改的标题")

    def test_himmpat_rejects_fields_outside_the_verified_mapping(self):
        self.connector.provider_type = "himmpat_mcp"
        self.connector.config_json = {"enrich_legal_status": False}
        self.db.commit()
        with self.assertRaises(Exception) as raised:
            SyncUpdateService._validate_fields(["title", "risk_level"], self.connector)
        self.assertIn("risk_level", str(raised.exception))
        self.assertEqual(
            SyncUpdateService._validate_fields(["title", "ipc_all"], self.connector),
            ["title", "ipc_all"],
        )
        self.assertEqual(SyncUpdateService._validate_fields(["claims", "description_full", "technical_solution"], self.connector), ["claims", "description_full", "technical_solution"])
        self.assertNotIn("claims", SyncUpdateService._validate_fields(None, self.connector))

    def test_fulltext_and_technical_fields_confirm_to_wiki_with_history(self):
        records = deepcopy(self.connector.config_json["records"])
        records[0]["fields"].update({"claims": "1. A device", "description_full": "Details", "technical_solution": "Technical means"})
        self.connector.config_json = {"records": records}
        self.db.commit()
        batch = SyncUpdateService.preview(self.db, self.connector, self.database.id, [self.patent.id], ["claims", "description_full", "technical_solution"])
        self.assertIsNone(self.patent.claims)
        SyncUpdateService.confirm(self.db, batch, [{"item_id": batch.items[0].id, "fields": ["claims", "technical_solution"]}], "tester")
        self.db.refresh(self.patent)
        self.assertEqual(self.patent.claims, "1. A device")
        self.assertEqual(self.patent.technical_solution, "Technical means")
        self.assertIsNone(self.patent.description_full)
        self.assertEqual(self.db.query(PatentHistory).filter(PatentHistory.source == "external_sync_update").count(), 2)

    def test_tool_api_validates_schema_and_persists_query_source(self):
        from app.api.sync import call_connector_tool, McpToolRequest
        from app.integrations.himmpat import HimmPatMcpAdapter
        self.connector.enabled = True
        self.connector.mcp_catalog_json = {"services": [{"service": "product_patent_dossier", "tools": [{
            "name": "get_pdf_by_patent_ids", "inputSchema": {"type": "object", "required": ["ids"],
                "properties": {"ids": {"type": "array", "items": {"type": "string"}}}},
        }]}]}
        self.db.commit()

        class Transport:
            def call_tool(self, service, name, arguments):
                return {"structuredContent": {"code": 200, "data": {"h-1": ["pdf-1"]}}}
            def close(self):
                pass

        with patch("app.api.sync.get_connector", return_value=HimmPatMcpAdapter({}, transport=Transport())) as factory:
            with self.assertRaises(Exception):
                call_connector_tool(self.connector.id, McpToolRequest(service="product_patent_dossier", tool="get_pdf_by_patent_ids", arguments={"ids": [123]}), self.db)
            factory.assert_not_called()
            response = call_connector_tool(self.connector.id, McpToolRequest(service="product_patent_dossier", tool="get_pdf_by_patent_ids", arguments={"ids": ["h-1"]}), self.db)
            snapshot = self.db.get(ExternalSnapshot, response["snapshot_id"])
            self.assertEqual(snapshot.request_metadata["tool"], "get_pdf_by_patent_ids")
            self.assertEqual(snapshot.run.trigger, "mcp_tool")
            self.assertEqual(response["data"], {"h-1": ["pdf-1"]})
            self.assertEqual(self.db.query(Patent).count(), 1)


if __name__ == "__main__":
    unittest.main()
