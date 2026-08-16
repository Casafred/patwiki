import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import imports as import_routes
from app.database import Base, get_db
from app.core.exceptions import BadRequestException
from app.models import (
    CustomField, CustomFieldType, FieldObservation, GovernanceDecision,
    ImportBatch, ImportSourceRow, Patent, PatentDatabase, PatentHistory,
)
from app.services.field_registry import get_all_fields_meta
from app.services.import_service import ImportService
from app.services.relation_service import parse_patent_numbers, process_family_members


class ImportPipelineTest(unittest.TestCase):
    def test_family_numbers_accept_common_delimiters_and_dedupe(self):
        raw = " US12304034B2 | CN209954561U；EP3468749B1 / US12304034B2\\CN209954561U\n"
        self.assertEqual(parse_patent_numbers(raw), [
            "US12304034B2",
            "CN209954561U",
            "EP3468749B1",
        ])

    def test_csv_preview_is_case_insensitive_and_keeps_headers(self):
        content = "标题,同族列\n设备,US12304034B2 | CN209954561U\n".encode("utf-8-sig")
        frame, columns = ImportService.parse_excel(content, "patents.CSV")
        self.assertEqual(columns, ["标题", "同族列"])
        self.assertEqual(frame.iloc[0]["同族列"], "US12304034B2 | CN209954561U")

    def test_xlsx_preview_and_invalid_uploads_return_actionable_errors(self):
        output = BytesIO()
        pd.DataFrame({"标题": ["设备"]}).to_excel(output, index=False)
        frame, columns = ImportService.parse_excel(output.getvalue(), "patents.XLSX")
        self.assertEqual(columns, ["标题"])
        self.assertEqual(frame.iloc[0]["标题"], "设备")

        with self.assertRaisesRegex(BadRequestException, "仅支持"):
            ImportService.parse_excel(b"data", "patents.pdf")
        with self.assertRaisesRegex(BadRequestException, "上传文件为空"):
            ImportService.parse_excel(b"", "patents.xlsx")

    def test_family_column_mapping_includes_export_variants(self):
        from app.services.import_service import STANDARD_FIELD_MAPPINGS

        self.assertEqual(STANDARD_FIELD_MAPPINGS["同族列"], "family_members")
        self.assertEqual(STANDARD_FIELD_MAPPINGS["family members"], "family_members")

    def test_family_members_are_created_and_linked_in_database_scope(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            database = PatentDatabase(name="测试库")
            current = Patent(
                title="主专利",
                application_number="US12304034B2",
                country="US",
                database=database,
            )
            db.add_all([database, current])
            db.commit()

            result = process_family_members(
                db,
                current,
                parse_patent_numbers("CN209954561U | EP3468749B1"),
                database_id=database.id,
            )
            db.commit()

            self.assertIsNotNone(result["family_id"])
            members = db.query(Patent).filter(
                Patent.database_id == database.id,
                Patent.family_id == current.family_id,
            ).all()
            self.assertEqual(len(members), 3)
            self.assertEqual(
                {member.application_number or member.publication_number for member in members},
                {"US12304034B2", "CN209954561U", "EP3468749B1"},
            )
        finally:
            db.close()
            engine.dispose()

    def test_family_hash_consistent_across_rows_with_different_current_number(self):
        # 回归：同一组专利无论从哪一行的同族列触发，都应得到相同的 family_id。
        # 旧算法用号字符串做哈希，current_num 取 application_number or publication_number，
        # 导致 CN115319697B 行和 US12643214B2 行产生不同的 family hash，
        # 同族成员被拆到不同的 PatentFamily，图谱看不到连接。
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            database = PatentDatabase(name="测试库")
            # CN115319697B 有 application_number（不同于 publication_number）
            patent_a = Patent(
                title="专利A",
                application_number="CN202210123456",
                publication_number="CN115319697B",
                country="CN",
                database=database,
            )
            # US12643214B2 有 application_number（不同于 publication_number）
            patent_b = Patent(
                title="专利B",
                application_number="US18123456",
                publication_number="US12643214B2",
                country="US",
                database=database,
            )
            db.add_all([database, patent_a, patent_b])
            db.commit()

            # 从 A 的行触发：同族列列出 B 的公开号
            family_numbers_a = ["US12643214B2", "CN115319696A"]
            result_a = process_family_members(
                db, patent_a, family_numbers_a, database_id=database.id,
            )
            db.commit()
            family_id_a = patent_a.family_id

            # 从 B 的行触发：同族列列出 A 的公开号
            family_numbers_b = ["CN115319697B", "CN115319696A"]
            result_b = process_family_members(
                db, patent_b, family_numbers_b, database_id=database.id,
            )
            db.commit()
            family_id_b = patent_b.family_id

            # 关键断言：两次处理应得到相同的 family_id
            self.assertEqual(family_id_a, family_id_b,
                "同一组专利从不同行触发时应得到相同的 family_id")
            # A 和 B 应在同一个族中
            self.assertEqual(patent_a.family_id, patent_b.family_id)
        finally:
            db.close()
            engine.dispose()

    def test_find_or_create_patent_finds_cross_database_match(self):
        # 回归：UNIQUE 约束 (publication_number, country) 不含 database_id，
        # 但 _find_or_create_patent_by_number 之前按 database_id 过滤查找，
        # 导致同号专利在其他库存在时尝试创建重复记录，触发 IntegrityError。
        from app.services.relation_service import _find_or_create_patent_by_number
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            db1 = PatentDatabase(name="库1")
            db2 = PatentDatabase(name="库2")
            existing = Patent(
                title="已有专利",
                publication_number="DE102023212809A1",
                country="DE",
                database=db1,
            )
            db.add_all([db1, db2, existing])
            db.commit()

            # 在 db2 中查找同号专利——应找到 db1 中的已有记录，不创建占位
            found = _find_or_create_patent_by_number(db, "DE102023212809A1", database_id=db2.id)
            self.assertIsNotNone(found)
            self.assertEqual(found.id, existing.id)
            # 不应创建新专利
            self.assertEqual(db.query(Patent).count(), 1)
        finally:
            db.close()
            engine.dispose()

    def test_mapping_validation_keeps_unknown_columns_out_of_formal_fields(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            field = CustomField(
                key="cf_formula",
                name="计算结果",
                field_type=CustomFieldType.FORMULA,
                is_active=True,
            )
            db.add(field)
            db.commit()

            issues = ImportService.validate_mapping(
                ["标题", "跳过列", "公式列", "附件列", "提议列"],
                {
                    "标题": "title",
                    "公式列": "cf_formula",
                    "附件列": "attachments",
                    "提议列": "cf_proposed_abc123",
                },
                db,
            )
            # 空目标允许保留原始值，但未注册的字段不可绕过字段治理。
            self.assertEqual(
                {issue["column"] for issue in issues},
                {"公式列", "附件列", "提议列"},
            )
            self.assertIn("attachments", {field["key"] for field in get_all_fields_meta(db)})
        finally:
            db.close()
            engine.dispose()

    def test_priority_number_mapping_validates_after_system_field_registration(self):
        # 回归：'优先权号' -> 'priority_number' 之前因 priority_number 未注册到
        # SYSTEM_FIELD_KEYS 而被 validate_mapping 误判为"目标字段不存在"，
        # 导致整批导入被阻断。
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            issues = ImportService.validate_mapping(
                ["标题", "优先权号", "优先权国家", "优先权日", "CPC分类号", "风险描述"],
                {
                    "标题": "title",
                    "优先权号": "priority_number",
                    "优先权国家": "priority_country",
                    "优先权日": "priority_date",
                    "CPC分类号": "cpc_main",
                    "风险描述": "risk_description",
                },
                db,
            )
            self.assertEqual(issues, [])
        finally:
            db.close()
            engine.dispose()

    def test_suggest_mapping_does_not_fuzzy_match_family_columns(self):
        # "同族备注" 不能因为名字里带"同族"就被塞进同族关系映射，
        # 也不能自动创建正式字段；它应保留为待治理属性。
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            mapping, issues = ImportService.suggest_mapping(
                ["同族专利号", "同族备注", "同族申请日", "标题"],
                db,
            )
            self.assertEqual(mapping["同族专利号"], "family_members")
            self.assertEqual(mapping["标题"], "title")
            # 同族备注 / 同族申请日 应为未映射属性，而非 family_members。
            self.assertEqual(mapping["同族备注"], "")
            self.assertEqual(mapping["同族申请日"], "")
            self.assertNotEqual(mapping["同族备注"], "family_members")
            self.assertNotEqual(mapping["同族申请日"], "family_members")
            # 预览阶段不应实际写库
            self.assertEqual(db.query(CustomField).count(), 0)
            self.assertEqual(issues, [])
        finally:
            db.close()
            engine.dispose()

    def test_unknown_columns_are_retained_with_row_and_wiki_provenance(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        original_temp_dir = import_routes.TEMP_DIR
        original_source_dir = import_routes.SOURCE_DIR
        try:
            database = PatentDatabase(name="治理测试库")
            db.add(database)
            db.commit()

            with TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                import_routes.TEMP_DIR = root / "sessions"
                import_routes.SOURCE_DIR = root / "artifacts"
                import_routes.TEMP_DIR.mkdir()
                import_routes.SOURCE_DIR.mkdir()
                import_routes.TEMP_FILES.clear()

                app = FastAPI()
                app.include_router(import_routes.router)
                app.dependency_overrides[get_db] = lambda: db
                client = TestClient(app)
                content = "标题,公开号,检索师临时标注,无效过程列\n示例专利,CN123456789A,需要二次判断,草稿\n".encode("utf-8-sig")
                preview = client.post(
                    "/import/preview",
                    files={"file": ("月度跟踪.csv", content, "text/csv")},
                )
                self.assertEqual(preview.status_code, 200)
                self.assertEqual(preview.json()["suggested_mapping"]["检索师临时标注"], "")

                result = client.post("/import/confirm", json={
                    "import_id": preview.json()["import_id"],
                    "field_mappings": [
                        {"source_column": "标题", "target_field": "title"},
                        {"source_column": "公开号", "target_field": "publication_number"},
                        {"source_column": "检索师临时标注", "target_field": ""},
                        {"source_column": "无效过程列", "target_field": "__skip__"},
                    ],
                    "database_id": database.id,
                    "source_table_title": "检索师月度跟踪",
                    "source_system": "商业专利数据库",
                })
                self.assertEqual(result.status_code, 200, result.text)
                body = result.json()
                self.assertEqual(body["created"], 1)
                self.assertEqual(body["unmapped_retained"], 1)

                self.assertEqual(db.query(CustomField).count(), 0)
                batch = db.query(ImportBatch).filter(ImportBatch.id == body["batch_id"]).one()
                self.assertEqual(batch.source_table_title, "检索师月度跟踪")
                self.assertEqual(batch.source_system, "商业专利数据库")
                self.assertTrue(Path(batch.artifact_path).exists())

                source_row = db.query(ImportSourceRow).filter(ImportSourceRow.import_batch_id == batch.id).one()
                self.assertEqual(source_row.resolution_status, "resolved")
                self.assertEqual(source_row.raw_row["检索师临时标注"], "需要二次判断")
                self.assertEqual(source_row.raw_row["无效过程列"], "草稿")
                observation = db.query(FieldObservation).filter(
                    FieldObservation.import_batch_id == batch.id,
                    FieldObservation.source_field_name == "检索师临时标注",
                ).one()
                self.assertEqual(observation.field_resolution, "unmapped_retained")
                self.assertEqual(observation.raw_value, "需要二次判断")
                self.assertIsNone(observation.canonical_field_key)
                self.assertEqual(
                    db.query(FieldObservation).filter(
                        FieldObservation.import_batch_id == batch.id,
                        FieldObservation.source_field_name == "无效过程列",
                    ).count(),
                    0,
                )

                histories = db.query(PatentHistory).filter(PatentHistory.import_batch_id == batch.id).all()
                self.assertEqual({history.field_key for history in histories}, {"title", "publication_number"})
                self.assertTrue(all(history.source_table_title == "检索师月度跟踪" for history in histories))
        finally:
            import_routes.TEMP_DIR = original_temp_dir
            import_routes.SOURCE_DIR = original_source_dir
            import_routes.TEMP_FILES.clear()
            db.close()
            engine.dispose()

    def test_governance_decision_maps_and_adopts_value_with_append_only_history(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            database = PatentDatabase(name="治理决策测试库")
            patent = Patent(
                title="待治理专利",
                publication_number="CN123456789A",
                country="CN",
                database=database,
            )
            batch = ImportBatch(
                filename="治理测试.csv",
                source_table_title="检索师临时表",
                worksheet_name="Sheet1",
                mapping_version="v-governance-1",
            )
            db.add_all([database, patent, batch])
            db.flush()
            source_row = ImportSourceRow(
                import_batch_id=batch.id,
                source_row=2,
                raw_row={"公开号": "CN123456789A", "技术标签": "通信"},
                patent_id=patent.id,
            )
            db.add(source_row)
            db.flush()
            observation = FieldObservation(
                import_batch_id=batch.id,
                source_row_id=source_row.id,
                patent_id=patent.id,
                source_field_name="技术标签",
                raw_value="通信",
                normalized_value="通信",
                candidate_value="通信",
                difference_type="unknown",
                field_resolution="unmapped_retained",
                proposed_action="retain",
            )
            db.add(observation)
            db.commit()

            app = FastAPI()
            app.include_router(import_routes.router)
            app.dependency_overrides[get_db] = lambda: db
            client = TestClient(app)
            response = client.patch(
                f"/import/observations/{observation.id}",
                json={
                    "action": "map_existing",
                    "canonical_field_key": "category",
                    "adopted_value": True,
                    "decided_by": "检索师",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["updated_count"], 1)
            db.refresh(patent)
            db.refresh(observation)
            self.assertEqual(patent.category, "通信")
            self.assertEqual(observation.field_resolution, "mapped")
            self.assertEqual(observation.final_decision, "mapped")
            self.assertEqual(
                db.query(GovernanceDecision).filter(GovernanceDecision.observation_id == observation.id).count(),
                1,
            )
            history = db.query(PatentHistory).filter(
                PatentHistory.patent_id == patent.id,
                PatentHistory.source == "governance",
            ).one()
            self.assertEqual(history.field_key, "category")
            self.assertEqual(history.changed_by, "检索师")
        finally:
            db.close()
            engine.dispose()

    def test_governance_scope_keeps_evidence_and_returns_decision_history(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            database = PatentDatabase(name="治理范围测试库")
            patent_a = Patent(title="专利A", publication_number="CN100000001A", database=database)
            patent_b = Patent(title="专利B", publication_number="CN100000002A", database=database)
            batch_a = ImportBatch(
                filename="批次A.csv",
                source_table_title="月度跟踪A",
                worksheet_name="Sheet1",
                mapping_version="v-governance-1",
            )
            batch_b = ImportBatch(
                filename="批次B.csv",
                source_table_title="月度跟踪B",
                worksheet_name="Sheet1",
            )
            db.add_all([database, patent_a, patent_b, batch_a, batch_b])
            db.flush()

            def add_observation(batch, patent, field_name, value, row_number):
                source_row = ImportSourceRow(
                    import_batch_id=batch.id,
                    source_row=row_number,
                    raw_row={field_name: value},
                    patent_id=patent.id,
                )
                db.add(source_row)
                db.flush()
                observation = FieldObservation(
                    import_batch_id=batch.id,
                    source_row_id=source_row.id,
                    patent_id=patent.id,
                    source_field_name=field_name,
                    raw_value=value,
                    normalized_value=value,
                    candidate_value=value,
                    difference_type="unknown",
                    field_resolution="unmapped_retained",
                    proposed_action="retain",
                )
                db.add(observation)
                db.flush()
                return observation

            same_field_a1 = add_observation(batch_a, patent_a, "临时字段", "A1", 2)
            same_field_a2 = add_observation(batch_a, patent_b, "临时字段", "A2", 3)
            other_field = add_observation(batch_a, patent_a, "其他字段", "B1", 4)
            same_field_b = add_observation(batch_b, patent_a, "临时字段", "C1", 2)
            db.commit()

            app = FastAPI()
            app.include_router(import_routes.router)
            app.dependency_overrides[get_db] = lambda: db
            client = TestClient(app)

            response = client.patch(
                f"/import/observations/{same_field_a1.id}",
                json={
                    "action": "retain_source",
                    "apply_to_batch": True,
                    "decided_by": "检索师",
                    "reason": "先保留来源语义",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["updated_count"], 2)
            db.refresh(same_field_a1)
            db.refresh(same_field_a2)
            db.refresh(other_field)
            db.refresh(same_field_b)
            self.assertEqual(same_field_a1.field_resolution, "source_only")
            self.assertEqual(same_field_a2.field_resolution, "source_only")
            self.assertEqual(other_field.field_resolution, "unmapped_retained")
            self.assertEqual(same_field_b.field_resolution, "unmapped_retained")

            decisions = client.get(f"/import/observations/{same_field_a2.id}/decisions")
            self.assertEqual(decisions.status_code, 200, decisions.text)
            self.assertEqual(decisions.json()[0]["action"], "retain_source")
            self.assertEqual(decisions.json()[0]["scope"], "batch_source_field")
            self.assertEqual(decisions.json()[0]["mapping_version"], "v-governance-1")

            response = client.patch(
                f"/import/observations/{other_field.id}",
                json={"action": "ignore", "decided_by": "检索师"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            db.refresh(other_field)
            self.assertEqual(other_field.field_resolution, "ignored")
            self.assertEqual(
                db.query(FieldObservation).filter(FieldObservation.id == other_field.id).count(),
                1,
            )

            default_queue = client.get("/import/unmapped")
            self.assertEqual(default_queue.status_code, 200, default_queue.text)
            self.assertEqual(default_queue.json()["total"], 1)
            complete_export = client.get("/import/unmapped/export")
            self.assertEqual(complete_export.status_code, 200, complete_export.text)
            self.assertIn("A1", complete_export.text)
            self.assertIn("B1", complete_export.text)
            self.assertIn("C1", complete_export.text)
        finally:
            db.close()
            engine.dispose()

    def test_invalid_dates_are_reported_instead_of_silently_dropped(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            with self.assertRaisesRegex(ValueError, "日期值无法识别"):
                ImportService._row_to_patent_data(
                    {"标题": "测试", "申请日": "not-a-date"},
                    {"标题": "title", "申请日": "filing_date"},
                    db,
                )
        finally:
            db.close()
            engine.dispose()

    def test_governance_date_validation_is_actionable(self):
        with self.assertRaisesRegex(BadRequestException, "无法写入日期字段"):
            import_routes._coerce_governance_value("filing_date", "not-a-date")


if __name__ == "__main__":
    unittest.main()
