# 19 — AI / Automation / MCP：智能化与集成边界

## 1. 总原则

AI 的作用是：

- 提取；
- 翻译；
- 结构化；
- 总结；
- 分类建议；
- 检索辅助；
- 比对辅助；
- 报告草拟；
- 发现关联。

AI 不负责：

- 最终侵权结论；
- 最终风险等级签发；
- 法务/领导决策；
- 自动接受风险；
- 自动改变正式申请策略；
- 直接删除或覆盖责任数据。

## 2. AIProvenance

每次 AI 输出保存：

- execution_id
- entity_type/entity_id
- field_key or task_type
- model_provider
- model_name
- model_version
- prompt_template_id
- prompt_version
- system_policy_version
- input_references
- input_hash
- output_json
- output_schema_version
- confidence
- tokens/cost/latency
- generated_at
- review_status
- reviewer
- reviewed_at
- superseded_by

## 3. Outdated 机制

满足任何条件时，AI 输出可标记 outdated：

- 原权利要求更新；
- PatentDocument 内容重新导入；
- ProjectSolutionVersion 变化；
- 技术分类版本变化；
- prompt/schema 发生不兼容升级；
- 依赖的外部事实发生变化。

outdated 不等于删除。保留旧输出用于追溯。

## 4. 外部专利数据 Connector

建议统一 Connector 接口：

```text
list_changes(cursor, scope) -> ChangePage
fetch_document(external_id) -> RawPatentDocument
fetch_family(external_id) -> RawFamily
fetch_legal_status(external_id) -> StatusEvents
normalize(raw) -> NormalizedPayload
apply(normalized, idempotency_key) -> SyncResult
```

每次同步记录：

- connector
- scope
- cursor_before
- cursor_after
- started_at
- completed_at
- records_seen
- records_created
- records_updated
- errors
- source_version

## 5. 自动化规则

高优先级：

### A. 法律状态变化

Trigger：

- new LegalStatusEvent

Condition：

- PatentDocument/Family 与开放 RiskCase 相关

Action：

- create RiskWatchEvent
- evaluate impact
- mark assessment outdated when necessary
- assign reassessment task

### B. 分案/续案/新同族

Trigger：

- FamilyRelation created

Action：

- 自动关联既有 RiskCase
- 检索师/分析师复核
- 必要时扩展出货法域风险

### C. 项目方案变化

Trigger：

- ProjectSolutionVersion confirmed

Action：

- diff technical features
- find linked risks
- find competitor patents
- find protection gaps
- create review tasks

### D. 月度报告

Trigger：

- schedule

Action：

- refresh saved views
- generate ReportSnapshot draft
- validate required fields
- assign reviewer

## 6. MCP / Tool Registry

不要向 AI 暴露任意数据库查询。

建议第一批只读 tools：

### `get_project_ip_context`

输入：

- project_id
- optional solution_version_id

输出：

- project
- solution
- technical_features
- open_risks
- recent_watch_events
- protection_cases
- filing_summary
- relevant_artifact_refs

### `get_patent_context`

输入：

- patent_document_id / publication_no

输出：

- normalized patent facts
- family
- legal status timeline
- linked projects
- linked risks
- prior analyses
- artifacts

### `search_prior_history`

输入：

- features / module / patent

输出：

- prior SearchCase
- SearchQuery
- RiskCase
- RelevanceReview
- report references

### `get_filing_coverage`

输入：

- project / product / technical_module

输出：

- ProtectionCase
- FilingCase
- jurisdictions
- status
- identified gaps

## 7. 建议的写入 Tools

写入 tools 必须默认创建 draft：

- create_search_case
- propose_patent_project_link
- propose_risk_link
- create_assessment_draft
- create_protection_case_draft
- generate_report_snapshot_draft

所有 responsibility-level 写操作不得直接 confirm。

## 8. Tool 权限

每个 tool 配置：

- allowed_roles
- allowed_scopes
- allowed_fields
- max_rows
- sensitive_field_policy
- write_mode
- requires_confirmation
- audit_level

Tool 输出优先返回实体 ID + 摘要，而不是整表 dump。

## 9. AI 报告生成

正确路径：

`Query source entities -> Snapshot data -> AI summarize -> human review -> publish`

不要：

`AI 直接读取旧 Excel -> 生成不可追溯结论 -> 覆盖正式报告`

## 10. 面向未来的智能能力

模型成熟后可逐步实现：

- 自动识别项目方案变动点；
- 从研发材料抽取 TechnicalFeature；
- 新公开竞对专利自动分类；
- 风险专利 claim amendment 差异摘要；
- 历史风险相似案例检索；
- 检索式推荐；
- 竞对技术路线时间轴；
- 保护空白图；
- 项目 Gate 风险预警；
- 专利挖掘候选提示。

这些能力的前提不是“大模型更强”，而是统一 ID、版本、关系、来源和权限已经完成。
