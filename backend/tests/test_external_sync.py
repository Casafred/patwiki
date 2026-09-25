import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.models  # noqa: F401
from app.models import (
    ConnectorDefinition,
    ExternalFactObservation,
    LegalStatusEvent,
    Patent,
    PatentDatabase,
    PatentHistory,
    SyncSubscription,
    SyncRecord,
    WatchEvent,
)
from app.services.sync_service import SyncService


class ExternalSyncTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.database = PatentDatabase(name="同步测试库", code="SYNC_TEST")
        self.db.add(self.database)
        self.db.commit()
        self.connector = ConnectorDefinition(
            code="demo-sync",
            name="Demo Sync",
            provider_type="demo",
            config_json={
                "version": "fixture-v1",
                "records": [
                    {
                        "external_record_id": "demo-1",
                        "identifiers": [{"identifier_type": "publication", "raw_value": "CN123456789A1", "jurisdiction_code": "CN"}],
                        "fields": {
                            "publication_number": "CN123456789A1",
                            "title": "外部同步专利",
                            "applicant": "测试申请人",
                            "publication_date": "2026-01-01",
                        },
                        "legal_events": [{
                            "provider_event_id": "event-1",
                            "event_code": "GRANT",
                            "event_date": "2026-02-01",
                            "status": "granted",
                            "jurisdiction_code": "CN",
                            "raw_description": "授权",
                        }],
                        "source_version": "fixture-v1",
                    },
                ],
            },
        )
        self.db.add(self.connector)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_subscription_sync_persists_evidence_applies_safe_facts_and_deduplicates_events(self):
        subscription = SyncService.create_subscription(self.db, {
            "database_id": self.database.id,
            "connector_id": self.connector.id,
            "name": "测试申请人监控",
            "scope_json": {"applicant": "测试申请人"},
            "schedule_json": {},
            "review_policy": "safe_auto_apply",
            "enabled": True,
        })
        first = SyncService.run_subscription(self.db, subscription)
        self.assertEqual(first.status, "succeeded")
        self.assertEqual(first.counts_json["created"], 1)
        self.assertGreaterEqual(first.counts_json["auto_applied"], 2)
        self.assertEqual(self.db.query(Patent).count(), 1)
        self.assertEqual(self.db.query(ExternalFactObservation).count(), 4)
        self.assertEqual(self.db.query(LegalStatusEvent).count(), 1)
        self.assertEqual(self.db.query(WatchEvent).count(), 1)
        self.assertEqual(self.db.query(SyncRecord).one().identity_candidate_patent_ids, [])
        self.assertEqual(self.db.query(PatentHistory).filter(PatentHistory.source == "external_sync").count(), 5)

        subscription = self.db.get(SyncSubscription, subscription.id)
        second = SyncService.run_subscription(self.db, subscription)
        self.assertEqual(second.status, "succeeded")
        self.assertEqual(self.db.query(Patent).count(), 1)
        self.assertEqual(self.db.query(LegalStatusEvent).count(), 1)
        self.assertEqual(self.db.query(WatchEvent).count(), 1)
        self.assertGreaterEqual(second.counts_json["duplicates"], 1)

    def test_changed_user_owned_field_requires_review(self):
        patent = Patent(title="人工标题", publication_number="CN123456789A1", applicant="旧申请人", database_id=self.database.id)
        self.db.add(patent)
        self.db.commit()
        subscription = SyncService.create_subscription(self.db, {
            "database_id": self.database.id,
            "connector_id": self.connector.id,
            "name": "审查策略",
            "scope_json": {},
            "schedule_json": {},
            "review_policy": "review_all",
            "enabled": True,
        })
        run = SyncService.run_subscription(self.db, subscription)
        self.assertEqual(run.status, "succeeded")
        observations = self.db.query(ExternalFactObservation).filter(
            ExternalFactObservation.patent_id == patent.id,
            ExternalFactObservation.canonical_field_key == "title",
        ).all()
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].decision, "pending_review")
        self.db.refresh(patent)
        self.assertEqual(patent.title, "人工标题")
        SyncService.decide_observation(self.db, observations[0], "accepted", "tester")
        self.db.refresh(patent)
        self.assertEqual(patent.title, "外部同步专利")

    def test_subscription_updates_only_selected_fields(self):
        patent = Patent(
            title="人工标题", publication_number="CN123456789A1",
            applicant="原申请人", database_id=self.database.id,
        )
        self.db.add(patent)
        self.db.commit()
        subscription = SyncService.create_subscription(self.db, {
            "database_id": self.database.id,
            "connector_id": self.connector.id,
            "name": "只更新公开日",
            "scope_json": {"update_fields": ["publication_date"]},
            "schedule_json": {},
            "review_policy": "safe_auto_apply",
            "enabled": True,
        })
        SyncService.run_subscription(self.db, subscription)
        self.db.refresh(patent)
        self.assertEqual(patent.title, "人工标题")
        self.assertEqual(patent.applicant, "原申请人")
        self.assertEqual(str(patent.publication_date), "2026-01-01")
        self.assertEqual(
            {item.canonical_field_key for item in self.db.query(ExternalFactObservation).all()},
            {"publication_date"},
        )
        self.assertFalse(any(item.field_key == "legal_status" for item in self.db.query(PatentHistory).all()))

    def test_failed_run_remains_queryable(self):
        connector = ConnectorDefinition(code="unsupported", name="Unsupported", provider_type="unknown")
        self.db.add(connector)
        self.db.commit()
        subscription = SyncService.create_subscription(self.db, {
            "database_id": self.database.id,
            "connector_id": connector.id,
            "name": "失败订阅",
            "scope_json": {},
            "schedule_json": {},
            "review_policy": "safe_auto_apply",
            "enabled": True,
        })
        with self.assertRaises(ValueError):
            SyncService.run_subscription(self.db, subscription)
        failed = self.db.get(SyncSubscription, subscription.id)
        self.assertEqual(failed.last_status, "failed_permanent")


if __name__ == "__main__":
    unittest.main()
