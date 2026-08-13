# 20 — Migration Roadmap：从现有 PatWiki / Excel 逐步迁移到 V2

## 0. 原则

- 不推倒重来；
- 不先重做全部 UI；
- 不直接删除旧字段；
- 先建立统一 ID 和数据血缘；
- 新旧模型并行一段时间；
- 每阶段有可量化验收；
- 每一步可回滚。

---

## Phase 0 — Field Registry / Baseline

目标：冻结语义，不再继续制造同义字段。

工作：

1. 建立 Field Registry。
2. 建立 Alias Registry。
3. 给现有表/导入行增加 `source_table/source_row_id`。
4. 统一项目号、产品号、专利号 normalization。
5. 统一基础枚举。
6. 标记每个字段的数据责任等级。

验收：

- 31 类原表每一列可映射到 canonical field；
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

- 新 SearchCase/RiskAssessment/ProtectionCase 必须有 solution context。

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

1. schema + migration；
2. repository/service；
3. API；
4. read-only UI；
5. write workflow；
6. compatibility adapter；
7. tests；
8. automation/AI。

每个 Phase 先实现 read model，再切 write path。
