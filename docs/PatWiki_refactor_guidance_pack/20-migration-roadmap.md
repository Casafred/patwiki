# 20 — Migration Roadmap：从现有 PatWiki / Excel 逐步迁移到 V2

> 实施约束：本路线图受 `21-implementation-contract.md` 约束。先建设迁移平台，再进入任何业务域；当前 `_ensure_column_migration()` 的容错加列不能继续作为 V2 复杂迁移机制。

## 0. 原则

- 不推倒重来；
- 不先重做全部 UI；
- 不直接删除旧字段；
- 先建立统一 ID 和数据血缘；
- 新旧模型并行一段时间；
- 每阶段有可量化验收；
- 每一步可回滚。

---

## Phase 0A — Migration Platform / Safety Gate

目标：让每一次模式和数据迁移可识别、可停止、可恢复。

工作：

1. 建立受版本控制的迁移账本与迁移执行记录；
2. 每次迁移前创建 SQLite 备份，执行完整性检查、升级、关键行数核对和恢复演练；
3. 运行时显式启用 SQLite foreign keys，失败时停止启动；
4. 建立来源行、隔离问题和映射版本的可追踪记录；
5. 用真实历史库副本验证重复执行、失败恢复和旧 API 回归。

验收：

- 任意迁移可识别当前版本、校验和和执行结果；
- 失败迁移不污染原库，恢复演练可通过；
- 未解决数据问题可定位到来源文件、工作表、行号和业务键；
- 新增 V2 表不再通过吞异常的 `ALTER TABLE` 进入生产数据。

---

## Phase 0B — Field Registry / Baseline

目标：冻结语义，不再继续制造同义字段。

工作：

1. 建立 Field Registry。
2. 建立 Alias Registry。
3. 给现有表/导入行增加 `source_table/source_row_id`。
4. 统一项目号、产品号、专利号 normalization。
5. 统一基础枚举。
6. 标记每个字段的数据责任等级。
7. 对每个 canonical field 记录存储位置、迁移状态和业务负责人。

验收：

- 31 类原表每一列处于 mapped、deprecated 或 quarantined 状态；
- 不再允许未注册的责任性字段直接上线。

---

## Phase 1 — 主数据与分类

目标：消灭核心自由文本。

新增/调整：

- Person / Role
- ProductCategory
- DepartmentProductLineLink
- ProductLineCategoryLink
- Technical taxonomy
- Project member / region / stage event

迁移：

- 产品类型/品类/分类 → ProductCategory
- 技术模块字符串 → taxonomy ID
- 人名文本 → Person ID

验收：

- 关键统计不依赖名称文本 join。
- 所有新关系两端有同一 `database_id`，且创建/失效/去重规则有服务层测试。

---

## Phase 2 — ProjectSolutionVersion

目标：风险、检索、保护都能引用具体方案。

工作：

1. 建表；
2. 现有项目创建 baseline v1；
3. 导入“继承历史产品型号、继续历史产品具体方案点、阶段方案变动点”；
4. 建 TechnicalFeature；
5. 关联出货地区和证据。

历史还原不完整时：

- `provenance=legacy_inferred`
- `confidence`
- `needs_confirmation=true`

验收：

- 新 SearchCase/RiskAssessment/ProtectionCase 草稿必须有单一 primary solution context；确认态 RiskAssessment 还必须有法域、输入哈希、责任人和证据引用。

---

## Phase 3 — Risk V2

目标：移除 Patent 全局风险真相。

新增：

- RiskCase
- RiskPatentLink
- RiskSolutionLink
- RiskAssessmentVersion
- ClaimAnalysis
- Mitigation
- RiskDecision
- RiskWatch

迁移顺序：

1. 依据风险主题、相关项目、专利族形成 RiskCase 候选；
2. 风险表中分析报告挂 Artifact；
3. 会议字段转 Decision；
4. 规避字段转 Mitigation；
5. 当前风险等级转 latest confirmed Assessment；
6. Patent.risk_* 改为 rollup。

兼容期：

旧页面仍可显示 Patent 风险列，但值来自聚合。

验收：

- 所有旧风险统计表可由 V2 查询生成；
- 新评估不会覆盖历史。
- `Patent.risk_*` 与最新 confirmed Assessment rollup 的差异可监控，切换前差异为零或有已批准例外。

---

## Phase 4 — Search V2

新增：

- SearchCase
- SearchCommunication
- SearchConcept
- SearchQuery
- SearchQueryRun
- SearchHit
- RelevanceReview

迁移：

- TC号 → SearchCase；
- 检索式 → SearchQuery；
- 检索时间/数量 → QueryRun；
- 专利号列表 → SearchHit；
- 相关性复核 → RelevanceReview。

验收：

- 能复现某次历史搜索；
- 能比较同一 query 两次运行的结果差异。
- 无法重放的历史搜索保留导出结果 Artifact、查询版本和结果哈希。

---

## Phase 5 — Protection V2

新增：

- ProtectionCase
- FilingStrategy
- FilingCase
- OfficeAction
- Docket
- MaintenanceEvent

迁移：

- “挖掘主题/申请保护主题” → ProtectionCase；
- “申请号” → FilingCase；
- “布局国家”拆子记录；
- 代理所/承办人结构化。

验收：

- 一个保护主题可展示全球 filing tree 和所有期限。

---

## Phase 6 — Artifact / Audit / Permission

新增：

- Artifact
- ArtifactVersion
- ArtifactLink
- AuditEvent
- ApprovalRequest
- sensitive field policy

迁移：

- 分析报告
- 专利原文
- 邮件
- PPT
- Word
- 表格
- 样机图片
- 外链

验收：

- 从 RiskCase / Patent / Project / Filing 任一页一键追溯材料；
- 高敏导出有日志。
- 在完成认证与服务端授权前，L4/L5 只允许受控本机测试；不得向真实外部对象开放分享或 MCP 写入。

---

## Phase 7 — View / Snapshot

目标：逐步停止维护重复 Excel 台账。

工作：

- 将月度风险、NEW项目风险会、挖掘、季度分享等定义为 SavedView；
- 定义 ReportTemplate；
- 生成冻结 Snapshot；
- 对外发布走 SharePackage。

验收：

- 月报/季度表关键值 100% 来源于主数据；
- 历史报告可复现。

---

## Phase 8 — External Sync / Automation

优先：

1. 法律状态；
2. 同族/分案续案；
3. 新公开竞对；
4. 期限；
5. 项目方案变化联动。

要求：

- idempotency
- cursor
- retry
- sync log
- source timestamp

验收：

- 外部变化能生成 WatchEvent；
- 不重复写事件；
- 失败可重试。

---

## Phase 9 — AI / MCP

先只读后写草稿。

第一批 tools：

- get_project_ip_context
- get_patent_context
- search_prior_history
- get_filing_coverage

第二批：

- create_search_case
- create_assessment_draft
- propose_links
- generate_report_snapshot_draft

验收：

- tool 有权限边界和审计；
- AI 输出有 provenance；
- AI 不直接修改 confirmed 决策。

---

## 数据迁移验收矩阵

每张旧表至少检查：

- 行数；
- 唯一业务键；
- 核心字段 null rate；
- 多值关系拆分数量；
- 未识别 alias；
- 无法映射字段；
- 附件链接完整性；
- 责任人映射；
- 时间字段；
- 新查询生成旧表的差异。
- 迁移版本、备份 ID、恢复验证结果；
- 新旧读模型切换状态与业务负责人签收。

建议保留迁移报告：

```json
{
  "source": "legacy_table_name",
  "batch_id": "...",
  "rows_seen": 1000,
  "rows_migrated": 995,
  "rows_quarantined": 5,
  "links_created": 2200,
  "aliases_unresolved": [],
  "started_at": "...",
  "completed_at": "..."
}
```

---

## PR 拆分建议

不要一个 PR 同时改：

- schema
- migration
- services
- routes
- UI
- AI tools

推荐：

1. migration platform + backup/restore tests；
2. schema + versioned migration；
3. repository/service；
4. API；
5. read-only UI；
6. compatibility adapter + reconciliation report；
7. write workflow；
8. tests + rollback evidence；
9. automation/AI。

每个 Phase 先实现 read model，再切 write path；写路径切换前必须完成双读核对、迁移回滚演练和现有 `/patents`、导入、附件、视图、AI 字段、历史接口回归。
