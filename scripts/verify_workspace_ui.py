"""Focused browser regression checks with isolated API fixtures (no user data)."""
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright, expect


def run():
    base_url = os.environ.get("PATWIKI_UI_URL", "http://127.0.0.1:5174")
    output = Path(os.environ.get('TEMP', '.')) / "patwiki-ui-checks"
    output.mkdir(exist_ok=True)
    errors = []
    requests = []

    def respond(route):
        url = urlparse(route.request.url)
        if not url.path.startswith('/api/'):
            route.continue_()
            return
        path = url.path.removeprefix("/api")
        data = []
        if path == "/databases":
            data = [{"id": 1, "name": "Regression library", "is_default": True, "patent_count": 123}]
        elif path == "/fields":
            data = [{"key": "title", "label": "Title", "field_type": "text", "is_system": True}]
        elif path.endswith("/views"):
            data = [{"id": 1, "database_id": 1, "name": "Master", "layout_type": "table", "config": {}, "is_department_master": True}]
        elif path.endswith("/patents"):
            params = parse_qs(url.query)
            page = int(params.get("page", [1])[0])
            size = int(params.get("page_size", [50])[0])
            requests.append((page, size, params))
            data = {"items": [{"id": i, "title": f"Patent {i}", "application_number": f"CN{i}", "custom_fields": {}, "tags": [], "projects": []} for i in range((page - 1) * size + 1, min(page * size, 123) + 1)], "total": 123, "page": page, "page_size": size}
        elif path.startswith("/semantic-search"):
            data = {"items": []}
            if path.endswith("/providers"):
                data = {"items": [{"id": 7, "name": "Embedding fixture", "provider_kind": "embedding", "enabled": True, "endpoint": "https://example.com/v1", "credential_ref": "env://TEST_KEY", "config_json": {"model": "fixture-model"}}]}
            if path.endswith("/profiles"):
                data = {"items": [{"id": 8, "name": "Patent search", "is_default": True, "enabled": True, "embedding_provider_id": 7, "embedding_model": "fixture-model", "embedding_dimensions": 1536, "vector_backend": "json_local", "rerank_enabled": False, "quality_gate_enabled": False, "quality_thresholds": {}}]}
            if path.endswith("/status"):
                data = {"configured_profiles": 1, "active_indexes": 0, "pending_jobs": 0, "coverage_rate": 0, "document_indexed": 0, "document_pending": 123, "job_failed": 0, "document_failed": 0, "job_dead_letter": 0, "outbox_dead_letter": 0, "outbox_retry_wait": 0, "sparse_available": True}
        elif path == "/settings":
            data = {"llm": {"llm_provider": "deepseek", "llm_model": "deepseek-v4-flash"}, "ai_enabled": False}
        elif path.startswith("/collaboration-sync"):
            data = {"configured": False, "setup_token_path": "fixture", "items": []}
        elif path.endswith("/rebuild"):
            data = {"family_count": 0, "grouped_patent_count": 0}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.route("**/api/**", respond)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{base_url}/db/1/ai-center")
        page.get_by_role("button", name="Embedding / Rerank 模型配置", exact=True).click()
        expect(page.locator(".semantic-model-card")).to_have_count(2)
        page.screenshot(path=str(output / "semantic-models-desktop.png"), full_page=True)
        page.get_by_role("button", name="工作台概览", exact=True).click()
        expect(page.get_by_role("button", name="开始向量化", exact=True)).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("document.querySelector('.sidebar').getBoundingClientRect().right <= 1")
        page.screenshot(path=str(output / "semantic-mobile.png"), full_page=True, animations="disabled")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "mobile page overflows"
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("button", name="自定义字段与AI抽取", exact=True).click()
        page.get_by_role("button", name="AI抽取任务记录", exact=True).click()
        expect(page.get_by_role("heading", name="AI抽取任务记录", exact=True)).to_be_visible()
        for mode in ("pagination", "continuous"):
            page.goto(f"{base_url}/db/1/patents")
            page.evaluate("mode => {localStorage.setItem('patwiki_table_view_mode', mode); sessionStorage.clear()}", mode)
            page.reload()
            expect(page.get_by_role("button", name="滚动到库底部", exact=True)).to_be_enabled()
            page.get_by_role("button", name="滚动到库底部", exact=True).click()
            page.wait_for_function("location.search.includes('page=3')")
            expect(page.get_by_role("button", name="滚动到库底部", exact=True)).to_be_disabled()
            assert requests[-1][0] == 3, requests[-1]
            page.get_by_role("button", name="滚动到库顶部", exact=True).click()
            page.wait_for_function("!location.search.includes('page=3')")
            expect(page.get_by_role("button", name="滚动到库顶部", exact=True)).to_be_disabled()
        if page.get_by_role("button", name="同族聚拢已关闭", exact=False).count():
            page.get_by_role("button", name="同族聚拢已关闭", exact=False).click()
        page.get_by_role("button", name="同族条件", exact=False).click()
        page.get_by_role("textbox", name="按族内国家筛选", exact=True).fill("CN")
        page.get_by_role("combobox", name="同族排序指标", exact=True).select_option("count")
        page.get_by_role("combobox", name="同族排序方向", exact=True).select_option("desc")
        page.wait_for_timeout(300)
        assert requests[-1][2].get('family_country') == ['CN'], requests[-1]
        assert requests[-1][2].get('family_sort_by') == ['count'], requests[-1]
        page.screenshot(path=str(output / "family-filter-desktop.png"), full_page=True)
        page.goto(f"{base_url}/db/1/sharing")
        expect(page.get_by_text("选择配置文件", exact=True)).to_be_visible()
        with page.expect_download() as download:
            page.get_by_role("link", name="格式样例", exact=True).click()
        assert download.value.suggested_filename == "patwiki-employee-config.example.json"
        page.screenshot(path=str(output / "member-config-desktop.png"), full_page=True)
        assert not errors, errors
        browser.close()
    print("PASS: model configuration, responsive layout, extraction tabs, global first/last jumps in both modes, sample download")


if __name__ == "__main__":
    run()
