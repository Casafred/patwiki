"""Regression coverage for the rebuildable semantic-search projection."""
from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Patent, SemanticIndexOutbox, SemanticProviderDefinition, SemanticSearchProfile
from app.services.semantic_index_service import SemanticIndexService
from app.services.semantic_job_service import SemanticJobService
from app.services.semantic_search_service import SemanticSearchService
from app.search.contracts import VectorDocument
from app.search.providers.openai_embedding import resolve_credential
from app.search.document_builder import SemanticDocumentBuilder
from app.search.vector.zvec_store import ZvecVectorStore


class SemanticSearchTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.profile = SemanticSearchProfile(name="test-profile", is_default=True, retrieval_mode="hybrid")
        self.db.add_all([
            self.profile,
            Patent(title="电池热失控隔热结构", publication_number="CN123456789A1", abstract="用于阻断电池热失控传播的隔热组件"),
            Patent(title="普通散热装置", publication_number="CN987654321A1", abstract="散热片和风扇结构"),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_hybrid_degrades_to_keyword_without_index(self):
        result = SemanticSearchService.query(self.db, text="热失控", database_id=None, mode="hybrid", top_k=10, profile_id=self.profile.id)
        self.assertTrue(result["meta"]["degraded"])
        self.assertEqual(result["items"][0]["patent"]["publication_number"], "CN123456789A1")

    def test_semantic_mode_degrades_to_keyword_without_index(self):
        result = SemanticSearchService.query(self.db, text="热失控", database_id=None, mode="semantic", top_k=10, profile_id=self.profile.id)
        self.assertTrue(result["meta"]["degraded"])
        self.assertIn("SEMANTIC_INDEX_NOT_READY", result["meta"]["degraded_reasons"])
        self.assertEqual(result["items"][0]["patent"]["publication_number"], "CN123456789A1")

    def test_exact_identifier_is_pinned_above_keyword_matches(self):
        result = SemanticSearchService.query(self.db, text="CN123456789A1", database_id=None, mode="keyword", top_k=10, profile_id=self.profile.id)
        self.assertTrue(result["items"][0]["scores"]["exact"])
        self.assertEqual(result["items"][0]["patent"]["publication_number"], "CN123456789A1")

    def test_outbox_is_deduplicated(self):
        SemanticIndexService.enqueue_patent(self.db, 1, "field_changed")
        SemanticIndexService.enqueue_patent(self.db, 1, "second_change")
        self.db.commit()
        rows = self.db.query(SemanticIndexOutbox).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].reason, "second_change")

    def test_keyring_credential_reference_is_resolved(self):
        with patch("keyring.get_password", return_value="test-secret") as get_password:
            self.assertEqual(resolve_credential("keyring://patwiki/embedding"), "test-secret")
        get_password.assert_called_once_with("patwiki", "embedding")

    def test_rebuild_versions_are_unique_within_one_second(self):
        first = SemanticIndexService.enqueue_rebuild(self.db, self.profile)
        second = SemanticIndexService.enqueue_rebuild(self.db, self.profile)
        self.assertNotEqual(first.index_id, second.index_id)

    def test_outbox_failure_uses_backoff_instead_of_immediate_retry(self):
        SemanticIndexService.enqueue_patent(self.db, 1, "field_changed")
        self.db.commit()
        with patch.object(SemanticIndexService, "apply_outbox", side_effect=RuntimeError("temporary failure")):
            SemanticJobService.run_due(self.db)
        item = self.db.query(SemanticIndexOutbox).one()
        self.assertEqual(item.status, "retry_wait")
        self.assertEqual(item.attempt_count, 1)
        self.assertIsNotNone(item.next_retry_at)

    def test_rerank_reorders_authorized_candidates(self):
        provider = SemanticProviderDefinition(
            name="test-rerank", provider_kind="rerank", provider_type="openai_compatible_rerank",
            endpoint="https://rerank.test/v1/rerank", credential_ref="env://PATWIKI_TEST_RERANK_KEY",
        )
        self.db.add(provider)
        self.db.flush()
        self.profile.rerank_provider_id = provider.id
        self.profile.rerank_model = "rerank-test"
        self.profile.rerank_enabled = True
        self.db.commit()

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]}

        with patch.dict(os.environ, {"PATWIKI_TEST_RERANK_KEY": "secret"}), patch("httpx.post", return_value=FakeResponse()):
            result = SemanticSearchService.query(self.db, text="结构", database_id=None, mode="keyword", top_k=10, profile_id=self.profile.id)
        self.assertTrue(result["meta"]["reranked"])
        self.assertEqual(result["items"][0]["patent"]["publication_number"], "CN987654321A1")
        self.assertEqual(result["items"][0]["scores"]["rerank_score"], 0.9)

    def test_exact_identifier_remains_first_after_rerank(self):
        provider = SemanticProviderDefinition(
            name="test-rerank-exact", provider_kind="rerank", provider_type="openai_compatible_rerank",
            endpoint="https://rerank.test/v1/rerank", credential_ref="env://PATWIKI_TEST_RERANK_KEY",
        )
        self.db.add(provider)
        self.db.flush()
        self.profile.rerank_provider_id, self.profile.rerank_model, self.profile.rerank_enabled = provider.id, "rerank-test", True
        self.db.commit()

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]}

        with patch.dict(os.environ, {"PATWIKI_TEST_RERANK_KEY": "secret"}), patch("httpx.post", return_value=FakeResponse()):
            result = SemanticSearchService.query(self.db, text="CN123456789A1", database_id=None, mode="keyword", top_k=10, profile_id=self.profile.id)
        self.assertTrue(result["items"][0]["scores"]["exact"])
        self.assertEqual(result["items"][0]["patent"]["publication_number"], "CN123456789A1")

    def test_zvec_store_persists_and_queries_vectors(self):
        with tempfile.TemporaryDirectory() as root:
            store = ZvecVectorStore(Path(root) / "index", 3)
            try:
                store.upsert([
                    VectorDocument("1:patent_summary:0", 1, "", [1.0, 0.0, 0.0]),
                    VectorDocument("2:patent_summary:0", 2, "", [0.0, 1.0, 0.0]),
                ])
                matches = store.dense_search([0.9, 0.1, 0.0], 2)
                self.assertEqual(matches[0]["patent_id"], 1)
                store.delete(["2:patent_summary:0"])
                self.assertEqual(len(store.dense_search([0.9, 0.1, 0.0], 10)), 1)
            finally:
                store.close()

    def test_claims_and_description_are_chunked_with_stable_metadata(self):
        patent = self.db.query(Patent).filter(Patent.id == 1).one()
        patent.claims = "1. 一种电池结构，包括隔热层。\n2. 根据权利要求1所述的电池结构，还包括传感器。"
        patent.description_full = "背景技术。\n\n本发明提供一种用于阻断热失控传播的结构。"
        documents = SemanticDocumentBuilder.build_documents(patent, chunk_strategy_version="claims-description-v1", max_chars=200)
        self.assertEqual(documents[0].metadata["document_type"], "patent_summary")
        chunks = documents[1:]
        self.assertEqual([item.metadata["document_type"] for item in chunks], ["patent_claims", "patent_claims", "patent_description"])
        self.assertEqual(chunks[0].document_id, "1:patent_claims:0")
        self.assertEqual(chunks[1].document_id, "1:patent_claims:1")
        self.assertEqual(chunks[2].document_id, "1:patent_description:0")
        self.assertTrue(all(item.metadata["parent_document_id"] == "1:patent_summary:0" for item in chunks))

    def test_zvec_storage_keeps_legacy_summary_key_and_separates_chunks(self):
        self.assertEqual(ZvecVectorStore._storage_id("1:patent_summary:0"), "p1_summary_0")
        self.assertEqual(ZvecVectorStore._storage_id("1:patent_claims:0"), "p1_patent_claims_0")
