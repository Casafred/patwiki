import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.comments import router
from app.database import Base, get_db
from app.models import Comment, Patent, PatentDatabase


class CommentApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        database = PatentDatabase(name="评论测试库", code="COMMENT_TEST")
        self.db.add(database)
        self.db.flush()
        self.patent = Patent(database_id=database.id, title="待评审专利")
        self.db.add(self.patent)
        self.db.commit()

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_comment_reply_mention_resolve_and_delete_lifecycle(self):
        created = self.client.post(f"/patents/{self.patent.id}/comments", json={
            "content": "@alice 请确认权利要求 1 的边界。 @alice",
            "author_name": "reviewer",
            "field_key": "claims",
        })
        self.assertEqual(created.status_code, 200)
        root = created.json()
        self.assertEqual(root["mentions"], ["alice"])
        self.assertEqual(root["field_key"], "claims")

        reply = self.client.post(f"/patents/{self.patent.id}/comments", json={
            "content": "我已经补充对比文件。",
            "author_name": "alice",
            "parent_id": root["id"],
        })
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply.json()["parent_id"], root["id"])

        edited = self.client.put(f"/comments/{reply.json()['id']}", json={"content": "我已经补充对比文件 @reviewer。"})
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["mentions"], ["reviewer"])

        resolved = self.client.post(f"/comments/{root['id']}/resolve", json={"resolved": True, "resolved_by": "reviewer"})
        self.assertEqual(resolved.status_code, 200)
        self.assertTrue(resolved.json()["is_resolved"])
        open_comments = self.client.get(f"/patents/{self.patent.id}/comments", params={"include_resolved": False})
        self.assertEqual(open_comments.status_code, 200)
        self.assertEqual(len(open_comments.json()), 1)

        thread = self.client.get(f"/comments/{root['id']}/thread")
        self.assertEqual(thread.status_code, 200)
        self.assertEqual(len(thread.json()), 2)

        self.assertEqual(self.client.delete(f"/comments/{reply.json()['id']}").status_code, 200)
        self.assertEqual(self.client.delete(f"/comments/{root['id']}").status_code, 200)
        self.assertEqual(self.db.query(Comment).count(), 0)

    def test_rejects_reply_from_another_patent(self):
        first = self.client.post(f"/patents/{self.patent.id}/comments", json={"content": "原评论"}).json()
        other = Patent(title="另一条专利")
        self.db.add(other)
        self.db.commit()
        response = self.client.post(f"/patents/{other.id}/comments", json={"content": "错误回复", "parent_id": first["id"]})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
