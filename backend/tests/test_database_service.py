import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Citation,
    FieldObservation,
    ImportBatch,
    ImportSourceRow,
    Patent,
    PatentDatabase,
    PatentHistory,
    PatentView,
)
from app.services.database_service import DatabaseService


class DatabaseServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.execute(text("PRAGMA foreign_keys=ON"))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_force_delete_removes_database_children_before_patents(self):
        database = PatentDatabase(name="可删除库", code="DELETE_TEST")
        self.db.add(database)
        self.db.flush()
        view = PatentView(name="删除库视图", database_id=database.id)
        current = Patent(database_id=database.id, title="当前专利")
        cited = Patent(database_id=database.id, title="被引用专利")
        self.db.add_all([view, current, cited])
        self.db.flush()
        self.db.add(Citation(citing_patent_id=current.id, cited_patent_id=cited.id))
        batch = ImportBatch(
            filename="delete.csv",
            review_config={"database_id": database.id},
            created_patent_ids=[current.id],
        )
        self.db.add(batch)
        self.db.flush()
        current.source_batch_id = batch.id
        source = ImportSourceRow(
            import_batch_id=batch.id,
            source_row=2,
            raw_row={"公开号": "CN123456789A1"},
        )
        self.db.add(source)
        self.db.flush()
        self.db.add(FieldObservation(
            import_batch_id=batch.id,
            source_row_id=source.id,
            patent_id=current.id,
            source_field_name="标题",
            raw_value="当前专利",
        ))
        self.db.add(PatentHistory(
            patent_id=current.id,
            field_key="title",
            old_value=None,
            new_value="当前专利",
            import_batch_id=batch.id,
            source="import",
        ))
        self.db.commit()
        database_id = database.id
        patent_ids = [current.id, cited.id]
        view_id = view.id
        batch_id = batch.id
        source_id = source.id

        self.assertTrue(DatabaseService.delete_database(self.db, database, force=True))
        self.assertIsNone(self.db.query(PatentDatabase).filter_by(id=database_id).first())
        self.assertEqual(self.db.query(Patent).filter(Patent.id.in_(patent_ids)).count(), 0)
        self.assertEqual(self.db.query(Citation).count(), 0)
        self.assertEqual(self.db.query(PatentView).filter_by(id=view_id).count(), 0)
        self.assertEqual(self.db.query(ImportBatch).filter_by(id=batch_id).count(), 0)
        self.assertEqual(self.db.query(ImportSourceRow).filter_by(id=source_id).count(), 0)
        self.assertEqual(self.db.query(FieldObservation).filter_by(import_batch_id=batch_id).count(), 0)
        self.assertEqual(self.db.query(PatentHistory).filter_by(import_batch_id=batch_id).count(), 0)


if __name__ == "__main__":
    unittest.main()
