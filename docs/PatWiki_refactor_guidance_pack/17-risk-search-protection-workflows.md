# 17 — Risk / Search / Protection 工作流设计

## 1. 总体原则

三个组不是三套数据库，而是围绕 ProjectSolutionVersion 和 Patent/Technology 共享上下文的三类 Case。

- 检索组：`SearchCase`
- 分析组：`RiskCase + RiskAssessmentVersion`
- 保护组：`ProtectionCase + FilingCase`

三组共同引用：

- Project
- ProjectSolutionVersion
- ProductCategory
- TechnicalFeature/Module
- PatentFamily/Document
- Artifact
- Person

---

# 2. 检索组

## 2.1 SearchCase 状态机

建议：

`draft -> scope_confirming -> searching -> reviewing -> completed -> reopened`

reopened 触发条件：

- 方案版本变化；
- 出货地区变化；
- 新公开竞对专利；
- 风险专利产生分案/续案；
- 分析师要求补充检索。

## 2.2 SearchCase 关键对象

### SearchCommunication

保存：

- 沟通时间
- 沟通人
- 方案背景
- 待检方案
- 产品图/技术资料附件
- 排查思路
- 研发确认

### SearchConcept

保存：

- 检索要素
- 同义词
- IPC/CPC
- 申请人/竞对
- 技术模块
- 来源：历史策略/AI/人工/竞对专利逆向

### SearchQuery

保存：

- query string
- 数据库平台
- 查询字段
- 筛选策略
- 思路说明

### SearchQueryRun

保存：

- query_id
- run_at
- source_system
- source_version
- result_count
- result_hash
- elapsed_time
- operator

### SearchHit

保存：

- query_run_id
- patent_document_id
- rank
- source_rank
- matched_concepts

### RelevanceReview

保存：

- search_case_id
- patent_document_id
- solution_version_id
- relevance_level / score
- review_note
- reviewer
- reviewed_at
- historical_risk_rollup
- family_continuation_rollup

## 2.3 检索输出

检索结果表应由 SearchHit + PatentDocument + RelevanceReview 生成。

检索策略记录应由 SearchConcept + SearchQuery + QueryRun 生成。

---

# 3. 分析组 / 风险

## 3.1 RiskCase 生命周期

建议：

`identified -> triage -> analyzing -> mitigation_pending -> decision_pending -> monitoring -> closed`

但“closed”不代表永久消失。若 RiskWatch 触发：

`closed/monitoring -> reassessment_required`

## 3.2 RiskCase 与 Assessment 分层

RiskCase 是长期风险事项。

RiskAssessmentVersion 是在某个时间点、某个输入条件下的分析。

建议保存：

- risk_case_id
- solution_version_id
- jurisdiction_id
- patent_claim_version
- evidence_snapshot_id
- input_hash
- assessed_at
- analyst
- risk_level
- conflict_status
- conclusion
- status: draft/confirmed/outdated/superseded

## 3.3 Claim Analysis

拆解：

`Claim -> ClaimElement -> FeatureComparison -> Evidence -> ElementConclusion`

每个 claim element 建议记录：

- claim_no
- element_no
- source_text
- translation
- interpretation
- solution_feature_id
- product_evidence_artifact_id
- match_status
- rationale
- comparison_prior_art
- reviewer

## 3.4 风险等级不要脱离维度

风险等级建议由以下维度共同产生，而不是一个不可解释的人工枚举：

- claim overlap / conflict strength
- legal status strength
- jurisdiction relevance
- product adoption status
- shipment region
- design-around difficulty
- commercial exposure
- family continuation risk
- evidence confidence
- urgency

最终可以映射为 `low / medium / high / critical`，但维度评分/说明要保留。

## 3.5 RiskDecision

正式风险会/领导/法务决策必须独立记录：

- decision_type
- decision_at
- participants
- decision_maker
- legal_participant
- conclusion
- accepted_risk_level
- required_actions
- conditions
- due_at
- review_at
- evidence_snapshot
- created_by

不得直接修改旧 Decision。

## 3.6 RiskWatch

典型触发：

- application published
- grant
- rejection/abandonment
- invalidation
- assignment
- continuation/divisional
- new family member
- claim amendment
- term/expiration
- ProjectSolutionVersion changed
- target country added
- mitigation design changed

触发后：

1. 创建 `RiskWatchEvent`；
2. 计算受影响 RiskCase；
3. 标记当前 assessment `outdated`（若输入确实变化）；
4. 创建新的 assessment draft；
5. 通知分析师；
6. 必要时升级给项目/领导。

---

# 4. 保护组

## 4.1 ProtectionCase 状态

建议：

`idea -> mining -> strategy_review -> drafting -> filing_planned -> filed -> active_portfolio -> closed`

ProtectionCase 是保护主题，不等于具体申请。

## 4.2 ProtectionCase

保存：

- source_project_id
- source_solution_version_id
- technical_modules
- invention_theme
- protectable_features
- novelty_position
- protection_scope_strategy
- business_importance
- competitor_context
- internal_owner
- approved_by
- status

## 4.3 FilingStrategy

一条 ProtectionCase 可产生多个布局记录：

- jurisdiction
- filing_route
- filing_type
- target_date
- priority_strategy
- core/peripheral/defensive role
- budget
- reason
- approved_by

## 4.4 FilingCase

保存具体案件：

- internal_docket_no
- application_no
- publication_no
- patent_document_id
- jurisdiction
- attorney/agency
- internal_owner
- filing_date
- current_status
- deadline rollups

## 4.5 OfficeAction / Docket

所有期限均进入事件/任务模型，而不是人工维护一个“当前状态”文本。

---

# 5. 三组联动规则

## Search -> Risk

高相关 SearchHit 若满足：

- 有效/待授权权利要求；
- 与出货地区匹配；
- 与当前方案特征高度关联；

可一键创建 RiskCase 草稿。

## Risk -> Search

RiskAssessment 发现：

- 权利要求解释不确定；
- 需要前案；
- 分案续案风险；
- 需要无效证据；

创建补充 SearchCase，并关联原 RiskCase。

## Project -> Risk

ProjectSolutionVersion 新增/删除技术特征：

- 自动匹配历史 RiskCase；
- 标记相关 assessment 是否 outdated；
- 生成复核任务。

## Project -> Protection

新增技术特征且满足：

- 无已覆盖 ProtectionCase；
- 商业价值达到阈值；
- 非明显已公开；

生成挖掘候选。

## Risk -> Protection

因规避产生的新结构/方案：

- 检查是否构成新的可保护主题；
- 形成 ProtectionCase 候选；
- 防止“为了规避竞对，产生创新但没有申请”。

---

# 6. 管理层视角

领导看到的不是原始过程表，而是：

- 未关闭 Critical/High RiskCase；
- 临近项目 Gate 且未完成规避的风险；
- 最近因外部状态变化被重新打开的风险；
- 保护空白；
- 高价值 ProtectionCase 的进度；
- 期限逾期/即将逾期；
- 各组负载与 SLA；
- 决策待办。

所有卡片可钻取到原始 evidence、assessment 和 history。
