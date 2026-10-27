import json
import unittest

from app.integrations.contracts import CanonicalPatentQuery, ProviderIdentifier
from app.integrations.patsnap import PatsnapMcpAdapter, tool_mappable_fields


class FixtureTransport:
    def __init__(self):
        self.calls = []

    def close(self):
        pass

    def discover(self, services):
        return {"services": [{"service": services[0], "tool_count": 7, "tools": [{"name": "search_patents"}]}]}

    def call_tool(self, service, tool, arguments):
        self.calls.append((service, tool, arguments))
        data = {
            "search_patents": {"results": [{"patent_id": "p-1", "pn": "CN123A", "title": "测试专利", "applicant": "测试申请人", "publication_date": "2026-01-02"}], "total_search_result_count": 1},
            "bibliography": [{"pn": "CN123A", "patent_id": "p-1", "bibliographic_data": {
                "application_reference": {"country": "CN", "doc_number": "2020123.4", "date": "20250101"},
                "publication_reference": {"country": "CN", "doc_number": "123A", "date": "20260102"},
                "invention_title": [{"lang": "CN", "text": "测试专利"}],
                "abstracts": [{"lang": "CN", "text": "摘要"}],
                "parties": {"applicants": [{"name": "测试申请人"}], "inventors": [{"name": "发明人"}]},
                "priority_claims": [{"number": "CN2020123", "date": "20200101"}],
            }}],
            "claims": {"claims": [{"claim_text": "1. 一种装置"}]},
            "description": {"description": "说明书全文"},
            "family": [{"patent_family": {"simple_family": [{"country": "CN", "doc_number": "123A", "kind": ""}, {"country": "US", "doc_number": "2024012345", "kind": "A1"}]}}],
            "get_patent_legal_status": [{"pn": "CN123A", "simple_legal_status": "有效", "grant_date": "20260201"}],
        }.get(tool, {})
        return {"content": [{"type": "text", "text": json.dumps({"success": True, "error_code": 0, "data": data})}]}


class PatsnapAdapterTest(unittest.TestCase):
    def setUp(self):
        self.transport = FixtureTransport()
        self.adapter = PatsnapMcpAdapter({"enrich_legal_on_fetch": False}, transport=self.transport)

    def test_search_maps_document_and_cursor(self):
        page = self.adapter.search(CanonicalPatentQuery(applicant="测试申请人"), None, 20)
        self.assertEqual(page.next_cursor, None)
        self.assertEqual(page.records[0].external_record_id, "p-1")
        self.assertEqual(page.records[0].fields["publication_number"], "CN123A")
        self.assertEqual(self.transport.calls[0][2]["query_text"], "PA=(测试申请人)")

    def test_fetch_maps_bibliography_and_selected_enrichments(self):
        record = self.adapter.fetch_patent_fields(
            ProviderIdentifier("publication", "CN123A"),
            {"claims", "description_full", "family_members", "legal_status"},
        )
        self.assertEqual(record.fields["title"], "测试专利")
        self.assertEqual(record.fields["application_number"], "CN2020123.4")
        self.assertEqual(record.fields["claims"], "1. 一种装置")
        self.assertEqual(record.fields["description_full"], "说明书全文")
        self.assertIn("US2024012345A1", record.fields["family_members"])
        self.assertIn("mcp_record_fields", record.fields)
        self.assertEqual(record.fields["legal_status"], "granted")
        self.assertEqual(record.fields["grant_date"].isoformat(), "2026-02-01")
        self.assertTrue(record.legal_events[0].provider_event_id.startswith("patsnap:"))

    def test_discovered_tool_mapping_and_business_error(self):
        self.assertIn("claims", tool_mappable_fields("claims"))
        self.assertIn("family_members", tool_mappable_fields("family"))
        self.assertIn("mcp_abstract_figure", tool_mappable_fields("abstract_image"))
        self.assertIn("mcp_description_figures", tool_mappable_fields("fulltext_image"))
        self.assertIn("mcp_intelligent_figures", tool_mappable_fields("intelligent_image"))

        class ErrorTransport(FixtureTransport):
            def call_tool(self, service, tool, arguments):
                return {"content": [{"type": "text", "text": json.dumps({"success": False, "error_code": 1001, "data": None})}]}

        with self.assertRaises(Exception) as raised:
            PatsnapMcpAdapter({}, transport=ErrorTransport()).search(CanonicalPatentQuery(expression="x"), None, 10)
        self.assertEqual(raised.exception.error_code, "provider_business_error")


if __name__ == "__main__":
    unittest.main()
