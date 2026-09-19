import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelDrawingImage
from PIL import Image as PillowImage
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models import Attachment, Patent, PatentDatabase
from app.services.attachment_service import AttachmentService
from app.services.excel_image_service import extract_embedded_images
from app.services.import_review_service import apply_batch, list_batch_changes, review_batch, stage_import


class ExcelEmbeddedImageTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.database = PatentDatabase(name="图片测试库")
        self.db.add(self.database)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def workbook_bytes() -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "专利数据"
        sheet.append(["公开号", "标题", "附图"])
        sheet.append(["CN123456789A1", "含图片专利", None])
        image_buffer = BytesIO()
        with PillowImage.new("RGB", (32, 20), (18, 122, 92)) as image:
            image.save(image_buffer, format="PNG")
        image_buffer.seek(0)
        sheet.add_image(ExcelDrawingImage(image_buffer), "C2")
        output = BytesIO()
        workbook.save(output)
        return output.getvalue()

    def test_extracts_cell_image_and_applies_after_review(self):
        content = self.workbook_bytes()
        images = extract_embedded_images(content, "images.xlsx", "专利数据", ["公开号", "标题", "附图"])
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].source_row, 2)
        self.assertEqual(images[0].source_column, 2)
        self.assertEqual(images[0].source_cell, "C2")
        self.assertEqual(images[0].source_field_name, "附图")
        self.assertEqual(images[0].mime_type, "image/png")
        self.assertEqual((images[0].width, images[0].height), (32, 20))
        self.assertTrue(images[0].sha256)

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "images.xlsx"
            artifact.write_bytes(content)
            with patch.object(settings, "FILES_DIR", root / "files"):
                result = stage_import(
                    self.db,
                    content=content,
                    filename="images.xlsx",
                    sheet_name="专利数据",
                    mapping={"公开号": "publication_number", "标题": "title", "附图": "attachments"},
                    database_id=self.database.id,
                    artifact_path=str(artifact),
                )
                self.assertEqual(result["embedded_image_count"], 1)
                changes = list_batch_changes(self.db, result["batch_id"])["items"]
                image_change = next(item for item in changes if item["canonical_field_key"] == "attachments")
                self.assertIn("image", image_change["candidate_value"])

                review_batch(self.db, result["batch_id"], default_action_name="adopt")
                applied = apply_batch(self.db, result["batch_id"])
                self.assertEqual(applied["created"], 1)

                patent = self.db.query(Patent).filter(Patent.publication_number == "CN123456789A1").one()
                attachment = self.db.query(Attachment).one()
                self.assertEqual(attachment.patent_id, patent.id)
                self.assertEqual(attachment.source_type, "excel_embedded")
                self.assertEqual(attachment.import_batch_id, result["batch_id"])
                self.assertEqual((attachment.source_sheet, attachment.source_cell), ("专利数据", "C2"))
                self.assertEqual((attachment.source_row, attachment.source_column), (2, 2))
                self.assertEqual((attachment.width, attachment.height), (32, 20))
                self.assertTrue(AttachmentService.path(attachment).is_file())
                self.assertEqual(len(patent.custom_fields["attachments"]), 1)
                self.assertTrue(patent.custom_fields["attachments"][0]["preview_url"].endswith("/preview"))


if __name__ == "__main__":
    unittest.main()
