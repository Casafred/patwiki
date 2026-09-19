# MCP 统一适配与 HimmPat 集成开发规范

## 1. 目标

PatWiki 的外部专利数据接入统一经过连接器和同步流水线。MCP 供应商不能直接写入 `Patent`，也不能绕过身份解析、外部快照、事实观察、审查策略和法律事件流水线。

当前已实现：

- 通用 JSON-RPC MCP 传输层：`backend/app/integrations/mcp_transport.py`
- HimmPat 业务适配器：`backend/app/integrations/himmpat.py`
- MCP 连接器注册：`provider_type=himmpat_mcp`、`transport=mcp`
- MCP 工具目录发现和脱敏快照：`POST /api/sync/connectors/{id}/discover`
- HimmPat 检索、按号码映射、著录项读取、可选法律状态补全
- 标准化 MCP 只读连接器：供应商已能返回 PatWiki 标准记录时可直接复用

## 2. 分层规则

```text
MCP 管理 API/UI
        |
McpTransport（JSON-RPC、握手、Session、重试、脱敏）
        |
供应商 Adapter（HimmPat 字段、业务 code、工具参数）
        |
PatentConnector 标准契约
        |
SyncService -> ExternalSnapshot -> SyncRecord -> Observation/LegalEvent
```

### 2.1 通用传输层

`McpTransport` 只处理协议，不允许出现 HimmPat 字段名、专利状态映射或供应商工具名。它必须负责：

1. `initialize` 和 `Mcp-Session-Id` 生命周期。
2. `tools/list` 和 `tools/call`。
3. HTTP、JSON-RPC、超时和可重试错误的统一转换。
4. 认证头注入和错误信息脱敏。
5. 服务 endpoint 的同源校验，禁止重定向到其他主机。

### 2.2 供应商适配器

每个供应商单独实现适配器。适配器必须：

- 输出 `ProviderPatentRecord`、`ProviderIdentifier` 和 `ProviderLegalEvent`。
- 将供应商业务返回包解包为标准结果。
- 保留脱敏后的 `raw_payload`，便于审计和重放。
- 对供应商内部 ID 生成稳定的外部记录 ID。
- 不导入 SQLAlchemy，不直接写业务表。
- 不把供应商的任意工具暴露为 PatWiki 任意执行接口。

HimmPat 特殊约束：一个业务服务对应一个 MCP endpoint；工具结果位于 `result.content[].text`，text 还要再次解析为 `{code,data,message}`。`code != 200` 必须转换为明确的 `ConnectorError`。

## 3. 凭证与安全

SQLite 只能保存 `env://VARIABLE` 或 `keyring://service/account` 引用，不能保存 token、API key、Authorization header 或 cookie。日志、快照、工具目录和异常消息不得包含凭证明文。

健康检查默认只检查 discovery 服务；遍历全部服务的工具发现需要用户手动点击。业务工具调用可能计费，测试必须使用离线 HTTP fixtures，禁止在单元测试中调用真实 HimmPat 业务接口。

## 4. HimmPat 接入约定

默认服务映射：

| 用途 | 服务 |
| --- | --- |
| 检索和号码映射 | `product_patent_discovery` |
| 著录项 | `product_patent_dossier` |
| 法律状态 | `product_legal_ownership_risk` |
| 变化监控 | `product_patent_monitoring` |

默认检索：申请人会转为 `申请人/pa`；也可通过 `expression` 传入完整 HimmPat 检索式。分页游标在 PatWiki 内部使用页码字符串，HimmPat 参数使用 `page` 和 `size`。

法律状态补全通过 `enrich_legal_status` 或 `enrich_legal_on_fetch` 显式启用，避免普通同步隐式增加调用成本。HimmPat 没有稳定法律事件 ID 时，适配器必须基于内部 ID、状态数据生成确定性 ID。

## 5. 新供应商接入流程

1. 新建 `backend/app/integrations/<provider>.py`，只依赖标准 connector contract 和 `McpTransport`。
2. 在 `registry.py` 增加 provider type 分支。
3. 提供离线 fixtures，覆盖 initialize/session、工具错误、业务错误、分页、字段映射和脱敏。
4. 不修改 `SyncService` 以适配供应商字段。
5. 只通过连接器 API 创建和检查配置；不在 `init_data.py` 中自动创建真实供应商连接器。
6. 需要新增能力时，先扩展 provider-neutral contract，再在适配器实现。
7. 更新本文件和迁移说明，运行完整后端和前端验证。

如果供应商已经返回标准的 `external_record_id`、`identifiers`、`fields` 结构，可以使用 `provider_type=mcp_standard` 和 `McpTransportReadonlyConnector`；只要存在供应商字段映射、业务状态码或特殊参数，就必须建立独立适配器。

## 6. 当前限制

- MCP 目前为同步 HTTP 客户端，适合本地桌面调度；长耗时 AI 工具不应放入定时同步链路。
- HimmPat 监控服务目前通过 `SyncSubscription` 轮询，不假设供应商存在 webhook/push。
- 图片、PDF 等二进制资源继续使用附件文件存储，不写入 SQLite；应由明确的资产同步动作触发。
