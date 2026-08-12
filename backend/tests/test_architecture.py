import unittest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.error_handler import register_exception_handlers
from app.core.exceptions import BadRequestException
from app.services.field_registry import (
    CustomFieldHandler,
    FIELD_REGISTRY,
    SYSTEM_FIELD_KEYS,
    get_all_fields_meta,
    get_system_field_meta,
)


class ArchitectureTest(unittest.TestCase):
    def test_field_registry_keeps_compatibility_exports_and_handlers(self):
        fields = FIELD_REGISTRY.list_fields()
        self.assertTrue(fields)
        self.assertEqual(set(SYSTEM_FIELD_KEYS) | {"attachments"}, {field["key"] for field in fields})
        self.assertEqual(get_system_field_meta("title")["name"], "标题")
        self.assertEqual(get_all_fields_meta(None), fields)

        record = SimpleNamespace(custom_fields={"priority": "high"})
        handler = CustomFieldHandler()
        self.assertEqual(handler.read_value(record, "priority"), "high")
        handler.write_value(record, "priority", "critical")
        self.assertEqual(record.custom_fields["priority"], "critical")

    def test_application_error_keeps_legacy_detail_shape(self):
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/failure")
        def failure():
            raise BadRequestException("invalid field")

        response = TestClient(app).get("/failure")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {
            "code": "BAD_REQUEST",
            "message": "invalid field",
            "detail": "invalid field",
        })


if __name__ == "__main__":
    unittest.main()
