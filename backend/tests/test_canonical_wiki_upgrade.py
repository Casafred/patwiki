import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Patent, PatentDatabase, PatentDatabaseMembership, PatentFamily, CustomField, CustomFieldType, PatentHistory, ViewLocalField, PatentViewFieldValue, FieldDefinition
from app.api.fields import router as fields_router
from app.api.imports import router as imports_router, TEMP_FILES
from app.api.patents import get_patent_family
from app.services.import_review_service import stage_import, apply_batch, list_batch_changes
from app.services.field_registry import get_all_fields_meta
from app.services.relation_service import rebuild_database_families, find_existing_patent_by_number
from app.services.view_service import ViewService


class CanonicalWikiUpgradeTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.master = PatentDatabase(name='主表', is_default=True)
        self.library = PatentDatabase(name='项目库')
        self.db.add_all([self.master, self.library]); self.db.commit()
        app = FastAPI(); app.include_router(fields_router); app.include_router(imports_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def patent(self, **values):
        patent = Patent(title='原始标题', publication_number='CN123456789A', database_id=self.master.id, **values)
        self.db.add(patent); self.db.commit(); return patent

    def stage(self, folder, title='更新标题'):
        content = f'公开号,标题\nCN123456789A,{title}\n'.encode('utf-8-sig')
        path = Path(folder) / 'source.csv'; path.write_bytes(content)
        return stage_import(self.db, content=content, filename='source.csv', sheet_name=None,
            mapping={'公开号': 'publication_number', '标题': 'title'}, database_id=self.library.id, artifact_path=str(path))

    def test_cross_library_latest_version_keeps_one_wiki_and_prior_value(self):
        patent = self.patent()
        with TemporaryDirectory() as folder:
            batch = self.stage(folder)
            conflicts = list_batch_changes(self.db, batch['batch_id'], only_conflicts=True)
            self.assertEqual(conflicts['total'], 1)
            self.assertEqual(conflicts['items'][0]['review_action'], 'adopt')
            result = apply_batch(self.db, batch['batch_id'])
            self.assertEqual(result['updated'], 1)
            self.assertEqual(self.db.query(Patent).count(), 1)
            self.assertEqual(patent.title, '更新标题')
            self.assertTrue(self.db.query(PatentDatabaseMembership).filter_by(patent_id=patent.id, database_id=self.library.id).first())
            timeline = self.client.get(f'/patents/{patent.id}/field/title/versions').json()
            self.assertEqual(timeline['versions'][0]['old_value'], '原始标题')
            self.assertEqual(timeline['imports'][0]['value'], '更新标题')
            history = self.client.get('/import/batches', params={'database_id': self.master.id}).json()
            self.assertEqual(history[0]['id'], batch['batch_id'])

    def test_policy_affects_review_and_rejects_invalid_manual_value(self):
        patent = self.patent()
        response = self.client.put('/fields/title/policy', json={'value_source': 'system', 'value_stability': 'fixed', 'merge_policy': 'keep_existing', 'validation_rules': {'max_length': 5}})
        self.assertEqual(response.status_code, 200)
        with TemporaryDirectory() as folder:
            batch = self.stage(folder, '新标题')
            item = list_batch_changes(self.db, batch['batch_id'], only_conflicts=True)['items'][0]
            self.assertEqual(item['review_action'], 'keep_existing')
            apply_batch(self.db, batch['batch_id']); self.assertEqual(patent.title, '原始标题')
        rejected = self.client.put(f'/patents/{patent.id}/field/title/versions', json={'value': '超过最大长度的标题', 'expected_value': '原始标题'})
        self.assertEqual(rejected.status_code, 400)
        fields = {field['key']: field for field in get_all_fields_meta(self.db)}
        self.assertEqual(fields['technical_problem']['value_source'], 'manual')
        self.assertEqual(fields['claims']['value_stability'], 'variable')
        self.assertEqual(fields['abstract']['value_stability'], 'fixed')

    def test_version_rollback_is_a_new_version_and_checks_concurrent_edit(self):
        patent = self.patent()
        path = f'/patents/{patent.id}/field/title/versions'
        updated = self.client.put(path, json={'value': '新版', 'expected_value': '原始标题'})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(self.client.put(path, json={'value': '过期编辑', 'expected_value': '原始标题'}).status_code, 400)
        restored = self.client.put(path, json={'value': '原始标题', 'expected_value': '新版'})
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(len(restored.json()['versions']), 2)

    def test_rebuild_splits_wrong_generated_family_and_does_not_guess_kind_codes(self):
        family = PatentFamily(family_id='FAM_123456abcdef')
        self.db.add(family); self.db.flush()
        a = self.patent(family_id=family.id, custom_fields={'family_members': 'US123456789A1'})
        b = Patent(title='真实同族', publication_number='US123456789A1', database_id=self.library.id, family_id=family.id)
        c = Patent(title='误关联', publication_number='JP987654321A', database_id=self.library.id, family_id=family.id)
        d = Patent(title='无文献类型号', publication_number='CN999999999', database_id=self.library.id)
        self.db.add_all([b, c, d]); self.db.commit()
        rebuild_database_families(self.db, self.library.id)
        self.assertEqual(a.family_id, b.family_id); self.assertIsNone(c.family_id)
        self.assertIsNone(find_existing_patent_by_number(self.db, 'CN999999999A'))
        members = get_patent_family(a.id, self.master.id, self.db)
        self.assertEqual({item['id'] for item in members['members']}, {a.id, b.id})
        self.assertEqual(members['external_members'], [])

    def test_view_field_is_canonical_and_reads_latest_global_edit(self):
        patent = self.patent()
        view = ViewService.create_view(self.db, name='项目视图', database_id=self.library.id)
        field = ViewService.create_local_field(self.db, view, key='memo', name='项目备注', field_type='text')
        ViewService.set_local_field_value(self.db, view, patent.id, field.key, '从视图录入')
        key = field.promoted_field_key
        self.assertEqual(patent.custom_fields[key], '从视图录入')
        response = self.client.put(f'/patents/{patent.id}/field/{key}/versions', json={'value': '全局最新值', 'expected_value': '从视图录入'})
        self.assertEqual(response.status_code, 200)
        values = ViewService.get_view_patent_with_local_fields(self.db, view, patent)
        self.assertEqual(values['view_local_fields'][field.key], '全局最新值')
        self.db.add(PatentDatabaseMembership(patent_id=patent.id, database_id=self.library.id)); self.db.commit()
        records, count = ViewService.list_view_patents(self.db, view, extra_filters={f'view_local.{field.key}': {'op': 'eq', 'value': '全局最新值'}})
        self.assertEqual(count, 1)
        self.assertEqual(records[0].id, patent.id)

    def test_custom_consolidation_preserves_source_and_future_mapping(self):
        patent = self.patent(custom_fields={'old_notes': '旧自定义备注'})
        self.db.add(CustomField(key='old_notes', name='旧备注', field_type=CustomFieldType.TEXT)); self.db.commit()
        path = '/fields/old_notes/consolidate'
        preview = self.client.post(path, json={'target_field': 'notes'}).json()
        self.assertFalse(preview['applied']); self.assertIsNone(patent.notes)
        applied = self.client.post(path, json={'target_field': 'notes', 'apply': True}).json()
        self.assertTrue(applied['applied']); self.assertEqual(patent.notes, '旧自定义备注')
        self.assertEqual(patent.custom_fields['old_notes'], '旧自定义备注')
        from app.services.import_service import ImportService
        self.assertEqual(ImportService.suggest_mapping(['旧备注'], self.db)[0]['旧备注'], 'notes')

    def test_draft_survives_memory_loss_and_confirm_failure_is_retryable(self):
        with TemporaryDirectory() as folder, patch('app.api.imports.SOURCE_DIR', Path(folder)), patch('app.api.imports.TEMP_DIR', Path(folder)):
            preview = self.client.post('/import/preview', files={'file': ('saved.csv', '公开号,标题\nCN123456789A,恢复导入\n'.encode('utf-8-sig'), 'text/csv')})
            self.assertEqual(preview.status_code, 200, preview.text)
            key = preview.json()['import_id']
            draft = {'database_id': self.library.id, 'mapping': {'公开号': 'publication_number', '标题': 'title'}, 'import_note': '测试恢复'}
            self.assertEqual(self.client.put(f'/import/sessions/{key}', json=draft).status_code, 200)
            TEMP_FILES.pop(key, None)
            Path(folder, f'{key}.bin').unlink()
            saved = self.client.get(f'/import/sessions/{key}').json()
            self.assertEqual(saved['draft']['mapping'], draft['mapping'])
            request = {'import_id': key, 'database_id': self.library.id, 'field_mappings': [{'source_column': '标题', 'target_field': 'title'}]}
            self.assertEqual(self.client.post('/import/confirm', json=request).status_code, 400)
            request['field_mappings'].append({'source_column': '公开号', 'target_field': 'publication_number'})
            staged = self.client.post('/import/confirm', json=request)
            self.assertEqual(staged.status_code, 200, staged.text)
            replacement = self.client.post('/import/confirm', json=request)
            self.assertEqual(replacement.status_code, 200, replacement.text)
            self.assertNotEqual(staged.json()['batch_id'], replacement.json()['batch_id'])
            resumed = self.client.post(f"/import/batches/{replacement.json()['batch_id']}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            saved = self.client.get(f"/import/sessions/{resumed.json()['import_id']}").json()
            self.assertEqual(saved['draft']['mapping'], draft['mapping'])

    def test_upgrade_migrates_legacy_local_values_once(self):
        from app.services.canonical_wiki_migration_service import upgrade_canonical_wiki
        patent = self.patent()
        view = ViewService.create_view(self.db, name='旧视图', database_id=self.library.id)
        field = ViewLocalField(view_id=view.id, key='vlf_old_memo', name='旧备注列', field_type='text')
        self.db.add(field)
        self.db.add(PatentViewFieldValue(view_id=view.id, patent_id=patent.id, field_key=field.key, value='历史独立存值'))
        self.db.commit()
        upgrade_canonical_wiki(self.db)
        self.assertTrue(field.is_promoted)
        self.assertEqual(patent.custom_fields[field.promoted_field_key], '历史独立存值')
        count = self.db.query(PatentHistory).count()
        upgrade_canonical_wiki(self.db)
        self.assertEqual(self.db.query(PatentHistory).count(), count)
        self.assertTrue(self.db.query(FieldDefinition).filter_by(canonical_key='migration:canonical-wiki-2026-10-08.1').first())
