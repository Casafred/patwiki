import unittest
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Patent, PatentDatabase, PatentFamily, PatentHistory
from app.api.patents import router as patents_router
from app.api.databases import router as databases_router
from app.services.patent_service import PatentService
from app.services.publication_version_service import (
    save_document, present_patents, backfill_versions,
)


class PublicationVersionsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.database = PatentDatabase(name="Version test", browsing_config={
            "application_mode": "merged", "preferred_version": "grant",
            "country_order": ["CN", "US", "EP", "JP"], "representative_date": "latest",
        })
        self.db.add(self.database)
        self.db.flush()
        self.patent = Patent(database_id=self.database.id, application_number="US202016845123",
            publication_number="US20220203506A1", title="Published title", country="US",
            publication_date=date(2022, 6, 30), claims="Published claims")
        self.db.add(self.patent)
        self.db.flush()
        save_document(self.patent, {"publication_number": "US11986927B2", "title": "Granted title",
            "claims": "Granted claims", "country": "US", "application_number": self.patent.application_number,
            "publication_date": date(2024, 5, 21)}, source="test", db=self.db)
        self.db.commit()
        app = FastAPI()
        app.include_router(patents_router)
        app.include_router(databases_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_merged_preference_and_separate_rows_share_wiki(self):
        rows, total = PatentService.list_patents(self.db, database_id=self.database.id)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0].publication_number, "US11986927B2")
        self.assertEqual(rows[0].claims, "Granted claims")
        self.database.browsing_config = {"application_mode": "merged", "preferred_version": "publication"}
        rows, total = PatentService.list_patents(self.db, database_id=self.database.id)
        self.assertEqual(rows[0].claims, "Published claims")
        self.database.browsing_config = {"application_mode": "separate"}
        response = self.client.get("/patents", params={"database_id": self.database.id}).json()
        self.assertEqual(response["total"], 2)
        self.assertEqual({item["id"] for item in response["items"]}, {self.patent.id})
        self.assertEqual(len({item["row_key"] for item in response["items"]}), 2)

    def test_version_details_and_edit_are_isolated(self):
        response = self.client.get(f"/patents/{self.patent.id}", params={"publication": "US11986927B2"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["title"], "Granted title")
        response = self.client.put(f"/patents/{self.patent.id}", json={
            "document_number": "US11986927B2", "claims": "Amended grant claims"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.patent.claims, "Published claims")
        self.assertEqual(self.client.get(f"/patents/{self.patent.id}", params={"publication": "US11986927B2"}).json()["claims"], "Amended grant claims")
        history = self.db.query(PatentHistory).filter(PatentHistory.field_key == "publication_versions.US11986927B2").order_by(PatentHistory.id.desc()).first()
        self.assertIsNotNone(history)
        PatentService.restore_history(self.db, self.patent, history)
        self.assertEqual(self.patent.publication_versions["US11986927B2"]["fields"]["claims"], "Granted claims")

    def test_version_filters_sorting_and_pagination(self):
        self.database.browsing_config = {"application_mode": "separate"}
        rows, total = PatentService.list_patents(self.db, database_id=self.database.id,
            filters={"title": {"contains": "Granted"}})
        self.assertEqual(total, 1)
        self.assertEqual(rows[0].document_number, "US11986927B2")
        rows, total = PatentService.list_patents(self.db, database_id=self.database.id,
            sort_by="publication_date", sort_order="asc", page_size=1, page=2)
        self.assertEqual(total, 2)
        self.assertEqual(rows[0].document_number, "US11986927B2")

    def test_representative_country_then_date_and_expansion(self):
        family = PatentFamily(family_id="test-family")
        self.db.add(family)
        self.db.flush()
        self.patent.family_id = family.id
        older = Patent(title="Older CN", country="CN", publication_number="CN100000001A",
            publication_date=date(2020, 1, 1), database_id=self.database.id, family_id=family.id)
        newer = Patent(title="Newer CN", country="CN", publication_number="CN100000002A",
            publication_date=date(2023, 1, 1), database_id=self.database.id, family_id=family.id)
        self.db.add_all([older, newer])
        self.db.commit()
        config = {**self.database.browsing_config, "family_representative": True}
        self.database.browsing_config = config
        rows, total = PatentService.list_patents(self.db, database_id=self.database.id, group_by_family=True, page_size=1)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0].id, newer.id)
        self.database.browsing_config = {**config, "representative_date": "earliest"}
        rows, total = PatentService.list_patents(self.db, database_id=self.database.id, group_by_family=True)
        self.assertEqual(rows[0].id, older.id)
        rows, total = PatentService.list_patents(self.db, database_id=self.database.id, group_by_family=True, expanded_families=[family.id])
        self.assertEqual(total, 3)
        self.assertEqual({row.id for row in rows}, {older.id, newer.id, self.patent.id})

    def test_unlisted_countries_and_unfamilied_documents_are_visible(self):
        other = Patent(id=999, title="Other", country="KR", publication_number="KR100000001A", family_id=777)
        config = {"family_representative": True, "application_mode": "separate", "country_order": ["CN"]}
        rows = present_patents([self.patent, other], config, group_by_family=True)
        self.assertEqual(len(rows), 3)

    def test_browsing_settings_persist_per_database(self):
        response = self.client.put(f"/databases/{self.database.id}/browsing-config", json={
            "application_mode": "separate", "country_order": ["cn", "US", "cn"],
            "representative_date": "earliest", "family_representative": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["browsing_config"]["country_order"], ["CN", "US"])
        self.assertEqual(self.client.get(f"/databases/{self.database.id}").json()["browsing_config"]["application_mode"], "separate")

    def test_backfill_missing_document_is_not_fabricated(self):
        self.patent.publication_versions = None
        self.patent.grant_number = "US11986927B2"
        self.db.commit()
        backfill_versions(self.db)
        self.assertEqual(self.patent.publication_versions["US20220203506A1"]["fields"]["claims"], "Published claims")
        self.assertFalse(self.patent.publication_versions["US11986927B2"]["data_available"])
        self.assertNotIn("claims", self.patent.publication_versions["US11986927B2"]["fields"])


if __name__ == "__main__":
    unittest.main()
