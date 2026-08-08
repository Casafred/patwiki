import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.database import get_db
from app.api.links import router
from app.models import CustomField, CustomFieldType, Patent, Product
from app.services.link_service import (
    create_link,
    list_links,
    list_links_batch,
    remove_link,
    resolve_lookup,
    resolve_relation_batch,
    resolve_rollup,
    search_targets,
)


class LinkServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        self.patent = Patent(title="源专利")
        self.product_a = Product(name="产品 A")
        self.product_b = Product(name="产品 B")
        self.link_field = CustomField(
            key="product_link",
            name="产品关联",
            field_type=CustomFieldType.LINK,
            link_config={"target_table": "products", "display_field": "name", "allow_multiple": True},
        )
        self.single_field = CustomField(
            key="single_link",
            name="单选关联",
            field_type=CustomFieldType.LINK,
            link_config={"target_table": "products", "display_field": "name", "allow_multiple": False},
        )
        self.lookup_field = CustomField(
            key="product_names",
            name="产品名称",
            field_type=CustomFieldType.LOOKUP,
            lookup_config={"link_field_key": "product_link", "source_field": "name", "allow_multiple": True},
        )
        self.rollup_field = CustomField(
            key="product_count",
            name="产品数",
            field_type=CustomFieldType.ROLLUP,
            rollup_config={"link_field_key": "product_link", "aggregation": "COUNT"},
        )
        self.db.add_all([
            self.patent,
            self.product_a,
            self.product_b,
            self.link_field,
            self.single_field,
            self.lookup_field,
            self.rollup_field,
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_link_lookup_rollup_batch_and_search(self):
        create_link(self.db, "product_link", self.patent.id, self.product_a.id)
        create_link(self.db, "product_link", self.patent.id, self.product_b.id)

        links = list_links(self.db, "product_link", self.patent.id)
        self.assertEqual([link["label"] for link in links], ["产品 A", "产品 B"])
        self.assertEqual(len(list_links_batch(self.db, "product_link", [self.patent.id])[self.patent.id]), 2)
        self.assertEqual(resolve_lookup(self.db, "product_names", self.patent.id)["value"], ["产品 A", "产品 B"])
        self.assertEqual(resolve_rollup(self.db, "product_count", self.patent.id)["value"], 2)

        batch = resolve_relation_batch(self.db, "product_count", [self.patent.id])
        self.assertEqual(batch[0]["value"], 2)
        self.assertEqual(search_targets(self.db, "product_link", "产品 B")[0]["label"], "产品 B")

    def test_single_link_replaces_previous_and_delete_removes_it(self):
        create_link(self.db, "single_link", self.patent.id, self.product_a.id)
        create_link(self.db, "single_link", self.patent.id, self.product_b.id)

        links = list_links(self.db, "single_link", self.patent.id)
        self.assertEqual([link["label"] for link in links], ["产品 B"])
        self.assertTrue(remove_link(self.db, "single_link", self.patent.id, self.product_b.id))
        self.assertEqual(list_links(self.db, "single_link", self.patent.id), [])

    def test_api_endpoints_cover_link_lifecycle_and_batch_resolve(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        client = TestClient(app)

        created = client.post("/links", json={
            "field_key": "product_link",
            "source_record_id": self.patent.id,
            "target_record_id": self.product_a.id,
        })
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["label"], "产品 A")

        search = client.get("/links/search", params={"field_key": "product_link", "search": "产品 A"})
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()[0]["label"], "产品 A")

        resolved = client.post("/relations/resolve-batch", json={
            "field_key": "product_link",
            "record_ids": [self.patent.id],
        })
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved.json()[0]["links"][0]["target_record_id"], self.product_a.id)

        deleted = client.request("DELETE", "/links", json={
            "field_key": "product_link",
            "source_record_id": self.patent.id,
            "target_record_id": self.product_a.id,
        })
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(client.get(f"/links/product_link/{self.patent.id}").json(), [])


if __name__ == "__main__":
    unittest.main()
