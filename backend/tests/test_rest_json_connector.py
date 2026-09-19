import unittest
from datetime import date

import httpx

from app.integrations.contracts import CanonicalPatentQuery, ConnectorError, ProviderIdentifier
from app.integrations.rest_json import RestJsonConnector


class RestJsonConnectorTest(unittest.TestCase):
    def _config(self):
        return {
            "capabilities": {"cursor_pagination": True, "updated_since": True},
            "headers": {"X-Client": "patwiki-test"},
            "auth": {"type": "api_key", "header": "X-API-Key", "required": True},
            "retry": {"max_attempts": 2, "backoff_seconds": 0, "max_delay_seconds": 3},
            "search": {
                "method": "GET",
                "path": "/patents/search",
                "params": {
                    "q": "{{query.expression}}",
                    "applicant": "{{query.applicant}}",
                    "cursor": "{{cursor}}",
                    "limit": "{{limit}}",
                },
                "response": {
                    "records_path": "results",
                    "next_cursor_path": "next.cursor",
                    "watermark_path": "meta.watermark",
                    "source_version_path": "meta.version",
                },
            },
            "fetch": {
                "method": "GET",
                "path": "/patents/{{identifier.raw_value}}",
                "response": {"record_path": "record"},
            },
            "record": {
                "external_record_id": "record_id",
                "identifiers": [
                    {
                        "identifier_type": "publication",
                        "raw_value_path": "publication.number",
                        "jurisdiction_code_path": "publication.country",
                    }
                ],
                "fields": {
                    "publication_number": "publication.number",
                    "title": "title",
                    "applicant": "applicant.name",
                    "publication_date": "publication.date",
                },
                "legal_events": {
                    "path": "legal_events",
                    "provider_event_id_path": "id",
                    "event_code_path": "code",
                    "event_date_path": "date",
                    "status_path": "status",
                    "jurisdiction_code_path": "country",
                    "raw_description_path": "description",
                },
                "source_updated_at_path": "updated_at",
                "source_version_path": "version",
            },
        }

    def test_search_maps_fixture_page_and_uses_credential_only_in_header(self):
        requests = []

        def handler(request: httpx.Request):
            requests.append(request)
            self.assertEqual(request.headers["X-API-Key"], "fixture-secret")
            self.assertEqual(request.url.params["applicant"], "Acme")
            return httpx.Response(200, json={
                "results": [{
                    "record_id": "provider-1",
                    "publication": {"number": "CN123A", "country": "CN", "date": "2026-01-02"},
                    "title": "A patent",
                    "applicant": {"name": "Acme"},
                    "updated_at": "2026-01-03T08:00:00Z",
                    "version": "fixture-1",
                    "legal_events": [{"id": "evt-1", "code": "GRANT", "date": "2026-02-01", "status": "granted", "country": "CN", "description": "Granted", "token": "must-not-persist"}],
                    "api_key": "must-not-persist",
                }],
                "next": {"cursor": "next-1"},
                "meta": {"watermark": "2026-01-03T08:00:00Z", "version": "fixture-1"},
            })

        connector = RestJsonConnector(
            self._config(),
            endpoint="https://fixture.test/api",
            credential_value="fixture-secret",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        page = connector.search(CanonicalPatentQuery(applicant="Acme", expression="battery"), None, 100)

        self.assertEqual(len(requests), 1)
        self.assertEqual(page.next_cursor, "next-1")
        self.assertEqual(page.watermark.isoformat(), "2026-01-03T08:00:00")
        self.assertEqual(page.records[0].identifiers[0].raw_value, "CN123A")
        self.assertEqual(page.records[0].fields["applicant"], "Acme")
        self.assertEqual(page.records[0].legal_events[0].event_date, date(2026, 2, 1))
        self.assertEqual(page.records[0].raw_payload["api_key"], "[REDACTED]")
        self.assertEqual(page.records[0].legal_events[0].payload["token"], "[REDACTED]")

    def test_fetch_maps_single_record(self):
        def handler(request: httpx.Request):
            self.assertEqual(request.url.path, "/api/patents/CN123A")
            return httpx.Response(200, json={"record": {
                "record_id": "provider-1",
                "publication": {"number": "CN123A", "country": "CN", "date": "2026-01-02"},
                "title": "A patent",
                "applicant": {"name": "Acme"},
                "legal_events": [],
            }})

        connector = RestJsonConnector(
            self._config(),
            endpoint="https://fixture.test/api",
            credential_value="fixture-secret",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        record = connector.fetch_patent(ProviderIdentifier("publication", "CN123A"))
        self.assertEqual(record.external_record_id, "provider-1")
        self.assertEqual(record.fields["publication_number"], "CN123A")

    def test_retry_after_is_honored_and_auth_error_is_permanent(self):
        delays = []
        responses = [
            httpx.Response(429, headers={"Retry-After": "2"}, json={"error": "busy"}),
            httpx.Response(401, json={"error": "no"}),
        ]

        def handler(_request: httpx.Request):
            return responses.pop(0)

        connector = RestJsonConnector(
            self._config(),
            endpoint="https://fixture.test/api",
            credential_value="fixture-secret",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleeper=delays.append,
        )
        with self.assertRaises(ConnectorError) as raised:
            connector.search(CanonicalPatentQuery(), None, 10)
        self.assertEqual(raised.exception.error_code, "authentication_error")
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(delays, [2.0])

    def test_inline_credentials_and_redirects_are_rejected(self):
        with self.assertRaisesRegex(ConnectorError, "明文凭证"):
            RestJsonConnector({"headers": {"X-API-Key": "secret"}}, endpoint="https://fixture.test")

        def handler(_request: httpx.Request):
            return httpx.Response(302, headers={"Location": "https://other.test/patents"})

        connector = RestJsonConnector(
            {"search": {"response": {"records_path": "items"}}},
            endpoint="https://fixture.test/api",
            client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        )
        with self.assertRaisesRegex(ConnectorError, "重定向"):
            connector.search(CanonicalPatentQuery(), None, 10)

    def test_full_request_url_cannot_change_scheme_or_host(self):
        connector = RestJsonConnector(
            {"search": {"path": "http://fixture.test/patents", "response": {"records_path": "items"}}},
            endpoint="https://fixture.test/api",
            client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"items": []}))),
        )
        with self.assertRaisesRegex(ConnectorError, "其他主机"):
            connector.search(CanonicalPatentQuery(), None, 10)


if __name__ == "__main__":
    unittest.main()
