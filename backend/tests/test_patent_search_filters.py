import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Patent, PatentDatabase
from app.services.patent_service import PatentService


class PatentSearchFiltersTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        database = PatentDatabase(name="检索筛选测试库", code="SEARCH_FILTER_TEST")
        self.db.add(database)
        self.db.flush()
        self.database_id = database.id
        self.db.add_all([
            Patent(
                title="\u7535\u673a\u63a7\u5236\u65b9\u6848",
                abstract="\u7528\u4e8e\u7a33\u5b9a\u63a7\u5236\u7684\u6458\u8981",
                claims="\u5305\u542b\u6e29\u5ea6\u8865\u507f\u7ed3\u6784",
                publication_number="CN500000001A1",
                applicant="\u7532\u516c\u53f8",
                category="\u7535\u673a",
                database_id=self.database_id,
                custom_fields={"\u6765\u6e90\u5907\u6ce8": "\u6708\u5ea6\u8ddf\u8e2a"},
                ai_fields={"\u6280\u672f\u95ee\u9898": "\u6563\u70ed\u95ee\u9898"},
            ),
            Patent(
                title="\u4f20\u611f\u5668\u65b9\u6848",
                abstract="\u53e6\u4e00\u6458\u8981",
                claims="\u5305\u542b\u4fe1\u53f7\u91c7\u96c6\u7ed3\u6784",
                publication_number="CN500000002A1",
                applicant="\u4e59\u516c\u53f8",
                category="\u4f20\u611f\u5668",
                database_id=self.database_id,
                custom_fields={"\u6765\u6e90\u5907\u6ce8": "\u5e74\u5ea6\u76d8\u70b9"},
                ai_fields={},
            ),
            Patent(
                title="\u7a7a\u5b57\u6bb5\u4e13\u5229",
                publication_number="CN500000003A1",
                applicant="甲公司",
                database_id=self.database_id,
                custom_fields={},
                ai_fields={},
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _titles(self, **kwargs):
        rows, _ = PatentService.list_patents(
            self.db,
            database_id=self.database_id,
            page=1,
            page_size=50,
            **kwargs,
        )
        return {row.title for row in rows}

    def test_search_covers_claims_custom_and_ai_fields(self):
        self.assertEqual(self._titles(search="\u6e29\u5ea6\u8865\u507f"), {"\u7535\u673a\u63a7\u5236\u65b9\u6848"})
        self.assertEqual(self._titles(search="\u6708\u5ea6\u8ddf\u8e2a"), {"\u7535\u673a\u63a7\u5236\u65b9\u6848"})
        self.assertEqual(self._titles(search="\u6563\u70ed\u95ee\u9898"), {"\u7535\u673a\u63a7\u5236\u65b9\u6848"})

    def test_excel_operators_and_multiple_fields_are_and_combined(self):
        self.assertEqual(
            self._titles(filters={"applicant": {"operator": "starts_with", "value": "\u7532"}}),
            {"\u7535\u673a\u63a7\u5236\u65b9\u6848", "\u7a7a\u5b57\u6bb5\u4e13\u5229"},
        )
        self.assertEqual(
            self._titles(filters={"title": {"operator": "ends_with", "value": "\u65b9\u6848"}}),
            {"\u7535\u673a\u63a7\u5236\u65b9\u6848", "\u4f20\u611f\u5668\u65b9\u6848"},
        )
        self.assertEqual(
            self._titles(filters={"category": {"operator": "is_empty"}}),
            {"\u7a7a\u5b57\u6bb5\u4e13\u5229"},
        )
        self.assertEqual(
            self._titles(filters={
                "applicant": {"operator": "eq", "value": "\u7532\u516c\u53f8"},
                "title": {"operator": "contains", "value": "\u7535\u673a"},
            }),
            {"\u7535\u673a\u63a7\u5236\u65b9\u6848"},
        )


if __name__ == "__main__":
    unittest.main()
