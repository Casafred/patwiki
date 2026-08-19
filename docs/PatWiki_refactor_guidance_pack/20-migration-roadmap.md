# 20 — Migration Roadmap：从现有 PatWiki / Excel 逐步迁移到 V2

> 实施约束：本路线图受 `23-2026-product-scope-and-business-rules.md` 与 `21-implementation-contract.md` 约束。先建设迁移平台，再完成专利信息中心；当前 `_ensure_column_migration()` 的容错加列不能继续作为 V2 复杂迁移机制。

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
8. 对暂时无法识别的来源列建立 `unmapped_retained` 记录；对真正无法解析或身份冲突的行建立 `quarantined` 记录。

验收：

- 31 类原表每一列处于 candidate、unmapped_retained、mapped、deprecated 或 quarantined 状态；
- 未注册属性仍可查询、导出和后续映射，但不会未经确认进入默认统计或责任性结论；
- 不再允许未知属性静默丢弃，也不允许未注册属性直接作为正式字段上线。

---

## Phase 0C — Patent Information Hub

目标：先把每篇专利的身份、事实、来源和高频关联信息治理好，形成今年的核心产品。

工作：

1. 冻结申请号、公开号、授权号、国家/地区、同族和外部 ID 的标准化与去重规则；
2. 建立 `PatentIdentifier`，把同一申请链的申请号、申请公开号和授权公告号关联到同一专利；
3. 建立外部事实的字段级覆盖策略，保留来源平台、工作簿、表格/工作表标题、来源行、原始值、标准化值和来源时间；
4. 建立 `PatentImportEvent + FieldObservation`，区分新增、相同、格式差异、内容冲突、身份冲突和受保护字段冲突；
5. 重构专利详情聚合读取，按 24 号规格的著录、加工、权利要求、说明书、同族、分类、项目风险、我司保护、附件和 Wiki 历史分组；
6. 支持智慧芽、Himmpat、德温特等 Excel 的可重复导入、预览、冲突提示和异常隔离；
7. 让人工分类、判断和内部信息默认不被外部导入覆盖。

验收：

- 同一专利重复导入不会产生重复主记录；
- 同一申请的公开和授权号码归入同一 PatentDocument，不错误合并不同国家同族；
- 任一关键事实可说明来源、导入时间和覆盖过程；
- 即使当前值未变化，Wiki 历史仍可看到本次导入表格和字段观察；
- 任一专利可从一个详情入口看到所有已录入关联信息；
- 导入失败或字段冲突不会污染既有人工信息。

---

## Phase 0D — Interactive Views

目标：让专利信息能够高频查询、组织和批量处理。

工作：

1. 完成快速搜索、组合筛选、排序、分组、列配置和保存视图；
2. 完成批量选择、批量编辑、关系钻取和同族展开；
3. 优先建立风险会风险统计、品类我司申请、单项目风险管控、单项目申请管控、产品品类数据总库和日常相关专利积累六个视图；
4. 用其余真实台账逐类验证所需输入和筛选，而非一次性复制 31 套页面；
5. 记录常用列表的真实性能基线并优化索引和分页。

验收：

- 常用台账的查询范围可由保存视图复现；
- 列配置、筛选条件和分组方式可复用；
- 现有 `/patents`、视图、导入和附件能力回归通过。

---

## Phase 0E — Excel / Word Work Product Output

目标：让专利数据库直接支撑现有 Excel 台账和 Word 检索/分析工作文件。

工作：

1. 建立可复用 Excel 导出模板、字段顺序和格式规则；
2. 建立 Word 检索/分析报告的数据装配接口、章节和专利引用约定；
3. 支持从选中专利或保存视图生成输出；
4. 记录模板版本、生成时间、来源视图和字段来源。

验收：

- 常用台账可由保存视图和导出模板生成，不再重复整理专利著录信息；
- 导出字段、顺序和格式可复用；
- 输出值可追溯到专利、来源字段或人工确认记录；
- 至少用一个真实 Excel 台账和一个 Word 检索报告完成端到端验收。

---

以下 Phase 1-9 是围绕专利信息中心逐步增强的长期路线。它们不能阻塞 Phase 0C-0E，也不代表 2026 年必须全部交付。

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

## Phase 2 — 轻量 ProjectSolutionVersion

> 当前状态（2026-08-19）：轻量切片已实现。已落地方案版本、变化点、地区、来源描述、确认/替代关系，以及风险案例所需的方案关联；TechnicalFeature、Artifact、BOM/图纸和 PLM 同步仍未实现。

目标：为专利风险和项目关联补充可复原的方案上下文，不建设完整研发版本管理。

工作：

1. 建立方案快照与变更记录；
2. 记录项目、TR 阶段、变更特征、适用地区、来源描述和来源附件；
3. 建立必要的 TechnicalFeature 关联；
4. 保存检索师录入人、录入时间和人工确认状态；
5. 暂不建设 BOM、图纸、PLM 同步和完整研发版本基线。

历史还原不完整时：

- `provenance=legacy_inferred`
- `confidence`
- `needs_confirmation=true`

验收：

- 涉及具体项目方案的正式风险评估必须引用方案快照和法域；普通专利导入、分类、检索命中和保护信息录入不以方案版本为前置条件。

---

## Phase 3 — Risk V2

> 当前状态（2026-08-19）：基础切片已实现，完整 Risk V2 尚未完成。已落地 RiskCase、RiskPatentLink、RiskSolutionLink、追加式 RiskAssessmentVersion 和 RiskReviewEvent；ClaimAnalysis、Mitigation、RiskDecision、RiskWatch、ArtifactLink、Patent.risk_* rollup 和正式版本化迁移仍属于后续工作。

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
- 待治理/尚未映射字段（包括已保留的未知属性）；
- 已保留的未知列数量、来源和样例值；
- 未知列后续映射/回填批次；
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
  "rows_unmapped_retained": 12,
  "unknown_fields": ["原始表.新字段"],
  "unknown_field_samples": {"原始表.新字段": ["样例值1", "样例值2"]},
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
