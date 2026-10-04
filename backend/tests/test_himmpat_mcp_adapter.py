import json
import unittest

from app.integrations.contracts import CanonicalPatentQuery, ProviderIdentifier
from app.integrations.himmpat import HimmPatMcpAdapter, READ_ONLY_TOOLS


class FixtureTransport:
    def __init__(self):
        self.calls = []

    def close(self):
        pass

    def discover(self, services):
        return {"services": [{"service": service, "tool_count": 1, "tools": [{"name": "fixture"}]} for service in services]}

    def call_tool(self, service, tool, arguments):
        self.calls.append((service, tool, arguments))
        if tool == "query_patent_ids_by_query_expression_with_info":
            return {"content": [{"type": "text", "text": json.dumps({"code": 200, "data": {"total": 2, "patents": [{
                "id": "h-1", "pn": "CN123A", "ap": "CN2020123.4", "ti": "测试专利", "as": ["测试申请人"], "pd": "2026-01-02", "apd": "2025-01-01", "ab": "摘要"
            }]}, "message": "查询成功;"})}]}
        if tool == "search_patent_by_patent_numbers":
            return {"content": [{"type": "text", "text": json.dumps({"code": 200, "data": {"CN123A": ["h-1"]}, "message": "查询成功;"})}]}
        if tool == "get_patent_publication_by_patent_ids":
            return {"content": [{"type": "text", "text": json.dumps({"code": 200, "data": {"h-1": {
                "applicationReferenceModel": {"ap": "CN2020123.4", "apc": "cn", "apd": "2025-01-01", "pty": "A"},
                "inventionTitleModel": {"tio": "测试专利"},
                "abstractModel": {"abc": "摘要"},
                "partiesModel": {"applicant": [{"pa": "测试申请人"}], "inventor": [{"in": "发明人"}]},
                "publicationReferenceModel": {"pd": "2026-01-02", "pn": "CN123A", "pnc": "cn", "pnty": "A"},
            }}, "message": "查询成功;"})}]}
        if tool == "get_patent_legal_status_by_patent_ids":
            return {"content": [{"type": "text", "text": json.dumps({"code": 200, "data": {"h-1": {"state": "I", "stc": "GR", "grd": "2026-02-01"}}, "message": "查询成功;"})}]}
        raise AssertionError(tool)


class HimmPatAdapterTest(unittest.TestCase):
    def setUp(self):
        self.transport = FixtureTransport()
        self.adapter = HimmPatMcpAdapter({"enrich_legal_on_fetch": True}, transport=self.transport)

    def test_search_maps_himmpat_summary_and_page_cursor(self):
        page = self.adapter.search(CanonicalPatentQuery(applicant="测试申请人", extra={"size": 1}), None, 1)
        self.assertEqual(page.next_cursor, "2")
        self.assertEqual(page.records[0].external_record_id, "h-1")
        self.assertEqual(page.records[0].fields["publication_number"], "CN123A")
        self.assertEqual(page.records[0].fields["applicant"], "测试申请人")
        self.assertEqual(self.transport.calls[0][2]["queryExpression"], "测试申请人/pa")

    def test_fetch_unwraps_dossier_and_enriches_legal_event(self):
        record = self.adapter.fetch_patent(ProviderIdentifier("publication", "CN123A", "CN"))
        self.assertEqual(record.fields["title"], "测试专利")
        self.assertEqual(record.fields["grant_date"].isoformat(), "2026-02-01")
        self.assertEqual(record.legal_events[0].status, "granted")
        self.assertTrue(record.legal_events[0].provider_event_id.startswith("himmpat:"))

    def test_business_error_is_not_logged_as_secret_or_retryable(self):
        class ErrorTransport(FixtureTransport):
            def call_tool(self, service, tool, arguments):
                return {"content": [{"type": "text", "text": json.dumps({"code": 202, "data": {}, "message": "bad"})}]}

        adapter = HimmPatMcpAdapter({}, transport=ErrorTransport())
        with self.assertRaises(Exception) as raised:
            adapter.search(CanonicalPatentQuery(expression="invalid"), None, 10)
        self.assertEqual(raised.exception.error_code, "provider_business_error")
        self.assertFalse(raised.exception.retryable)

    def test_current_state_without_grant_date_does_not_invent_event_date(self):
        class NoDateTransport(FixtureTransport):
            def call_tool(self, service, tool, arguments):
                if tool == "get_patent_legal_status_by_patent_ids":
                    return {"content": [{"type": "text", "text": json.dumps({"code": 200, "data": {"h-1": {"state": "P", "stc": "PB"}}})}]}
                return super().call_tool(service, tool, arguments)

        adapter = HimmPatMcpAdapter({}, transport=NoDateTransport())
        record = adapter.fetch_patent(ProviderIdentifier("publication", "CN123A", "CN"))
        record = adapter._enrich_legal([record])[0]
        self.assertEqual(record.fields["legal_status"], "pending")
        self.assertEqual(record.legal_events, ())

    def test_complete_service_endpoint_is_normalized_for_cross_service_refresh(self):
        adapter = HimmPatMcpAdapter(
            {"credential_value": "fixture-secret"},
            endpoint="https://www.himmpat.com/api/service/himmuc_api/mcp/product_patent_dossier",
        )
        self.assertEqual(adapter.transport.endpoint, "https://www.himmpat.com")
        self.assertEqual(
            adapter.transport.service_endpoint(adapter.services["discovery"]),
            "https://www.himmpat.com/api/service/himmuc_api/mcp/product_patent_discovery",
        )
        self.assertEqual(
            adapter.transport.service_endpoint(adapter.services["legal"]),
            "https://www.himmpat.com/api/service/himmuc_api/mcp/product_legal_ownership_risk",
        )
        adapter.close()

    def test_selected_fulltext_and_ai_fields_use_provider_schema_and_normalize_text(self):
        class FullTransport(FixtureTransport):
            def discover(self, services):
                return {"services": [{"service": services[0], "tools": [
                    {"name": "get_claims_by_patent_id", "inputSchema": {"properties": {"patentId": {"type": "string"}}}},
                    {"name": "get_description_by_patent_id", "inputSchema": {"properties": {"id": {"type": "string"}}}},
                ]}]}

            def call_tool(self, service, tool, arguments):
                payloads = {
                    "get_claims_by_patent_id": {"h-1": {"claims": [{"text": "1. A device"}, {"text": "2. The device"}]}},
                    "get_description_by_patent_id": {"h-1": {"description": "Detailed description"}},
                    "get_patent_ai_tech_info": {"h-1": {"technicalProblem": "Problem", "technicalMeans": "Means", "technicalEffect": "Effect"}},
                }
                if tool in payloads:
                    self.calls.append((service, tool, arguments))
                    return {"structuredContent": {"code": 200, "data": payloads[tool]}}
                return super().call_tool(service, tool, arguments)

        transport = FullTransport()
        adapter = HimmPatMcpAdapter({}, transport=transport)
        basic = adapter.fetch_patent_fields(ProviderIdentifier("publication", "CN123A"), {"title"})
        self.assertNotIn("claims", basic.fields)
        self.assertEqual(len(transport.calls), 2)
        record = adapter.fetch_patent_fields(ProviderIdentifier("publication", "CN123A"), {"claims", "description_full", "technical_solution"})
        self.assertEqual(record.fields["claims"], "1. A device\n\n2. The device")
        self.assertEqual(record.fields["description_full"], "Detailed description")
        self.assertEqual(record.fields["technical_solution"], "Means")
        self.assertIn("get_patent_ai_tech_info", record.raw_payload)
        self.assertIn(("product_patent_dossier", "get_claims_by_patent_id", {"patentId": "h-1"}), transport.calls)

    def test_workbench_supports_all_catalog_tools_and_array_scalar_results(self):
        class ToolTransport(FixtureTransport):
            def call_tool(self, service, tool, arguments):
                return {"structuredContent": {"code": 200, "data": ["one", "two"]}}
        adapter = HimmPatMcpAdapter({}, transport=ToolTransport())
        self.assertEqual(sum(len(names) for names in READ_ONLY_TOOLS.values()), 40)
        for service, names in READ_ONLY_TOOLS.items():
            for name in names:
                data, _ = adapter.call_discovered_tool(adapter.services[service], name, {})
                self.assertEqual(data["items"], ["one", "two"])
        with self.assertRaises(Exception) as raised:
            adapter.call_discovered_tool(adapter.services["dossier"], "delete_patent", {})
        self.assertEqual(raised.exception.error_code, "unsupported_tool")


if __name__ == "__main__":
    unittest.main()
