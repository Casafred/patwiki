# 28 - Agent 导入、数据库 AI 与专利关系可靠性契约

> 状态：`agent-executable / mandatory`
> 更新：2026-08-20
> 用途：修复或新增导入、AI 调用、专利详情关系维护时，Agent 必须遵守的可执行契约。本文件补充 21、24、25、26 号文档；若与用户最新确认的业务事实冲突，以用户事实为准。

## 1. 开发前置

涉及本文件范围的 Agent 必须先读取：

1. `25-agent-development-protocol.md`；
2. `23-2026-product-scope-and-business-rules.md`；
3. `21-implementation-contract.md`；
4. `24-patent-information-hub-functional-spec.md`；
5. `26-human-data-entry-interaction-spec.md`。

实现 PR 必须说明使用了本文件的哪一节，并补充对应自动化验收。

## 2. Excel 导入状态机

### 2.1 列目标语义

| 前端/请求值 | 服务层含义 | 必须行为 |
| --- | --- | --- |
| 已注册字段 key | `mapped` | 按字段覆盖策略写入当前专利，非空值写 `FieldObservation` 和来源 Wiki；空单元格不清空已有值 |
| 空字符串/缺失映射 | `unmapped_retained` | 原始文件、来源行、来源列和值全部保留；合法的其他列继续处理；不自动创建正式字段 |
| `__skip__` | 用户明确跳过该列 | 原始文件和来源行仍保留；该列不进入默认治理观察队列；结果必须显示跳过列数 |
| 未注册目标 key | 请求错误 | 阻止确认前写入并返回具体列和原因；不能静默降级为跳过 |
| 解析/身份冲突 | `quarantined` | 整行阻断；保留完整原始行、候选 Patent ID、观察值和可重试原因 |

未知列不得因为没有标题、申请人、日期或其他非核心字段而阻断同一行的合法字段。

### 2.2 行处理决策

1. 有合法申请号、公开号或授权号：先调用 `patent_identity_service`。
2. 命中一个 Patent：执行字段级增量合并；命中多个 Patent：整行 `quarantined`。
3. 有身份但标题为空：创建/匹配 `title="待补全"` 的身份锚定记录；此值是内部占位状态，不得当作外部标题来源。
4. 没有官方身份且有任何非空内容：只保存 `ImportSourceRow`、`FieldObservation` 和原始附件，状态 `unmapped_retained`；不得猜测创建正式 Patent。
5. 全行无非空内容：才可 `skipped_empty_row`。

导入结果必须至少区分：`created`、`created_pending_title`、`updated_duplicate`、`retained_source_row`、`skipped_empty_row`、`identity_conflict`、`error_mapping`、`error_database`。不能把所有非新增结果统称为“跳过”。

## 3. 数据库 AI 调用边界

### 3.1 单一配置和请求实现

设置页测试和实际 AI 任务必须共同使用 `backend/app/services/llm_service.py` 的边界：

- 配置来自同一 `settings.json` 读取函数；设置页测试允许使用未保存的临时覆盖，但必须明确这不是已保存配置；
- Base URL 必须去除末尾 `/`，并去除误填的 `/chat/completions` 后缀，再统一拼接 `/chat/completions`；
- 请求必须统一使用 OpenAI-compatible JSON、Bearer Key、模型、temperature、max_tokens、连接超时和读取超时；
- HTTP 错误、超时、DNS/连接错误、返回 JSON 不合法、`choices` 缺失和响应内容为空必须转换成可读的 `LLMServiceError`；
- 网络重试只能在连接/超时类错误执行，不能对明确的 4xx 配置错误盲目重试；
- 不得在设置页使用一套客户端、在 AI engine 使用另一套 URL 拼接或另一套配置优先级。

### 3.2 AITask 事务和生命周期

任何快速抽取或批量 AI 调用必须遵守以下顺序：

```text
校验用户输入
  -> 创建 AITask(status=pending) 并 commit
  -> 创建/校验目标字段并更新 task.config
  -> commit
  -> 后台执行并更新 processing/progress
  -> 每条调用记录成功或失败
  -> completed / completed_with_errors / failed 并 commit
```

强制要求：

- 目标字段创建失败、配置缺失、后台任务启动异常都必须产生可查询的 `AITask(status=failed)`；
- 任务列表必须包含失败阶段、错误文本、处理数、成功数、失败数、模型和创建/完成时间；
- 单条专利不存在也必须计入处理进度和失败明细，不能造成任务永远停留 `processing`；
- 每篇专利调用失败不能回滚或删除其他专利已成功结果；
- 任务执行不能以 HTTP 请求响应是否成功作为唯一状态来源；响应返回后仍必须从 `/ai/tasks` 读取实际状态；
- 单篇执行失败至少记录 `patent_id`、`stage`（`prepare`/`execute`/`background`）和可读 `error`；快速抽取响应无法解析为 JSON 时必须进入失败，不能把空对象当作成功并写入空值；
- 前端不得把后端的可读任务错误丢成单一 `NetworkError`。Axios 错误优先展示 `response.data.message`，再展示 `detail`，最后才展示网络错误本身。

### 3.3 AI 写入规则

- AI 生成内容默认为草稿，保存模型、输入字段、提示词/请求样本、响应样本、任务 ID 和时间；
- AI 不得直接写入风险正式结论、外部事实、项目关系、专利身份或兼容风险投影；
- AI 抽取目标只能是已经注册且允许 AI 草稿写入的字段，公式、附件、Link、Lookup、Rollup 和系统事实字段必须拒绝；
- 用户明确选择新字段时可以创建可编辑字段，但 AI 值仍然标记为草稿，不能自动签发正式结论；
- 响应 JSON 解析失败必须保留原始响应和任务失败明细，不得把空字符串当成成功结果。

## 4. 专利-项目关系维护

项目关系是多值关系实体，不能写成专利表里的逗号文本或前端临时数组。当前详情页必须支持：

- `GET /patents/{patent_id}/projects`：返回当前关系和项目展示信息；
- `PUT /patents/{patent_id}/projects`：兼容接收去重后的 `project_ids`；需要维护关系属性时接收 `links:[{project_id, role, relation_type, risk_level, document_role, relevance_score, importance, notes, assigned_to_id}]`，由服务层整体校验和替换；
- 不存在的项目、无效 ID 或数据库约束错误必须拒绝整次操作并保留旧关系；
- 添加/移除关系不要求提交整篇 Patent 编辑表单；成功后详情页立即刷新，失败时保留选择并可重试；
- 关系增加多维属性时，必须通过 `PatentProjectLink` 服务入口维护 `relation_type`、`role`、`notes` 等，不得在页面中直接操作 ORM secondary 数组绕过审计。

## 5. 自动化验收门禁

### 导入

- 未知列留在 `FieldObservation`，空映射不阻断已知列；
- 显式 `__skip__` 与默认空映射结果不同；
- 有公开号无标题创建 `created_pending_title`；
- 无身份有内容进入 `retained_source_row`；完全空行才是 `skipped_empty_row`；
- 重复导入仍保留观察、来源表、Sheet、行号和导入时间。

### AI

- 设置测试和实际调用使用同一 URL/模型/Key 解析；
- 缺 Key、目标字段不存在、字段不允许写入、网络失败、返回解析失败均能在 AI 任务列表看到 `failed`；
- 任务失败包含阶段和可读原因，任务不会消失或卡在 processing；
- LLM 返回空内容或无法解析的抽取 JSON 会失败且不写入空值；
- 单条成功和批量部分失败互不回滚。

### 项目关系

- 详情页直接添加项目、读取项目、移除项目；
- 添加不存在项目返回明确错误且旧关系不变；
- 关系操作不改变专利其他字段；
- 前端 ESLint、TypeScript、Vite build 与相关后端测试必须通过。

## 6. 禁止回退

- 禁止恢复“标题为空即 skipped”；
- 禁止将空映射重新解释为跳过或丢弃；
- 禁止在后台调用前先执行不可追踪的网络请求；
- 禁止只在浏览器控制台记录 AI 错误而不写 `AITask`；
- 禁止要求用户进入整篇编辑模式才能维护单条项目关系；
- 禁止用 `except Exception: pass` 隐藏 LLM 配置读取、请求或任务状态更新失败。
