"""P1-10 ~ P1-16 后端优化项的快速回归测试。

覆盖：
  P1-10  合并后的 PATCH /patents/{id}/field/{key} 支持 source_view_id
  P1-11  filter_config 标准化 + column_config=[] 语义
  P1-12  GET /fields?view_id=xxx 返回 vlf_ 本地字段
  P1-13  历史记录 source 字段（view_edit / import / ai）
  P1-14  部门总表强制 column_config=[]
  P1-15  导入到视图时未知列自动创建为 vlf_ 本地字段
  P1-16  视图编辑权限校验（owner / editor / viewer）
"""
import sys
import os
import json

sys.path.insert(0, "/workspace/backend")

# 干净 DB
DB_PATH = "/workspace/data/patwiki.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

from app.database import SessionLocal, engine, Base
from app.models import (
    User, PatentDatabase, DatabaseMembership, Patent, PatentView,
    ViewLocalField, PatentHistory, HistorySource,
)
from app.services.view_service import ViewService
from app.services.import_service import ImportService, auto_create_view_local_field
from app.services.field_registry import get_all_fields_meta

Base.metadata.create_all(bind=engine)

db = SessionLocal()

passed = 0
failed = 0


def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [OK] {msg}")
    else:
        failed += 1
        print(f"  [FAIL] {msg}")


# -------- 准备：用户 + 库 + 部门总表 + 个人视图 --------
owner = User(username="owner1", display_name="Owner")
editor = User(username="editor1", display_name="Editor")
viewer = User(username="viewer1", display_name="Viewer")
db.add_all([owner, editor, viewer])
db.flush()

db_obj = PatentDatabase(name="测试库1", description="测试", is_default=True)
db.add(db_obj)
db.flush()

db.add_all([
    DatabaseMembership(user_id=owner.id, database_id=db_obj.id, role="owner"),
    DatabaseMembership(user_id=editor.id, database_id=db_obj.id, role="editor"),
    DatabaseMembership(user_id=viewer.id, database_id=db_obj.id, role="viewer"),
])
db.flush()

print("[1] P1-14 部门总表强制 column_config=[]")
master = ViewService.get_department_master_view(db, db_obj.id)
if master is None:
    master = ViewService.create_view(
        db,
        name=f"{db_obj.name} - 部门总表",
        database_id=db_obj.id,
        description="部门总表",
        view_type="department_master",
        is_department_master=True,
        filter_config={},
        column_config=[],
        sort_config={"sort_by": "filing_date", "sort_order": "desc"},
    )
ok(master is not None, "部门总表自动创建")
ok(master.column_config == [], f"部门总表 column_config 应为 [], 实际: {master.column_config}")

# 试图更新部门总表的 column_config 为非空，应被拒绝
try:
    ViewService.update_view(db, master, {"column_config": [{"key": "title", "order": 1}]})
    ok(False, "部门总表应拒绝非空 column_config 更新")
except Exception as e:
    ok(True, f"部门总表拒绝非空 column_config 更新: {e}")
ok(master.column_config == [], f"拒绝后 column_config 仍为 [], 实际: {master.column_config}")

# filter_config 标准化
ViewService.update_view(db, master, {"filter_config": {"title": {"contains": "abc"}}})
ok(master.filter_config == {"title": {"contains": "abc"}}, "filter_config 标准化存储")


print("\n[2] P1-16 视图编辑权限校验")
# editor 不能编辑部门总表
ok(ViewService.check_view_write_permission(db, master, owner.id) is True, "owner 可编辑部门总表")
ok(ViewService.check_view_write_permission(db, master, editor.id) is False, "editor 不可编辑部门总表")
ok(ViewService.check_view_write_permission(db, master, viewer.id) is False, "viewer 不可编辑部门总表")

# 个人视图
personal = ViewService.create_view(
    db,
    database_id=db_obj.id,
    name="我的小表",
    view_type="personal",
    owner_id=owner.id,
    filter_config={},
    column_config=[],
    sort_config={},
)
ok(personal is not None, "个人视图创建成功")
ok(ViewService.check_view_write_permission(db, personal, owner.id) is True, "owner 可编辑个人视图")
ok(ViewService.check_view_write_permission(db, personal, editor.id) is False, "editor 不可编辑他人 personal 视图")
ok(ViewService.check_view_write_permission(db, personal, viewer.id) is False, "viewer 不可编辑个人视图")


print("\n[3] P1-12 GET /fields?view_id= 返回 vlf_ 本地字段")
vlf = ViewService.create_local_field(
    db, personal,
    key="vlf_test_field",
    name="测试本地字段",
    field_type="text",
    description="测试",
)
ok(vlf is not None, f"创建本地字段成功: key={vlf.key}")

fields_meta = get_all_fields_meta(db, view_id=personal.id)
vlf_keys = [f["key"] for f in fields_meta if f.get("source") == "view_local"]
ok("vlf_test_field" in vlf_keys, f"GET /fields?view_id 返回 vlf_test_field, vlf_keys={vlf_keys}")

# 不传 view_id 时不应返回 vlf_ 字段
fields_meta_no_view = get_all_fields_meta(db)
vlf_keys2 = [f["key"] for f in fields_meta_no_view if f.get("source") == "view_local"]
ok(not vlf_keys2, f"不传 view_id 时不应返回 vlf_ 字段, 实际: {vlf_keys2}")


print("\n[4] P1-10 + P1-13 PATCH 单字段写入 source_view_id/source_view_name")
patent = Patent(
    title="测试专利A",
    application_number="APP001",
    country="CN",
    database_id=db_obj.id,
)
db.add(patent)
db.flush()

# 模拟前端在视图内编辑共享字段
from app.services.patent_service import PatentService
PatentService.update_patent(
    db, patent,
    patent_in={"abstract": "由视图编辑的摘要"},
    changed_by="owner1",
    source="view_edit",
    source_view_id=personal.id,
    source_view_name=personal.name,
)

history = db.query(PatentHistory).filter(
    PatentHistory.patent_id == patent.id,
    PatentHistory.field_key == "abstract",
).order_by(PatentHistory.id.desc()).first()
ok(history is not None, "历史记录已创建")
ok(history.source == "view_edit", f"source=view_edit, 实际: {history.source}")
ok(history.source_view_id == personal.id, f"source_view_id 正确, 实际: {history.source_view_id}")
ok(history.source_view_name == personal.name, f"source_view_name 正确, 实际: {history.source_view_name}")


print("\n[5] P1-15 导入到视图时未知列自动建为 vlf_ 字段")
# 模拟一列未知列
mapping = ImportService.suggest_mapping(
    columns=["标题", "申请号", "未知列XYZ"],
    db=db,
    view_id=personal.id,
)
ok(mapping.get("标题") == "title", f"标题映射到 title: {mapping.get('标题')}")
ok(mapping.get("申请号") == "application_number", f"申请号映射到 application_number: {mapping.get('申请号')}")
vlf_key = mapping.get("未知列XYZ", "")
ok(vlf_key.startswith("vlf_"), f"未知列应建为 vlf_ 字段, 实际: {vlf_key}")

# 验证 vlf_ 字段已注册到视图
db.refresh(personal)
vlf_names = [lf.name for lf in personal.local_fields]
ok("未知列XYZ" in vlf_names, f"vlf_ 字段已注册到视图, names={vlf_names}")

# 再次 suggest_mapping 应复用已建好的 vlf_
mapping2 = ImportService.suggest_mapping(
    columns=["未知列XYZ"],
    db=db,
    view_id=personal.id,
)
ok(mapping2.get("未知列XYZ") == vlf_key, f"复用现有 vlf_ key: {mapping2.get('未知列XYZ')}")


print("\n[6] P1-13 import / ai / manual 来源标记")
# import source
PatentService.update_patent(
    db, patent,
    patent_in={"assignee": "导入的申请人"},
    changed_by="import",
    source="import",
)
h_imp = db.query(PatentHistory).filter(
    PatentHistory.patent_id == patent.id,
    PatentHistory.field_key == "assignee",
).order_by(PatentHistory.id.desc()).first()
ok(h_imp.source == "import", f"import 历史记录 source=import, 实际: {h_imp.source}")

# manual source
PatentService.update_patent(
    db, patent,
    patent_in={"applicant": "手工录入"},
    changed_by="owner1",
    source="manual",
)
h_man = db.query(PatentHistory).filter(
    PatentHistory.patent_id == patent.id,
    PatentHistory.field_key == "applicant",
).order_by(PatentHistory.id.desc()).first()
ok(h_man.source == "manual", f"manual 历史记录 source=manual, 实际: {h_man.source}")


print("\n[7] P1-11 column_config=[] 语义（show_all_columns）")
ok(ViewService.is_show_all_columns(master) is True, "部门总表 is_show_all_columns=True")
ok(ViewService.is_show_all_columns(personal) is True, "空 column_config 视图 is_show_all_columns=True")

# 设置非空 column_config
ViewService.update_view(db, personal, {"column_config": [
    {"key": "title", "order": 1, "width": 200},
    {"key": "abstract", "order": 2},
]})
ok(ViewService.is_show_all_columns(personal) is False, "非空 column_config 时 is_show_all_columns=False")


print("\n[8] P1-13 HistorySource 枚举完整性")
expected = {"manual", "view_edit", "import", "ai", "promote", "bulk", "api"}
actual = {s.value for s in HistorySource}
ok(actual == expected, f"HistorySource 完整: {actual}")


print("\n" + "=" * 60)
print(f"  测试结果: ✅ {passed} 通过, ❌ {failed} 失败")
print("=" * 60)

if failed > 0:
    sys.exit(1)
