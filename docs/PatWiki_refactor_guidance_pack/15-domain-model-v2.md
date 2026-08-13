# 15 — Domain Model V2：PatWiki 统一领域模型

> 实施约束：先阅读 `21-implementation-contract.md`。本文描述目标领域模型；当前物理 `Patent` 表在兼容期承担 `PatentDocument` 角色，不在本阶段重命名。

## 1. 建模目标

PatWiki 不应继续以“所有业务都给 Patent 增加字段”为演化方式。Patent（目标术语为 PatentDocument）仍是专利知识的锚点，但 IP 业务至少存在以下一级聚合根：

- `Project`
- `ProjectSolutionVersion`
- `PatentFamily`
- `PatentDocument`
- `SearchCase`
- `RiskCase`
- `ProtectionCase`
- `FilingCase`
- `Artifact`
- `ReportSnapshot`

聚合根之间通过带属性的关系实体连接。

所有可独立查询、导入、审计或访问控制的业务聚合根还必须有 `database_id` 作为工作台归属；`database_id` 用于数据集合与查询范围，当前并不构成认证隔离。每个聚合根同时至少保存 `created_at`、`updated_at`、来源和责任人/创建人。

## 2. 领域边界

### 2.1 Organization

核心对象：

- Department
- Team
- Person
- Role
- PersonRoleAssignment

规则：

- 人名不得在责任性字段中只保存自由文本。
- “分析师/检索师/保护师/领导/法务/研发/项目管理/产品经理”是角色，不应复制成多个 Person 表。
- 角色分配允许有效期。

### 2.2 Product

核心对象：

- ProductLine
- ProductCategory
- Product
- ProductVariant
- DepartmentProductLineLink
- ProductLineCategoryLink

关键点：

- Department ↔ ProductLine 支持 N:M。
- ProductLine ↔ ProductCategory 支持 N:M。
- Product 可有一个 primary category，也可有多个辅助分类。
- 商用/家用等组织视角与“产品品类”不是同一棵树。

### 2.3 Project

核心对象：

- Project
- ProjectMember
- ProjectStageEvent
- ProjectRegionLink

Project 只保存当前快照字段，如 `current_stage`；历史阶段保存在 ProjectStageEvent。

### 2.4 ProjectSolutionVersion

这是 V2 的 P0 实体。

建议字段：

- id
- project_id
- version_no
- name
- effective_from
- effective_to
- project_stage
- source_solution_version_id
- inherited_product_id
- change_summary
- change_reason
- status
- confirmed_by
- confirmed_at
- created_at / updated_at

关系：

- SolutionVersion ↔ TechnicalFeature
- SolutionVersion ↔ Artifact
- SolutionVersion ↔ Region
- SolutionVersion ↔ RiskCase
- SolutionVersion ↔ SearchCase
- SolutionVersion ↔ ProtectionCase

任何风险评估必须明确基于哪个 `solution_version_id`。

P0 约束：一个 SearchCase、RiskAssessmentVersion 或 ProtectionCase 草稿只允许一个 `primary_solution_version_id`。多方案比较是后续显式 scope link 的能力，不能先用 JSON 数组、逗号文本或多选 CustomField 代替。

### 2.5 Technology Taxonomy

核心对象：

- TechnicalDomain
- TechnicalModule
- TechnicalFeature
- TaxonomyAlias
- TaxonomyEdge

技术分类不能只是一条字符串路径。建议支持：

- parent-child 层级；
- 多父节点；
- 同义词/旧名称；
- 生效版本；
- 人工/AI/IPC 等分类来源。

`TechnicalFeature` 是可被方案、权利要求和专利关系引用的稳定概念；分类树的父子或多父关系应由 `TaxonomyEdge` 表示，不应把 `parent_id` 同时承担树和多父图两种语义。

### 2.6 Patent Common Data

核心对象：

- PatentFamily
- PatentDocument
- PriorityClaim
- FamilyRelation
- LegalStatusEvent
- PatentPartyLink
- Party

原则：

- 一个国家/地区的申请/公开号/授权号对应具体 `PatentDocument`。
- 同族对应 `PatentFamily`。
- 分案、续案、继续申请等通过 `FamilyRelation` 表达。
- `current_legal_status` 可以作为缓存，但完整事实来自 `LegalStatusEvent`。
- 原始申请人/权利人值和标准化 Party 必须并存。

兼容策略：在当前仓库中用 `Patent.id` 作为 V2 `patent_document_id` 的外键目标；`PatentFamily` 保持现有物理表。表重命名、全量拆分 PatentDocument 和真正的 Party 正规化均放在迁移稳定后的独立决策中。

### 2.7 Search

核心对象：

- SearchCase
- SearchCommunication
- SearchConcept
- SearchQuery
- SearchQueryRun
- SearchHit
- RelevanceReview

不要在 SearchQuery 单元格中保存“该式找到的全部专利号”。命中结果通过 `SearchQueryRun -> SearchHit` 表达。

### 2.8 Risk

核心对象：

- RiskCase
- RiskPatentLink
- RiskSolutionLink
- RiskAssessmentVersion
- ClaimAnalysis
- ClaimElementAnalysis
- MitigationPlan
- MitigationAction
- RiskDecision
- RiskWatchRule
- RiskWatchEvent

核心原则：

`Risk = Patent/Family × SolutionVersion × Jurisdiction × Time × Evidence`

因此 `Patent.has_risk / risk_level / risk_description` 只能作为物化汇总缓存，不能作为正式风险数据源。

### 2.9 Protection

核心对象：

- ProtectionCase
- InventionTheme
- ProtectionSolutionLink
- FilingStrategy
- FilingCase
- OfficeAction
- OfficeActionResponse
- Docket
- Fee / MaintenanceEvent

一个保护主题可对应多件申请、多国申请；布局国家不应只保存在一个多选字段里。

### 2.10 Artifact

统一所有附件：

- email
- ppt
- patent_pdf
- word
- spreadsheet
- image
- sample_evidence
- report
- external_link
- other

对象：

- Artifact
- ArtifactVersion
- ArtifactLink

`ArtifactLink(entity_type, entity_id, role)` 使任何 Patent / Project / Risk / Assessment / Search / Filing 都能追溯全部证据。

### 2.11 Report

对象：

- SavedView
- ReportTemplate
- ReportSnapshot
- ReportSnapshotItem
- SharePackage

月度、季度、年度和对外表均应由源数据生成快照，而不是复制出另一套主数据。

## 3. 关键关系

| A | B | 基数 | 关系实体/说明 |
|---|---|---:|---|
| Department | ProductLine | N:M | DepartmentProductLineLink |
| ProductLine | ProductCategory | N:M | ProductLineCategoryLink |
| Product | Project | 1:N | Project.product_id |
| Project | ProjectSolutionVersion | 1:N | 方案版本 |
| ProjectSolutionVersion | TechnicalFeature | N:M | SolutionFeatureLink |
| PatentFamily | PatentDocument | 1:N | family_id |
| PatentDocument | TechnicalModule | N:M | PatentModuleLink |
| Project | PatentDocument | N:M | PatentProjectLink |
| SearchCase | PatentDocument | N:M | SearchHit |
| RiskCase | PatentDocument | N:M | RiskPatentLink |
| RiskCase | ProjectSolutionVersion | N:M | RiskSolutionLink |
| RiskCase | RiskAssessmentVersion | 1:N | 评估版本 |
| ProtectionCase | ProjectSolutionVersion | N:M | ProtectionSolutionLink |
| ProtectionCase | FilingCase | 1:N | 多国/多件申请 |
| Any Entity | Artifact | N:M | ArtifactLink |

`ArtifactLink` 是受控的多态关联：实体类型必须在服务端白名单内，写入时验证目标存在、`database_id` 一致、调用者权限和审计；不能依赖数据库外键自动保证完整性。

## 4. 当前快照 vs 历史事实

以下属性可以有 current 缓存，但正式历史必须由事件/版本支持：

- PatentDocument.current_legal_status
- Project.current_stage
- RiskCase.current_risk_level
- RiskCase.current_status
- MitigationPlan.current_status
- FilingCase.current_status

## 5. V2 聚合根边界规则

一个对象满足下列任一条件时，应从 CustomField 提升为独立实体：

1. 有独立生命周期；
2. 有独立负责人；
3. 有多个状态；
4. 有历史版本；
5. 有附件；
6. 会被多个业务对象引用；
7. 会形成多对多关系；
8. 需要独立权限；
9. 需要独立审计；
10. 将被自动化或 AI tool 直接操作。

## 6. 与现有 PatWiki 的兼容

保留当前：

- PatentDatabase
- PatentView
- CustomField
- ViewLocalField
- PatentProjectLink
- AutomationRule

但扩展方向为：

- PatentView → 跨实体 Dataset/View；
- PatentProjectLink 的“关系带业务属性”模式推广到其他核心关系；
- PatentHistory → 通用 AuditEvent；
- Patent.ai_fields → 通用 AIProvenance。

补充约束：

- `Patent.has_risk/risk_level/risk_description` 在 V2 切换后只保留为由已确认评估生成的兼容聚合缓存，禁止详情页直接编辑。
- `PatentHistory` 在兼容期继续保留，新 V2 聚合根统一写 `AuditEvent`；不要删除既有历史。
- `PatentDatabase` 是所有 V2 Case 的工作台归属；每个关联两端必须属于同一 `database_id`，除非明确实现受审计的跨库引用。
- 任何新增物理表、外键和索引均通过受版本控制的迁移引入，不能直接执行 `schema-v2-draft.sql`。
