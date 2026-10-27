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
    database = {"id": 1, "name": "Regression library", "is_default": True, "patent_count": 123, "browsing_config": {"application_mode": "merged", "preferred_version": "grant", "family_representative": False, "country_order": ["CN", "US"], "representative_date": "latest"}}

    def respond(route):
        url = urlparse(route.request.url)
        if not url.path.startswith('/api/'):
            route.continue_()
            return
        path = url.path.removeprefix("/api")
        data = []
        if path == "/databases":
            data = [database]
        elif path == "/databases/1/browsing-config":
            database["browsing_config"] = route.request.post_data_json
            data = database
        elif path == "/fields":
            data = [{"key": "title", "label": "Title", "field_type": "text", "is_system": True, "name": "标题", "visible": True}, {"key": "application_number", "name": "申请号", "field_type": "text", "is_system": True, "visible": True}]
        elif path.endswith("/views"):
            data = [{"id": 1, "database_id": 1, "name": "Master", "layout_type": "table", "config": {}, "is_department_master": True}]
        elif path.endswith("/patents"):
            params = parse_qs(url.query)
            page = int(params.get("page", [1])[0])
            size = int(params.get("page_size", [50])[0])
            requests.append((page, size, params))
            config = database["browsing_config"]
            total = 41 if config["family_representative"] and params.get("group_by_family") == ["true"] else 246 if config["application_mode"] == "separate" else 123
            data = {"items": [{"id": i, "title": f"Patent {i}", "application_number": f"CN{i}", "custom_fields": {}, "tags": [], "projects": []} for i in range((page - 1) * size + 1, min(page * size, total) + 1)], "total": total, "page": page, "page_size": size}
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
        context.grant_permissions(['clipboard-read', 'clipboard-write'])
        page.goto(f"{base_url}/db/1/patents")
        cells=page.locator('td[data-range-row]')
        expect(cells.first).to_be_visible()
        first=cells.nth(0).bounding_box()
        second=cells.nth(3).bounding_box()
        page.mouse.move(first['x']+15,first['y']+15)
        page.mouse.down()
        page.mouse.move(second['x']+15,second['y']+15,steps=10)
        page.mouse.up()
        expect(page.locator('.cell-range-selected')).to_have_count(4)
        page.keyboard.press('Control+c')
        clip=page.evaluate('navigator.clipboard.readText()')
        assert clip=='Patent 1\tCN1\r\nPatent 2\tCN2',repr(clip)
        page.get_by_role('button',name='复制选区',exact=True).click()
        assert page.evaluate('navigator.clipboard.readText()')==clip
        page.screenshot(path=str(output/'cell-copy.png'))
        cells.nth(0).click(button='right')
        page.get_by_text('复制选中单元格',exact=True).click()
        assert page.evaluate('navigator.clipboard.readText()')==clip
        page.keyboard.press('Escape')
        expect(page.locator('.cell-range-selected')).to_have_count(0)
        for path in ('/db/1/ai-center', '/db/1/sharing', '/management', '/attachments', '/agent-analysis'):
            page.goto(base_url+path)
            page.wait_for_timeout(600)
            page.screenshot(path=str(output/(path.split('/')[-1]+'.png')),full_page=True)
            assert page.locator('.management-brandline, .ai-center-eyebrow, .project-wiki-eyebrow').count()==0
        page.set_viewport_size({'width':390,'height':844})
        for path in ('/db/1/ai-center','/management','/attachments','/agent-analysis','/db/1/sharing'):
            page.goto(base_url+path)
            page.wait_for_timeout(500)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),path
            page.screenshot(path=str(output/(path.split('/')[-1]+'-mobile.png')),full_page=True)
        assert not errors,errors
        browser.close()
    print('PASS: drag range, clipboard TSV, explicit copy, Escape, workspace page smoke checks')


if __name__ == "__main__":
    run()
