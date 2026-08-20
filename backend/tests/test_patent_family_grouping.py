import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Patent, PatentDatabase, PatentFamily
from app.services.patent_service import PatentService


class PatentFamilyGroupingTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        database = PatentDatabase(name="同族测试库", code="FAMILY_GROUP_DB")
        self.db.add(database)
        self.db.flush()
        family = PatentFamily(family_id="FAM_GROUP_TEST", family_type="simple")
        self.db.add(family)
        self.db.flush()
        self.db.add_all([
            Patent(
                title="族成员 A",
                publication_number="CN300000001A",
                database_id=database.id,
                family_id=family.id,
            ),
            Patent(
                title="族成员 B",
                publication_number="US300000001A",
                database_id=database.id,
                family_id=family.id,
            ),
            Patent(
                title="无族专利",
                publication_number="CN300000002A",
                database_id=database.id,
            ),
        ])
        self.db.commit()
        self.database_id = database.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_group_by_family_keeps_members_as_rows_and_adds_stable_group_metadata(self):
        patents, total = PatentService.list_patents(
            self.db,
            database_id=self.database_id,
            page=1,
            page_size=20,
            group_by_family=True,
        )
        self.assertEqual(total, 3)
        self.assertEqual(len(patents), 3)
        self.assertEqual({patent.title for patent in patents[:2]}, {"族成员 A", "族成员 B"})
        self.assertEqual([patent.family_size for patent in patents[:2]], [2, 2])
        self.assertEqual([patent.family_key for patent in patents[:2]], ["FAM_GROUP_TEST", "FAM_GROUP_TEST"])
        self.assertIsNone(patents[2].family_id)

    def test_family_size_is_limited_to_current_database_scope(self):
        other_database = PatentDatabase(name="另一同族库", code="FAMILY_GROUP_OTHER")
        self.db.add(other_database)
        self.db.flush()
        family_id = self.db.query(PatentFamily).filter(PatentFamily.family_id == "FAM_GROUP_TEST").one().id
        self.db.add(Patent(
            title="跨库同族成员",
            publication_number="JP300000001A",
            database_id=other_database.id,
            family_id=family_id,
        ))
        self.db.commit()

        patents, _ = PatentService.list_patents(
            self.db,
            database_id=self.database_id,
            page=1,
            page_size=20,
            group_by_family=True,
        )
        family_members = [patent for patent in patents if patent.family_id == family_id]
        self.assertEqual(len(family_members), 2)
        self.assertEqual({patent.family_size for patent in family_members}, {2})


if __name__ == "__main__":
    unittest.main()
