import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.patents import router
from app.core.exceptions import BadRequestException
from app.database import Base, get_db
from app.models import Citation, Patent, PatentFamily, PatentDatabase
from app.services.patent_service import PatentService


class PatentGraphApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        database = PatentDatabase(name="当前专利库", code="CURRENT_GRAPH_DB")
        family = PatentFamily(family_id="FAM_TEST_GRAPH", family_type="simple")
        root = Patent(
            title="核心专利",
            publication_number="CN100000001A",
            database=database,
            custom_fields={
                "family_members": "US100000001A;JP999999999A1",
                "cited_patents": "CN900000001A | EP999999999A1",
                "citing_patents": "CN200000001A;WO999999999A1",
            },
        )
        family_member = Patent(title="同族专利", publication_number="US100000001A", database=database)
        cited = Patent(title="被引用专利", publication_number="CN900000001A", database=database)
        citing = Patent(title="引用专利", publication_number="CN200000001A", database=database)
        self.db.add_all([database, family, root, family_member, cited, citing])
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
        self.assertEqual(
            [item["publication_number"] for item in payload["missing_members"]],
            ["JP999999999A1"],
        )

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
        external_ids = {item["id"] for item in response.json()["external_members"]}
        self.assertIn(cross_database_member.id, external_ids)

    def test_citations_endpoint_returns_directions_and_database_statuses(self):
        other_database = PatentDatabase(name="其他专利库", code="OTHER_CITATION_DB")
        external_cited = Patent(
            title="其他库被引用专利",
            publication_number="JP300000001A",
            database=other_database,
        )
        self.db.add_all([other_database, external_cited])
        self.db.flush()
        self.db.add(Citation(citing_patent_id=self.root_id, cited_patent_id=external_cited.id))
        self.db.commit()

        response = self.client.get(f"/patents/{self.root_id}/citations")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        cited_by_number = {item["publication_number"]: item for item in payload["cited"]}
        citing_by_number = {item["publication_number"]: item for item in payload["citing"]}
        self.assertEqual(cited_by_number["CN900000001A"]["status"], "in_database")
        self.assertEqual(cited_by_number["JP300000001A"]["status"], "other_database")
        self.assertEqual(cited_by_number["EP999999999A1"]["status"], "missing_record")
        self.assertEqual(citing_by_number["CN200000001A"]["status"], "in_database")
        self.assertEqual(citing_by_number["WO999999999A1"]["status"], "missing_record")
        self.assertEqual(cited_by_number["CN900000001A"]["direction"], "cited")
        self.assertEqual(citing_by_number["CN200000001A"]["direction"], "citing")

        self.assertEqual(
            self.db.query(Patent).filter(Patent.publication_number == "EP999999999A1").count(),
            0,
        )
        self.assertEqual(
            self.db.query(Patent).filter(Patent.publication_number == "WO999999999A1").count(),
            0,
        )

    def test_graph_does_not_leak_cross_database_citation(self):
        other_database = PatentDatabase(name="图谱其他库", code="OTHER_GRAPH_CITATION_DB")
        external_cited = Patent(
            title="图谱其他库被引用专利",
            publication_number="JP300000002A",
            database=other_database,
        )
        self.db.add_all([other_database, external_cited])
        self.db.flush()
        self.db.add(Citation(citing_patent_id=self.root_id, cited_patent_id=external_cited.id))
        self.db.commit()

        response = self.client.get(f"/patents/{self.root_id}/graph")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertNotIn(external_cited.id, [node["patent_id"] for node in payload["nodes"]])
        self.assertEqual(payload["counts"]["citation_edges"], 2)

    def test_normal_patent_edit_cannot_overwrite_relation_source_projection(self):
        with self.assertRaises(BadRequestException):
            PatentService.update_patent(
                self.db,
                self.db.get(Patent, self.root_id),
                {"custom_fields": {"cited_patents": "CN999999999A"}},
            )
        self.db.expire_all()
        root = self.db.get(Patent, self.root_id)
        self.assertEqual(root.custom_fields["cited_patents"], "CN900000001A | EP999999999A1")



if __name__ == "__main__":
    unittest.main()
