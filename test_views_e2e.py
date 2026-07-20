"""部门总表 + 小表视图 E2E 验证测试。"""
import sys
import os
import json

# 确保使用 backend 目录
sys.path.insert(0, "/workspace/backend")
os.chdir("/workspace/backend")


def banner(title):
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def step(n, msg):
    print(f"\n[Step {n}] {msg}")


def ok(msg):
    print(f"  [OK] {msg}")


def fail(msg):
    print(f"  [FAIL] {msg}")
    raise AssertionError(msg)


def assert_eq(actual, expected, label):
    if actual == expected:
        ok(f"{label}: {actual}")
    else:
        fail(f"{label}: 期望={expected!r}, 实际={actual!r}")


def assert_true(cond, label):
    if cond:
        ok(label)
    else:
        fail(label)


def main():
    banner("初始化数据库")

    # 清理已有 DB
    from app.config import settings
    db_path = settings.DATABASE_PATH
    print(f"数据库路径: {db_path}")
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"已清理旧库: {db_path}")

    from app.database import init_db, SessionLocal
    init_db()
    print("init_db() 完成")

    # 创建默认数据
    from init_data import init_default_data
    init_default_data()

    # 启动 FastAPI TestClient
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)

    # ===== Step 1: 列出数据库（应有 1 个默认数据库）=====
    step(1, "GET /api/databases 列出数据库")
    r = client.get("/api/databases")
    assert_eq(r.status_code, 200, "HTTP 状态")
    dbs = r.json()
    assert_true(len(dbs) >= 1, f"应至少有 1 个数据库，实际 {len(dbs)}")
    default_db = dbs[0]
    assert_true(default_db["is_default"], "首个库应为默认库")
    db_id = default_db["id"]
    ok(f"默认数据库 id={db_id}, name={default_db['name']}")

    # ===== Step 2: GET /databases/{id}/master-view 首次创建部门总表 =====
    step(2, "GET /api/databases/{id}/master-view 首次创建")
    r = client.get(f"/api/databases/{db_id}/master-view")
    assert_eq(r.status_code, 200, "HTTP 状态")
    master_view = r.json()
    assert_true(master_view["is_department_master"], "is_department_master=True")
    assert_eq(master_view["view_type"], "department_master", "view_type")
    master_id = master_view["id"]
    ok(f"部门总表视图 id={master_id}")

    # ===== Step 3: 再次调用应幂等返回同一视图 =====
    step(3, "GET /api/databases/{id}/master-view 幂等")
    r = client.get(f"/api/databases/{db_id}/master-view")
    assert_eq(r.status_code, 200, "HTTP 状态")
    assert_eq(r.json()["id"], master_id, "返回相同 view id（幂等）")

    # ===== Step 4: 创建个人小表视图 =====
    step(4, "POST /api/views 创建个人小表")
    r = client.post("/api/views", json={
        "name": "我的技术布局小表",
        "database_id": db_id,
        "description": "用于技术布局分析的小表",
        "view_type": "personal",
        "filter_config": {},
        "column_config": [
            {"key": "title", "visible": True, "order": 1},
            {"key": "applicant", "visible": True, "order": 2},
        ],
        "sort_config": {"sort_by": "filing_date", "sort_order": "desc"},
    })
    assert_eq(r.status_code, 200, "HTTP 状态")
    personal_view = r.json()
    personal_id = personal_view["id"]
    assert_eq(personal_view["view_type"], "personal", "view_type")
    assert_true(not personal_view["is_department_master"], "非部门总表")
    ok(f"个人小表 id={personal_id}")

    # ===== Step 5: 列出视图（应有 2 个：部门总表 + 个人）=====
    step(5, "GET /api/views 列出视图")
    r = client.get(f"/api/views?database_id={db_id}")
    assert_eq(r.status_code, 200, "HTTP 状态")
    views = r.json()
    assert_eq(len(views), 2, f"应有 2 个视图，实际 {len(views)}")
    # 部门总表应排在最前
    assert_eq(views[0]["id"], master_id, "部门总表应排在首位")

    # ===== Step 6: 创建一件专利 =====
    step(6, "POST /api/patents 创建专利")
    r = client.post("/api/patents", json={
        "application_number": "CN20231012345",
        "publication_number": "CN116000000A",
        "title": "一种基于大语言模型的专利分析系统",
        "abstract": "本发明涉及一种基于大语言模型的专利分析系统...",
        "applicant": "示例科技公司",
        "inventor": "张三;李四",
        "country": "CN",
        "patent_type": "invention",
        "filing_date": "2023-01-15",
        "legal_status": "published",
        "database_id": db_id,
    })
    assert_eq(r.status_code, 200, f"HTTP 状态 (body={r.text})")
    patent = r.json()
    patent_id = patent["id"]
    ok(f"专利 id={patent_id}")

    # ===== Step 7: 列出部门总表中的专利（应有 1 件）=====
    step(7, "GET /api/views/{master}/patents 部门总表专利列表")
    r = client.get(f"/api/views/{master_id}/patents")
    assert_eq(r.status_code, 200, "HTTP 状态")
    data = r.json()
    assert_eq(data["total"], 1, f"部门总表应有 1 件专利，实际 {data['total']}")
    ok(f"部门总表中有 {data['total']} 件专利")

    # ===== Step 8: 列出个人小表中的专利（应也有 1 件，共享大表数据）=====
    step(8, "GET /api/views/{personal}/patents 个人小表专利列表")
    r = client.get(f"/api/views/{personal_id}/patents")
    assert_eq(r.status_code, 200, "HTTP 状态")
    data = r.json()
    assert_eq(data["total"], 1, f"个人小表应共享大表数据有 1 件，实际 {data['total']}")
    # 应包含 view_local_fields 占位
    assert_true("view_local_fields" in data["items"][0], "返回结构包含 view_local_fields")

    # ===== Step 9: 在个人小表中创建一个本地字段 =====
    step(9, "POST /api/views/{personal}/local-fields 创建本地字段")
    r = client.post(f"/api/views/{personal_id}/local-fields", json={
        "key": "tech_layout_note",
        "name": "技术布局备注",
        "field_type": "text",
        "description": "本小表专用：技术布局分析备注",
        "is_required": False,
    })
    assert_eq(r.status_code, 200, "HTTP 状态")
    local_field = r.json()
    local_field_id = local_field["id"]
    local_field_key = local_field["key"]
    assert_true(local_field_key.startswith("vlf_"), f"key 应有 vlf_ 前缀，实际 {local_field_key}")
    ok(f"本地字段 id={local_field_id}, key={local_field_key}")

    # ===== Step 10: 设置本地字段值（不影响大表）=====
    step(10, "PUT /api/views/{personal}/local-fields/{key}/values/{pid} 设置本地值")
    r = client.put(
        f"/api/views/{personal_id}/local-fields/{local_field_key}/values/{patent_id}",
        json={"value": "本专利属于核心布局点，需要重点关注", "changed_by": "test_user"}
    )
    assert_eq(r.status_code, 200, "HTTP 状态")
    assert_eq(r.json()["value"], "本专利属于核心布局点，需要重点关注", "返回值")

    # ===== Step 11: 获取专利在视图中的字段（应含本地字段值）=====
    step(11, "GET /api/views/{personal}/patents 验证本地字段值")
    r = client.get(f"/api/views/{personal_id}/patents")
    item = r.json()["items"][0]
    vlf = item["view_local_fields"]
    assert_true(local_field_key in vlf, f"返回应包含本地字段 key={local_field_key}")
    assert_eq(vlf[local_field_key], "本专利属于核心布局点，需要重点关注", "本地字段值")

    # 验证大表的 custom_fields 不应被本地字段污染
    r2 = client.get(f"/api/patents/{patent_id}")
    patent_full = r2.json()
    assert_true(
        local_field_key not in (patent_full.get("custom_fields") or {}),
        "大表 custom_fields 不应包含视图本地字段"
    )
    ok("大表未被本地字段污染")

    # ===== Step 12: 在视图中编辑共享字段（应写入大表+记录来源视图）=====
    step(12, "PATCH /api/views/{personal}/patents/{pid}/field/title 编辑共享字段")
    new_title = "一种基于大语言模型的专利分析系统（修订版）"
    r = client.patch(
        f"/api/views/{personal_id}/patents/{patent_id}/field/title",
        json={"value": new_title, "changed_by": "test_user"}
    )
    assert_eq(r.status_code, 200, "HTTP 状态")
    assert_eq(r.json()["source_view_id"], personal_id, "响应应返回 source_view_id")
    assert_eq(r.json()["source_view_name"], "我的技术布局小表", "source_view_name")

    # 验证大表的 title 已更新
    r = client.get(f"/api/patents/{patent_id}")
    assert_eq(r.json()["title"], new_title, "大表 title 应已更新")

    # ===== Step 13: 获取专利历史（应包含 source_view_id/source_view_name）=====
    step(13, "GET /api/patents/{pid}/history 验证历史来源")
    r = client.get(f"/api/patents/{patent_id}/history")
    assert_eq(r.status_code, 200, "HTTP 状态")
    history = r.json()
    # 找出 title 的修改记录
    title_changes = [h for h in history if h.get("field_key") == "title"]
    assert_true(len(title_changes) > 0, "应有 title 修改历史")
    last_title_change = title_changes[-1] if isinstance(title_changes[-1], dict) else title_changes[-1]
    # 列表可能是 {items: [...]} 或直接是 list
    if isinstance(history, dict) and "items" in history:
        title_changes = [h for h in history["items"] if h.get("field_key") == "title"]
        last_title_change = title_changes[-1]
    assert_eq(last_title_change.get("source_view_id"), personal_id, "history.source_view_id")
    assert_eq(last_title_change.get("source_view_name"), "我的技术布局小表", "history.source_view_name")
    ok(f"历史记录已正确记录来源视图: {last_title_change['source_view_name']}")

    # ===== Step 14: 字段来源追溯 =====
    step(14, "GET /api/patents/{pid}/field-sources 字段来源追溯")
    r = client.get(f"/api/patents/{patent_id}/field-sources")
    assert_eq(r.status_code, 200, "HTTP 状态")
    sources = r.json()
    title_src = next((s for s in sources if s["field_key"] == "title"), None)
    assert_true(title_src is not None, "应能找到 title 字段的来源记录")
    assert_eq(title_src["last_source_view_id"], personal_id, "title.last_source_view_id")
    assert_eq(title_src["last_source_view_name"], "我的技术布局小表", "title.last_source_view_name")
    ok(f"字段来源追溯成功: title ← {title_src['last_source_view_name']}")

    # ===== Step 15: 将本地字段提升为全局 CustomField =====
    step(15, "POST /api/views/{personal}/local-fields/{fid}/promote 字段提升")
    r = client.post(
        f"/api/views/{personal_id}/local-fields/{local_field_id}/promote",
        json={"global_name": "技术布局备注（全局）", "global_group": "从小表提升"}
    )
    assert_eq(r.status_code, 200, f"HTTP 状态 (body={r.text})")
    promote_result = r.json()
    global_key = promote_result["global_field_key"]
    assert_true(global_key.startswith("cf_"), f"全局 key 应有 cf_ 前缀，实际 {global_key}")
    ok(f"提升成功: 全局 key={global_key}, id={promote_result['global_field_id']}")

    # 验证：
    # 1) CustomField 表中应有新字段
    # 2) 视图本地字段标记 is_promoted=True
    # 3) 专利 custom_fields 中应有该 key 且值 = 原本地字段值
    # 4) PatentHistory 中应有 source='promote' 的记录
    r = client.get(f"/api/views/{personal_id}/local-fields")
    lf_now = next(f for f in r.json() if f["id"] == local_field_id)
    assert_true(lf_now["is_promoted"], "本地字段应标记 is_promoted=True")
    assert_eq(lf_now["promoted_field_key"], global_key, "promoted_field_key")

    r = client.get(f"/api/patents/{patent_id}")
    custom_fields = r.json().get("custom_fields") or {}
    assert_true(global_key in custom_fields, f"专利 custom_fields 应包含提升后的全局 key={global_key}")
    assert_eq(
        custom_fields[global_key],
        "本专利属于核心布局点，需要重点关注",
        "全局字段值应等于原本地字段值"
    )

    r = client.get(f"/api/patents/{patent_id}/history")
    hist_items = r.json()
    if isinstance(hist_items, dict) and "items" in hist_items:
        hist_items = hist_items["items"]
    promote_histories = [h for h in hist_items if h.get("source") == "promote"]
    assert_true(len(promote_histories) > 0, "应有 source='promote' 的历史记录")
    ph = promote_histories[-1]
    assert_eq(ph["source_view_id"], personal_id, "promote history.source_view_id")
    assert_eq(ph["source_view_name"], "我的技术布局小表", "promote history.source_view_name")
    ok("字段提升：值迁移 + 历史记录 + 视图标记全部正确")

    # ===== Step 16: 归档个人视图（不允许归档部门总表）=====
    step(16, "POST /api/views/{personal}/archive 归档个人视图")
    r = client.post(f"/api/views/{personal_id}/archive")
    assert_eq(r.status_code, 200, "HTTP 状态")
    archived = r.json()
    assert_true(archived["is_archived"], "归档后 is_archived=True")

    # 部门总表不应允许归档
    r = client.post(f"/api/views/{master_id}/archive")
    assert_eq(r.status_code, 400, "部门总表归档应返回 400")
    ok("部门总表拒绝归档校验通过")

    # 列出视图默认不显示已归档
    r = client.get(f"/api/views?database_id={db_id}")
    active_views = r.json()
    assert_true(
        all(not v["is_archived"] for v in active_views),
        "默认查询不应包含已归档视图"
    )
    # include_archived=True 才能看到
    r = client.get(f"/api/views?database_id={db_id}&include_archived=true")
    all_views = r.json()
    assert_eq(len(all_views), 2, "include_archived=true 时应看到全部 2 个视图")
    ok("归档/查询过滤正常")

    banner("✅ 全部 16 步 E2E 测试通过！")
    print("\n功能点覆盖：")
    print("  - 部门总表视图创建/幂等")
    print("  - 个人小表创建")
    print("  - 视图共享大表数据（不复制）")
    print("  - 视图本地字段（不污染大表）")
    print("  - 视图内编辑共享字段（写入大表+记录来源视图）")
    print("  - 历史记录含 source_view_id/source_view_name")
    print("  - 字段来源追溯")
    print("  - 本地字段提升为全局 CustomField（含值迁移+历史）")
    print("  - 视图归档/部门总表保护")


if __name__ == "__main__":
    main()
