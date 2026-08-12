"""Reproduce the reported issues:
1. Role creation 400 error
2. Database switching / pagination data disappearing
3. Large import 400 error
"""
import sys
import os
import io

sys.path.insert(0, "/workspace/backend")
os.chdir("/workspace/backend")

# Use a fresh temp database to avoid messing with dev data
import tempfile
tmp_dir = tempfile.mkdtemp(prefix="patwiki_repro_")
os.environ.setdefault("DATA_DIR", tmp_dir)

# Re-import settings after env override (settings already loaded above, must override manually)
from app import config as _config
_config.settings.DATA_DIR = _config.Path(tmp_dir)
_config.settings.DATABASE_PATH = _config.Path(tmp_dir) / "patwiki.db"
_config.settings.DATABASE_URL = f"sqlite:///{_config.settings.DATABASE_PATH.as_posix()}"
for d in [_config.settings.VECTORS_DIR, _config.settings.FILES_DIR, _config.settings.BACKUPS_DIR, _config.settings.CACHE_DIR, _config.settings.LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

from app.database import init_db, SessionLocal
init_db()

from init_data import init_default_data
init_default_data()

from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)


def banner(title):
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def step(n, msg):
    print(f"\n[Step {n}] {msg}")


def show_resp(r, label):
    body_preview = r.text[:300] if r.text else ""
    print(f"  {label}: status={r.status_code} body={body_preview}")


banner("Test 1: 列出库 + 创建用户（验证 400 错误根因）")

step(1, "GET /api/databases")
r = client.get("/api/databases")
show_resp(r, "list databases")
assert r.status_code == 200, "list databases failed"
dbs = r.json()
print(f"  数据库列表: {[(d['id'], d['name'], d.get('patent_count')) for d in dbs]}")
default_db = dbs[0]
db1_id = default_db["id"]

step(2, "POST /api/users 创建用户（角色）—— 期望 200，曾经 400/500")
r = client.post("/api/users", json={
    "username": "zhangsan",
    "display_name": "张三",
})
show_resp(r, "create user")
if r.status_code != 200:
    print(f"  !!! 复现成功：创建用户返回非 200 -> {r.status_code}")
else:
    print(f"  创建用户成功：{r.json()}")

step(3, "GET /api/users 列出用户")
r = client.get("/api/users")
show_resp(r, "list users")

banner("Test 2: 创建第二个库 + 切换库 + 分页")

step(4, "POST /api/databases 创建第二个库")
r = client.post("/api/databases", json={"name": "测试库B"})
show_resp(r, "create database B")
assert r.status_code == 200, "create database B failed"
db2 = r.json()
db2_id = db2["id"]
print(f"  db2 id={db2_id}")

step(5, "为 db2 创建 master-view")
r = client.get(f"/api/databases/{db2_id}/master-view")
show_resp(r, "master-view db2")
assert r.status_code == 200
db2_view = r.json()
db2_view_id = db2_view["id"]

step(6, "在 db1 插入若干专利（让分页有意义）")
import uuid as _uuid
for i in range(75):
    payload = {
        "title": f"测试专利 db1 #{i+1}",
        "application_number": f"CN20240000{i+1:04d}",
        "publication_number": f"CN2024{i+1:04d}A",
        "database_id": db1_id,
        "applicant": f"申请人{i+1}",
        "filing_date": "2024-01-15",
    }
    rr = client.post("/api/patents", json=payload)
    if rr.status_code != 200:
        print(f"  insert #{i+1} failed: {rr.status_code} {rr.text[:200]}")
        break
print(f"  db1 插入完成")

step(7, "在 db2 插入若干专利")
for i in range(35):
    payload = {
        "title": f"测试专利 db2 #{i+1}",
        "application_number": f"CN_DB2_{i+1:04d}",
        "publication_number": f"CN_DB2_{i+1:04d}A",
        "database_id": db2_id,
        "applicant": f"申请人B{i+1}",
        "filing_date": "2024-02-15",
    }
    rr = client.post("/api/patents", json=payload)
    if rr.status_code != 200:
        print(f"  insert #{i+1} failed: {rr.status_code} {rr.text[:200]}")
        break
print(f"  db2 插入完成")

step(8, "刷新两个库的专利计数")
for did in [db1_id, db2_id]:
    rr = client.post(f"/api/databases/{did}/refresh-count")
    print(f"  refresh db{did}: {rr.status_code} {rr.json()}")

step(9, "GET /api/databases 再列一次查看 patent_count")
r = client.get("/api/databases")
print(f"  databases patent_count: {[(d['id'], d.get('patent_count')) for d in r.json()]}")

step(10, "切换到 db1：通过 master-view listPatents page=1")
r = client.get(f"/api/views/{client.get(f'/api/databases/{db1_id}/master-view').json()['id']}/patents",
               params={"page": 1, "page_size": 50})
show_resp(r, "db1 view patents p1")
if r.status_code == 200:
    j = r.json()
    print(f"  db1 page1: total={j.get('total')}, items={len(j.get('items') or [])}")

step(11, "切换到 db2：通过 db2 master-view listPatents page=1")
r2 = client.get(f"/api/views/{db2_view_id}/patents", params={"page": 1, "page_size": 50})
show_resp(r2, "db2 view patents p1")
if r2.status_code == 200:
    j = r2.json()
    print(f"  db2 page1: total={j.get('total')}, items={len(j.get('items') or [])}")

step(12, "在 db1 跳到 page=2")
r = client.get(f"/api/views/{client.get(f'/api/databases/{db1_id}/master-view').json()['id']}/patents",
               params={"page": 2, "page_size": 50})
show_resp(r, "db1 view patents p2")
if r.status_code == 200:
    j = r.json()
    print(f"  db1 page2: total={j.get('total')}, items={len(j.get('items') or [])}")

step(13, "直查 /api/patents?database_id=db1&page=2")
r = client.get("/api/patents", params={"database_id": db1_id, "page": 2, "page_size": 50})
show_resp(r, "patents db1 p2 (direct)")
if r.status_code == 200:
    j = r.json()
    print(f"  direct db1 page2: total={j.get('total')}, items={len(j.get('items') or [])}")

step(14, "直查 /api/patents?database_id=db2&page=1")
r = client.get("/api/patents", params={"database_id": db2_id, "page": 1, "page_size": 50})
show_resp(r, "patents db2 p1 (direct)")
if r.status_code == 200:
    j = r.json()
    print(f"  direct db2 page1: total={j.get('total')}, items={len(j.get('items') or [])}")

banner("Test 3: 大量导入 — 生成 5000 行 Excel 并预览 + 确认")
import pandas as pd

rows = []
for i in range(5000):
    rows.append({
        "申请号": f"CN_IMP_{i+1:05d}",
        "公开号": f"CN_IMP_{i+1:05d}A",
        "标题": f"导入测试专利 {i+1}",
        "申请人": f"测试申请人 {i % 50}",
        "发明人": f"发明人 {i % 100}",
        "申请日": "2024-03-15",
    })
df = pd.DataFrame(rows)
buf = io.BytesIO()
df.to_excel(buf, index=False)
buf.seek(0)

step(15, "POST /api/import/preview 上传 5000 行 Excel")
files = {"file": ("big.xlsx", buf.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
r = client.post("/api/import/preview", files=files)
show_resp(r, "preview big import")
if r.status_code != 200:
    print(f"  !!! 大文件预览失败")
else:
    j = r.json()
    print(f"  preview: total_rows={j.get('total_rows')}, columns={j.get('detected_columns')}")
    import_id = j["import_id"]

    step(16, "POST /api/import/confirm 确认导入 5000 行（指定 database_id=db2）")
    mapping = [
        {"source_column": "申请号", "target_field": "application_number"},
        {"source_column": "公开号", "target_field": "publication_number"},
        {"source_column": "标题", "target_field": "title"},
        {"source_column": "申请人", "target_field": "applicant"},
        {"source_column": "发明人", "target_field": "inventor"},
        {"source_column": "申请日", "target_field": "filing_date"},
    ]
    r = client.post("/api/import/confirm", json={
        "import_id": import_id,
        "field_mappings": mapping,
        "database_id": db2_id,
        "update_on_duplicate": True,
    })
    show_resp(r, "confirm big import")
    if r.status_code == 200:
        j = r.json()
        print(f"  confirm result: {j}")
    else:
        print(f"  !!! 大文件确认失败")

banner("Done")
