import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.patents import router
from app.database import Base, get_db
from app.models import Citation, Patent, PatentFamily, PatentDatabase


class PatentGraphApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        family = PatentFamily(family_id="FAM_TEST_GRAPH", family_type="simple")
        root = Patent(title="核心专利", publication_number="CN100000001A")
        family_member = Patent(title="同族专利", publication_number="US100000001A")
        cited = Patent(title="被引用专利", publication_number="CN900000001A")
        citing = Patent(title="引用专利", publication_number="CN200000001A")
        self.db.add_all([family, root, family_member, cited, citing])
        self.db.flush()
        root.family_id = family.id
        family_member.family_id = family.id
        self.db.add_all([
            Citation(citing_patent_id=root.id, cited_patent_id=cited.id),
            Citation(citing_patent_id=citing.id, cited_patent_id=root.id),
        ])
        self.db.commit()
        self.root_id = root.id

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_graph_contains_family_and_both_citation_directions(self):
        response = self.client.get(f"/patents/{self.root_id}/graph")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["root_id"], self.root_id)
        self.assertEqual(payload["counts"]["family_edges"], 1)
        self.assertEqual(payload["counts"]["citation_edges"], 2)
        self.assertEqual(payload["counts"]["nodes"], 4)
        self.assertEqual(
            {edge["relation"] for edge in payload["edges"]},
            {"family", "citation"},
        )

    def test_graph_can_disable_relationship_types(self):
        response = self.client.get(
            f"/patents/{self.root_id}/graph",
            params={"include_family": "false", "include_citations": "false"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nodes"], [
            {
                "id": f"patent:{self.root_id}",
                "patent_id": self.root_id,
                "kind": "root",
                "label": "核心专利",
                "title": "核心专利",
                "number": "CN100000001A",
                "is_placeholder": False,
            },
        ])
        self.assertEqual(response.json()["edges"], [])

    def test_family_endpoint_returns_independent_navigable_members(self):
        response = self.client.get(f"/patents/{self.root_id}/family")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["root_id"], self.root_id)
        self.assertEqual(payload["family_key"], "FAM_TEST_GRAPH")
        self.assertEqual({item["id"] for item in payload["members"]}, {self.root_id, self.root_id + 1})
        current = next(item for item in payload["members"] if item["id"] == self.root_id)
        member = next(item for item in payload["members"] if item["id"] != self.root_id)
        self.assertTrue(current["is_current"])
        self.assertFalse(member["is_current"])
        self.assertEqual(member["publication_number"], "US100000001A")

    def test_family_endpoint_does_not_leak_same_family_member_from_other_database(self):
        other_database = PatentDatabase(name="其他库", code="OTHER_GRAPH_DB")
        self.db.add(other_database)
        self.db.flush()
        cross_database_member = Patent(
            title="其他库同族专利",
            publication_number="JP100000001A",
            database_id=other_database.id,
            family_id=self.db.query(PatentFamily).filter(
                PatentFamily.family_id == "FAM_TEST_GRAPH"
            ).one().id,
        )
        self.db.add(cross_database_member)
        self.db.commit()

        response = self.client.get(f"/patents/{self.root_id}/family")
        self.assertEqual(response.status_code, 200)
        member_ids = {item["id"] for item in response.json()["members"]}
        self.assertNotIn(cross_database_member.id, member_ids)



if __name__ == "__main__":
    unittest.main()
