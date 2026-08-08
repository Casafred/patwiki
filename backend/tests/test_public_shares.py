import unittest
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.public_shares import router
from app.database import Base, get_db
from app.models import Patent, PatentShare


class PublicPatentShareTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.patent = Patent(
            title="分享测试专利",
            abstract="面向测试的技术摘要",
            technical_solution="通过结构化组件完成技术方案。",
            ai_fields={"secret_analysis": "不应公开"},
        )
        self.db.add(self.patent)
        self.db.commit()

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_create_access_and_revoke_share(self):
        created = self.client.post(
            f"/patents/{self.patent.id}/shares",
            json={"title_override": "研发技术主题"},
        )
        self.assertEqual(created.status_code, 200)
        share = created.json()
        self.assertTrue(share["is_active"])
        self.assertTrue(share["token"])
        self.assertEqual(share["share_path"], f"/share/patents/{share['token']}")

        public = self.client.get(f"/share/patents/{share['token']}")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.json()["patent"]["title"], "研发技术主题")
        self.assertEqual(public.json()["patent"]["abstract"], "面向测试的技术摘要")
        self.assertNotIn("ai_fields", public.json()["patent"])
        self.assertEqual(public.json()["share"]["access_count"], 1)

        revoked = self.client.delete(f"/patents/{self.patent.id}/shares/{share['token']}")
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(self.client.get(f"/share/patents/{share['token']}").status_code, 404)

    def test_expired_share_is_not_accessible(self):
        share = PatentShare(
            patent_id=self.patent.id,
            token="expired-share-token",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1),
        )
        self.db.add(share)
        self.db.commit()
        response = self.client.get("/share/patents/expired-share-token")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
