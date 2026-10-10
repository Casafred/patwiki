import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Patent, Product, Tag, TagGroup, CrossTableLink, PatentHistory
from app.core.exceptions import BadRequestException
from app.services.tag_service import (
    apply_classification, classification_fields, ensure_product_tags,
    export_config, import_config, product_predicate, sync_product_tags, validate_tag,
)
from app.services.export_service import ExportService
from app.services.patent_service import PatentService


class ClassificationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.group = TagGroup(name="Technology")
        self.other = TagGroup(name="Region")
        self.db.add_all([self.group, self.other])
        self.db.flush()
        self.root = Tag(name="Devices", group_id=self.group.id)
        self.region = Tag(name="CN", group_id=self.other.id)
        self.db.add_all([self.root, self.region])
        self.db.flush()
        self.child = Tag(name="Sensors", group_id=self.group.id, parent_id=self.root.id)
        self.patent = Patent(title="Test", publication_number="CN123456789A", tags=[self.root, self.region])
        self.db.add_all([self.child, self.patent])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_scoped_replace_export_and_audit(self):
        apply_classification(self.db, [self.patent.id], [self.child.id], "replace", self.group.id)
        self.assertEqual({tag.id for tag in self.patent.tags}, {self.child.id, self.region.id})
        field = next(item for item in classification_fields(self.db) if item["taxonomy_group_id"] == self.group.id)
        value = ExportService._field_value(self.patent, field["key"])
        self.assertEqual(ExportService._option_label(field, value), "Devices / Sensors")
        self.assertEqual(self.db.query(PatentHistory).filter_by(field_key=field["key"]).count(), 1)
        apply_classification(self.db, [self.patent.id], [], "replace", self.group.id)
        self.assertEqual([tag.id for tag in self.patent.tags], [self.region.id])

    def test_hierarchy_and_bulk_validation(self):
        for parent_id in (self.child.id, self.region.id):
            with self.assertRaises(BadRequestException):
                validate_tag(self.db, {"name": self.root.name, "group_id": self.group.id, "parent_id": parent_id}, self.root.id)
        with self.assertRaises(BadRequestException):
            apply_classification(self.db, [self.patent.id], [self.region.id], "replace", self.group.id)
        with self.assertRaises(BadRequestException):
            apply_classification(self.db, [self.patent.id, 99999], [self.child.id], "replace", self.group.id)
        self.assertIn(self.root, self.patent.tags)

    def test_product_associations_and_primary_sync(self):
        product = Product(name="Device", code="D1")
        self.db.add(product)
        self.db.flush()
        group = ensure_product_tags(self.db)
        tag = self.db.query(Tag).filter_by(product_id=product.id).one()
        direct = Patent(title="Direct", publication_number="CN123456788A", product_id=product.id)
        linked = Patent(title="Linked", publication_number="CN123456787A")
        self.db.add_all([direct, linked])
        self.db.flush()
        self.db.add(CrossTableLink(link_field_key="cf_products", source_table="patents", source_record_id=linked.id,
                                   target_table="products", target_record_id=product.id))
        apply_classification(self.db, [self.patent.id], [tag.id], "add", group.id)
        self.assertEqual(self.patent.product_id, product.id)
        self.assertEqual(self.db.query(Patent).filter(product_predicate(product.id)).count(), 3)
        stats = PatentService.get_stats(self.db)
        self.assertEqual(next(item["count"] for item in stats["by_product"] if item["id"] == product.id), 3)
        apply_classification(self.db, [self.patent.id], [], "replace", group.id)
        self.assertIsNone(self.patent.product_id)
        sync_product_tags(self.db, direct)
        self.assertIn(tag, direct.tags)

    def test_portable_import_is_idempotent_and_atomic(self):
        product = Product(name="Portable", code="P1")
        self.db.add(product)
        self.db.flush()
        group = ensure_product_tags(self.db)
        config = export_config(self.db, [self.group.id, group.id])
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as target:
                target.add(TagGroup(name="Unrelated"))
                target.commit()
                import_config(target, config)
                import_config(target, config)
                child = target.query(Tag).filter_by(name="Sensors").one()
                self.assertEqual(target.get(Tag, child.parent_id).name, "Devices")
                self.assertNotEqual(child.group_id, self.group.id)
                self.assertEqual(target.query(Product).filter_by(code="P1").count(), 1)
                self.assertEqual(target.query(Tag).count(), 3)
                invalid = {"format": "patwiki-classifications", "version": 1, "systems": [
                    {"name": "Rollback", "nodes": [{"key": "x", "name": "Cycle", "parent_key": "x"}]}]}
                with self.assertRaises(BadRequestException):
                    import_config(target, invalid)
                self.assertIsNone(target.query(TagGroup).filter_by(name="Rollback").first())
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
