# HimmPat MCP 专利更新调用与验证指引

## 更新链路

PatWiki 的“外部更新”只覆盖已存在且已唯一匹配的本地专利，不创建新专利。每条记录按下列链路执行：

| 步骤 | 服务 / 工具 | 请求 | 返回用途 | PatWiki 字段 |
| --- | --- | --- | --- | --- |
| 1 | `product_patent_discovery` / `search_patent_by_patent_numbers` | `{"matchingMethod":["PN"],"patentList":["CN1719785A"]}` | 公开号对应的 HimmPat 内部 ID | 仅用于下一步，不写库 |
| 2 | `product_patent_dossier` / `get_patent_publication_by_patent_ids` | `{"ids":["<步骤 1 的内部 ID>"]}` | 著录项主记录 | `publication_number`、`application_number`、`title`、`abstract`、`applicant`、`assignee`、`inventor`、`filing_date`、`publication_date`、`country`、`ipc_all` |
| 3，可选 | `product_legal_ownership_risk` / `get_patent_legal_status_by_patent_ids` | `{"ids":["<内部 ID>"]}` | `state`、`stc`、`grd` | `legal_status`、`grant_date` |
| 4 | PatWiki 更新预览 | 已选择的字段列表 | 对比本地值与候选值 | 仅勾选发生变化的字段后确认写入 |

完整 MCP 服务地址统一为 `https://www.himmpat.com/api/service/himmuc_api/mcp/{service_name}`。配置页接受主站地址，也兼容历史保存的完整 dossier 地址；运行时会还原主机并分别访问上述服务，不能将三个工具都请求到 `product_patent_dossier`。

## 可选字段边界

更新前的字段列表由适配器已实现并已用测试返回验证的映射生成。法律状态开关未启用时，不显示也不接受 `legal_status`、`grant_date`；权利要求、代理人、优先权等字段虽然可能存在于其他 MCP 工具返回中，但当前更新链路没有调用其工具，因此不能选择。后端会再次校验，不能通过 API 绕过界面提交。

## 测试证据与完整路径

| 校验内容 | fixture / 原始结果完整路径 | 已验证结论 |
| --- | --- | --- |
| 公开号到内部 ID | `C:\Users\sdh777\Documents\ChatGPT\MCP测试\test-data\public\patent-number.json`；`C:\Users\sdh777\Documents\ChatGPT\MCP测试\results\2026-09-07\T-003\search_patent_by_patent_numbers.json` | `matchingMethod: PN` 和 `patentList` 可以返回供后续调用的内部 ID。 |
| 内部 ID 到著录项 | `C:\Users\sdh777\Documents\ChatGPT\MCP测试\test-data\public\patent-id.json`；`C:\Users\sdh777\Documents\ChatGPT\MCP测试\results\2026-09-07\T-004\get_patent_publication_by_patent_ids.json` | `applicationReferenceModel`、`publicationReferenceModel`、`inventionTitleModel`、`abstractModel`、`partiesModel` 可解析为更新字段。 |
| 批量著录项 | `C:\Users\sdh777\Documents\ChatGPT\MCP测试\test-data\user-provided\home-appliance-dossier.fixture.json`；`C:\Users\sdh777\Documents\ChatGPT\MCP测试\results\2026-09-07\T-006-home-appliance-dossier\get_patent_publication_by_patent_ids.json` | `ids` 支持批量；schema 上限为 100。PatWiki 当前逐条预览，避免跨记录匹配错误。 |
| 批量法律状态 | `C:\Users\sdh777\Documents\ChatGPT\MCP测试\test-data\user-provided\home-appliance-legal-status.fixture.json`；`C:\Users\sdh777\Documents\ChatGPT\MCP测试\results\2026-09-07\T-006-07\get_patent_legal_status_by_patent_ids.json` | `state`/`stc` 映射 `legal_status`，`grd` 映射 `grant_date`。 |
| 参数与服务事实来源 | `C:\Users\sdh777\Documents\ChatGPT\MCP测试\schemas\product_patent_discovery.json`；`C:\Users\sdh777\Documents\ChatGPT\MCP测试\schemas\product_patent_dossier.json`；`C:\Users\sdh777\Documents\ChatGPT\MCP测试\schemas\product_legal_ownership_risk.json` | 参数名、必填项和上限必须以 schema 为准，不凭工具名猜测。 |

原始响应是 MCP `result.content[type=text].text` 中的业务 JSON。适配器先验证 JSON-RPC 成功、再解析业务 `code == 200` 和 `data`，最后生成候选字段。任一层失败都会在预览中保留错误且不写入本地专利。

## 回归命令

```powershell
Set-Location C:\Users\sdh777\Documents\ChatGPT\patwiki\backend
python -m pytest tests/test_mcp_transport.py tests/test_himmpat_mcp_adapter.py tests/test_sync_updates.py -q
```

实际供应商回归应使用测试项目的安全执行器，调用会产生供应商费用：

```powershell
Set-Location C:\Users\sdh777\Documents\ChatGPT\MCP测试
.\scripts\himmpat_mcp_test.ps1 -Command fixture -InputFile .\test-data\public\patent-number.json
.\scripts\himmpat_mcp_test.ps1 -Command fixture -InputFile .\test-data\public\patent-id.json
```
