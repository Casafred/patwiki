import unittest

import httpx

from app.integrations.contracts import ConnectorError
from app.integrations.mcp_transport import McpTransport


class McpTransportTest(unittest.TestCase):
    def test_initialize_reuses_session_and_lists_tools(self):
        requests = []

        def handler(request: httpx.Request):
            requests.append(request)
            body = request.read().decode("utf-8")
            if '"initialize"' in body:
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}}, headers={"Mcp-Session-Id": "fixture-session"})
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "fixture_tool"}]}})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        transport = McpTransport("https://fixture.test", credential_value="fixture-secret", client=client)
        tools = transport.list_tools("product_fixture")

        self.assertEqual(tools[0]["name"], "fixture_tool")
        self.assertEqual(requests[0].headers["Authorization"], "Bearer fixture-secret")
        self.assertEqual(requests[1].headers["Mcp-Session-Id"], "fixture-session")
        transport.close()

    def test_rpc_and_http_errors_are_provider_neutral(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "bad"}},
            headers={"Mcp-Session-Id": "fixture"},
        )))
        transport = McpTransport("https://fixture.test", credential_value="fixture-secret", client=client)
        with self.assertRaises(ConnectorError) as raised:
            transport.initialize("fixture")
        self.assertEqual(raised.exception.error_code, "mcp_rpc_error")
        transport.close()

    def test_tool_call_accepts_content_text_payload(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": '{"ok":true}'}]}},
            headers={"Mcp-Session-Id": "fixture"},
        )))
        transport = McpTransport("https://fixture.test", credential_value="fixture-secret", client=client)
        result = transport.call_tool("fixture", "tool", {})
        self.assertEqual(result["content"][0]["type"], "text")
        transport.close()


if __name__ == "__main__":
    unittest.main()
