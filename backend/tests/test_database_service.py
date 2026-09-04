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
    PatentDatabaseMembership,
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

    def test_force_delete_detaches_duplicate_patent_in_another_database(self):
        target_db = PatentDatabase(name="目标库", code="DELETE_TARGET")
        other_db = PatentDatabase(name="其他库", code="DELETE_OTHER")
        self.db.add_all([target_db, other_db])
        self.db.flush()
        deleted_patent = Patent(database_id=target_db.id, title="待删除专利")
        self.db.add(deleted_patent)
        self.db.flush()
        external_patent = Patent(
            database_id=other_db.id,
            title="其他库中的副本",
            is_duplicate=True,
            duplicate_of=deleted_patent.id,
        )
        self.db.add(external_patent)
        self.db.commit()
        deleted_patent_id = deleted_patent.id
        external_patent_id = external_patent.id

        self.assertTrue(DatabaseService.delete_database(self.db, target_db, force=True))

        self.assertIsNone(self.db.query(Patent).filter_by(id=deleted_patent_id).first())
        surviving = self.db.query(Patent).filter_by(id=external_patent_id).one()
        self.assertIsNone(surviving.duplicate_of)

    def test_force_delete_shared_wiki_keeps_default_database_record(self):
        default_db = PatentDatabase(name="默认库", code="SHARED_DEFAULT", is_default=True)
        imported_db = PatentDatabase(name="导入库", code="SHARED_IMPORT")
        self.db.add_all([default_db, imported_db])
        self.db.flush()
        shared = Patent(database_id=default_db.id, title="共享 Wiki")
        self.db.add(shared)
        self.db.flush()
        self.db.add_all([
            PatentDatabaseMembership(patent_id=shared.id, database_id=default_db.id),
            PatentDatabaseMembership(patent_id=shared.id, database_id=imported_db.id),
        ])
        self.db.commit()
        imported_database_id = imported_db.id

        self.assertTrue(DatabaseService.delete_database(self.db, imported_db, force=True))
        self.assertIsNotNone(self.db.query(Patent).filter_by(id=shared.id).first())
        self.assertIsNotNone(self.db.query(PatentDatabase).filter_by(id=default_db.id).first())
        self.assertIsNotNone(self.db.query(PatentDatabaseMembership).filter_by(
            patent_id=shared.id, database_id=default_db.id,
        ).first())
        self.assertIsNone(self.db.query(PatentDatabaseMembership).filter_by(
            patent_id=shared.id, database_id=imported_database_id,
        ).first())

    def test_force_delete_cleans_legacy_physical_database_child_table(self):
        database = PatentDatabase(name="旧表删除库", code="DELETE_LEGACY")
        self.db.add(database)
        self.db.commit()
        database_id = database.id
        self.db.execute(text(
            "CREATE TABLE legacy_database_child ("
            "id INTEGER PRIMARY KEY, "
            "database_id INTEGER NOT NULL REFERENCES patent_databases(id)"
            ")"
        ))
        self.db.execute(text(
            "INSERT INTO legacy_database_child (database_id) VALUES (:database_id)"
        ), {"database_id": database_id})
        self.db.commit()

        self.assertTrue(DatabaseService.delete_database(self.db, database, force=True))
        self.assertEqual(self.db.execute(text("SELECT COUNT(*) FROM legacy_database_child")).scalar(), 0)
        self.assertIsNone(self.db.query(PatentDatabase).filter_by(id=database_id).first())


if __name__ == "__main__":
    unittest.main()
