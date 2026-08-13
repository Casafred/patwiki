# 16 — Field Governance Registry：字段治理与注册规范

## 1. 为什么需要 Field Registry

当前大量表格存在：

- 同义字段：产品类型/产品品类/产品分类；
- 同义专利字段：风险专利号/同族专利号/公开号；
- 重复事实：项目号、产品号、专利权人、优先权日被多表复制；
- 状态字段被覆盖；
- AI 结果和责任性判断混用；
- 多值关系以文本存储。

Field Registry 的作用是让新增字段先回答“它是什么”，再决定“放在哪张视图”。

## 2. 每个字段的 12 维元数据

建议 `FieldDefinition` 至少增加：

| 字段 | 说明 |
|---|---|
| owner_entity_type | Patent / Project / RiskCase / SearchCase 等 |
| semantic_type | identifier / fact / status / judgment / derived / reference / attachment / snapshot |
| source_type | manual / external_api / ai / formula / collaboration / import |
| source_system | 数据库或外部系统 |
| source_timestamp | 外部事实采集时间 |
| volatility | immutable / stable / event_driven / periodic / ephemeral |
| update_policy | never / on_event / scheduled / manual / recompute |
| freshness_ttl | 多久后视为过期 |
| validation_schema | JSON Schema / enum / regex / range |
| sensitivity | internal / confidential / highly_confidential |
| audit_policy | normal / strict / source_provenance / immutable |
| ai_policy | forbidden / assist / generate_draft / generate_and_review |

建议继续扩展：

- read_roles
- write_roles
- approval_policy
- lock_policy
- retention_policy
- index_policy
- promote_threshold

## 3. 字段分类规则

### 3.1 标识字段

例：

- 项目号
- 产品号
- 申请号
- 公开号
- 专利卷号
- TC 号

要求：

- 业务唯一性；
- 格式校验；
- 确认后受限修改；
- 修改必须保留旧值和原因。

### 3.2 外部事实

例：

- 申请日
- 优先权日
- IPC/CPC
- 申请人
- 法律状态事件

要求：

- source_system；
- source_timestamp；
- raw_value 与 normalized_value；
- 不得由 AI 凭空生成。

### 3.3 研发事实

例：

- 出货地区
- 项目阶段
- 方案版本
- 继承点
- 方案变动点

要求：

- 项目/研发责任人确认；
- 方案事实版本化；
- 变更可触发 Risk Watch。

### 3.4 专业判断

例：

- 相关性
- 是否冲突
- 风险等级
- 风险结论
- claim chart
- 申请策略

要求：

- reviewer；
- confirmed_at；
- 严格版本；
- 必要时审批；
- AI 只可辅助。

### 3.5 正式决策

例：

- 风险接受
- 会议结论
- 法务意见
- 领导批准的申请策略

要求：

- 不可变追加；
- 不能原地覆盖；
- participant + decision_at + basis；
- 修订通过新 Decision 实体产生。

### 3.6 AI 派生字段

例：

- 权利要求翻译
- 摘要翻译
- 技术问题
- 技术方案
- 技术效果
- 实施例总结
- 分类建议

要求：

- model；
- prompt_version；
- input_hash；
- output_schema；
- generated_at；
- review_status；
- reviewer；
- superseded_by。

## 4. 哪些字段需要时间戳

至少需要：

- created_at
- updated_at
- confirmed_at
- source_timestamp
- effective_from
- effective_to
- reviewed_at
- decision_at
- snapshot_at
- published_at
- expires_at

不要只依靠数据库 `updated_at` 推断业务时间。

## 5. 哪些字段需要锁定/审批

建议默认严格控制：

- 风险等级；
- 是否冲突；
- 风险结论；
- Claim Analysis；
- 风险会/领导/法务决策；
- 申请保护主题；
- 保护范围策略；
- 申请策略；
- 布局国家批准结果；
- 对外发布内容；
- 已确认的项目方案版本。

## 6. 哪些字段适合 AI

### 可自动生成草稿

- 翻译
- 一句话技术问题
- 一句话技术方案
- 一句话技术效果
- 实施例总结
- 保护点概要
- 技术模块候选
- 摘要

### 可辅助但不能成为最终责任值

- 相关性
- 风险等级
- 是否冲突
- 规避建议
- 分案续案风险判断
- 申请保护范围建议

### 禁止 AI 作为事实来源

- 申请号/公开号
- 申请日/优先权日
- 当前法律状态
- 正式会议决策
- 领导/法务批准

## 7. 从 ViewLocalField 提升为实体字段的阈值

出现以下信号即进入评审：

- 在 ≥4 类业务表/视图中重复出现；
- 是常用 filter/sort/group 维度；
- 被 API/MCP/tool 直接引用；
- 需要索引；
- 与其他实体关联；
- 有权限/审批/审计要求；
- 有时态；
- 有多值；
- 有责任人。

## 8. Alias Registry

建议维护：

```yaml
aliases:
  产品类型: ProductCategory
  产品品类: ProductCategory
  产品分类: ProductCategory

  所涉项目: ProjectLink
  相关项目: ProjectLink
  哪些项目相关: ProjectLink

  风险专利号: RiskPatentLink
  风险专利号（含同族）: RiskPatentLink

  出货地: ProjectRegionLink
  出货地区: ProjectRegionLink
```

所有 Excel 导入先走 alias normalization，再进入领域实体。

## 9. 数据质量等级

建议每个可疑字段可选记录：

- `confidence`: 0~1
- `provenance`: external_verified / internal_confirmed / ai_generated / inferred / legacy
- `review_status`: pending / confirmed / rejected / outdated

这样能明确“随手记”和“承担责任的信息”不是同一级数据。
