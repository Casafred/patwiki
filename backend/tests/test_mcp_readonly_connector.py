import unittest

from app.integrations.contracts import CanonicalPatentQuery, ProviderIdentifier, ProviderPatentRecord
from app.integrations.demo import record_from_payload
from app.integrations.mcp_readonly import McpReadonlyConnector


class McpReadonlyConnectorTest(unittest.TestCase):
    def test_only_configured_read_tools_are_called_and_records_are_normalized(self):
        calls = []

        def call_tool(name, arguments):
            calls.append((name, arguments))
            if name == "search_patents":
                return {
                    "structuredContent": {
                        "items": [{
                            "external_record_id": "mcp-1",
                            "identifiers": [{"identifier_type": "publication", "raw_value": "CN123"}],
                            "fields": {"title": "MCP patent"},
                        }],
                        "next": "cursor-2",
                    }
                }
            return {"record": {"external_record_id": "mcp-1", "identifiers": [], "fields": {}}}

        connector = McpReadonlyConnector(
            call_tool,
            record_mapper=record_from_payload,
            response_config={"records_path": "items", "next_cursor_path": "next", "record_path": "record"},
        )
        page = connector.search(CanonicalPatentQuery(applicant="Acme"), None, 25)
        record = connector.fetch_patent(ProviderIdentifier("publication", "CN123"))

        self.assertEqual([item[0] for item in calls], ["search_patents", "get_patent"])
        self.assertEqual(calls[0][1]["limit"], 25)
        self.assertEqual(page.next_cursor, "cursor-2")
        self.assertIsInstance(page.records[0], ProviderPatentRecord)
        self.assertEqual(record.external_record_id, "mcp-1")


if __name__ == "__main__":
    unittest.main()
