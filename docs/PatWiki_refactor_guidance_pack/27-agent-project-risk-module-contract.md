# 27 - Agent Contract: Project Solution Context and Risk Tracking

> 状态：`implemented-lightweight-slice`
> 更新：2026-08-19
> 本文是项目方案版本和风险跟踪模块的 Agent 执行契约。实现前必须先阅读：
> `25-agent-development-protocol.md`、`21-implementation-contract.md`、
> `23-2026-product-scope-and-business-rules.md`、`24-patent-information-hub-functional-spec.md`、
> `26-human-data-entry-interaction-spec.md`。

## 1. 当前边界

本模块服务于单人本地专利信息中心，只保存围绕专利的项目方案上下文和风险历史。它不是研发项目管理、法务审批、Docket、费用、多人权限或 Gate 自动阻断系统。

本模块已经实现：

- 项目方案版本、变化特征、适用国家/地区、来源描述和确认状态；
- 风险案例、风险专利关联、风险方案版本关联和风险地区；
- 初步判断、分析确认、讨论/领导结论的追加式评估版本；
- 接受风险、要求规避、关闭、持续关注等轻量结论；
- 由变化、出货地或其他原因触发的持续复核记录；
- 专利详情页风险分区中的方案版本和风险案例录入、追加评估、复核。

本模块当前没有实现：

- 通用 `Artifact` / `ArtifactVersion` / `ArtifactLink`；来源先用 `source_type`、`source_description` 和 `evidence_summary` 保存；
- 研发、法务、代理机构账号、通知、审批编排或外部系统同步；
- 自动改变项目 Gate、自动产生法务赔偿预算或自动签发法律结论；
- SearchCase、ProtectionCase、ClaimElementAnalysis 的完整工作流。

Agent 不得把未实现项伪装成已实现字段，也不得为填补缺口把它们塞入 `Patent.custom_fields`。

## 2. 领域对象和存储位置

| 对象 | 物理表 | 关键规则 |
|---|---|---|
| 项目方案版本 | `project_solution_versions` | 同一项目的 `version_no` 唯一；版本确认后不可原地修改；后续变化必须新建版本 |
| 方案变化点 | `project_solution_changes` | 每条变化点独立保存，不能只拼成不可检索的备注 |
| 方案地区 | `project_solution_regions` | 多值关系表；不能在正式字段中保存逗号文本 |
| 风险案例 | `risk_cases` | 风险生命周期和当前聚合投影；必须属于一个 `database_id` |
| 风险专利关系 | `risk_patent_links` | 一项风险可关联多篇 Patent；同一案例/专利不能重复关联 |
| 风险方案关系 | `risk_solution_links` | 一项风险可以关联多个方案，但每个正式评估只能指定一个方案版本 |
| 风险地区 | `risk_case_regions` | 多值关系表；正式评估另有单一 `jurisdiction_code` |
| 风险评估版本 | `risk_assessment_versions` | 追加式；不提供编辑或删除正式评估的接口 |
| 风险持续复核 | `risk_review_events` | 追加式；出货地、保护范围、结构、前案、法律状态或同族变化都可触发 |

## 3. 方案版本写入规则

### 3.1 创建

调用 `POST /projects/{project_id}/solution-versions`。最少需要：

- `database_id`
- `name`
- `created_by`（本地单人场景可使用 `local-user`）

建议同时填写：`project_stage`（当前选项 TR1/TR2/TR3/TR4/TR5）、`source_type`、`source_description`、`change_summary`、`changes[]`、`regions[]`。

`version_no` 可以不传，服务端按该项目已有版本生成 `v1`、`v2`；如果传入，服务端校验项目内唯一性。未知的来源类型、阶段或地区代码可以保存为人工输入，不得因枚举暂未收录而丢失。

### 3.2 确认和修订

- 草稿可以用 `PUT /solution-versions/{id}` 补充；
- `POST /solution-versions/{id}/confirm` 将版本标记为 `confirmed`，记录 `confirmed_by`、`confirmed_at`；
- 已确认版本不能再用 PUT 修改；
- 同一项目确认新版本时，旧确认版本变为 `superseded`，旧版本内容和时间线保留；
- 不能通过删除旧版本“修订”历史。

## 4. 风险案例写入规则

调用 `POST /risk-cases` 创建案例。案例必须至少关联一篇专利；服务端必须校验：

- 每篇关联专利的 `database_id` 与案例一致；
- 关联的 `ProjectSolutionVersion.database_id` 与案例一致；
- 不能因专利号、标题或同族关系猜测关联对象；
- 风险案例的 `trigger_reason` 不得省略；
- `current_*` 字段是服务端聚合投影，不是用户直接填写的正式结论。

允许的轻量案例状态由服务层从正式评估决策聚合：`open`、`mitigation_required`、`accepted`、`closed`；草稿评估不会覆盖当前案例状态。

## 5. 风险评估版本门禁

调用 `POST /risk-cases/{id}/assessments`。每次调用都创建新的 `version_no`，不能更新或删除旧版本。

### 5.1 草稿

`decision=pending` 时允许保存不完整草稿。草稿必须仍保存录入人、时间、方案（若已知）、法域（若已知）和输入内容，不能对外显示为正式决定，也不能更新 `RiskCase.current_*`。

### 5.2 正式结论

`decision` 不是 `pending` 时，服务层必须拒绝缺少以下任一项的请求：

- `solution_version_id`：必须是当前风险案例已关联的方案版本；
- `jurisdiction_code`：例如 `US`；
- `assessed_by`：检索师/分析师等实际分析人；
- `confirmed_by`：确认人；
- `decision_at`：决定时间；当前 UI 可以不要求用户手填，服务层自动填当前时间，但 API 测试必须证明最终有值；
- `risk_level`、`gate_impact`、`decision_basis`；
- `input_hash`：由服务端依据风险案例、方案、法域和判断文本计算，Agent 不得接受客户端伪造的 hash。

建议记录：`preliminary_assessment`、`analysis_confirmation`、`discussion_conclusion`、`leadership_confirmation`、`mitigation_summary`、`evidence_summary`、`reviewed_by`、`decided_by`。

风险结论不自动阻断项目 Gate。`gate_impact` 只记录 `unknown`、`none`、`review_required`、`hold`、`continue_with_risk` 等工作判断，实际 Gate 仍由业务会议决定。

### 5.3 兼容投影

`Patent.has_risk`、`Patent.risk_level`、`Patent.risk_description` 只为既有高频视图和旧导出保留。当前阶段旧投影只读：

- `PatentService.update_patent` 拒绝直接写入；
- `PATCH /patents/{id}/field/{key}` 拒绝直接写入；
- 详情页不再编辑这三个字段；
- 外部导入保留对应 `FieldObservation`，但不覆盖或初始化 Patent 投影。

后续如果要自动刷新兼容投影，必须新增“从已确认评估聚合”的服务、审计和测试；任何 Agent 不得在普通编辑路径中偷偷补写。

## 6. 复核规则

调用 `POST /risk-cases/{id}/reviews`，每次追加 `RiskReviewEvent`。至少需要：

- `trigger_type`，如 `shipment_region_changed`、`claim_scope_changed`、`solution_changed`、`new_prior_art`、`legal_status_changed`、`manual_review`；
- `review_outcome`；
- `reviewed_by`。

复核可以更新案例的 `next_review_condition` / `next_review_at`，但不能删除旧复核，也不能自动修改上一版评估。复核如果产生新判断，必须另建新的评估版本。

## 7. 前端录入要求

风险详情分区必须满足：

- 先显示已有方案版本和风险案例，再显示兼容风险投影；
- 新增方案版本允许只填名称、阶段和一句变化描述后保存，其他信息可以补录；
- 国家/地区输入支持逗号、分号和换行拆分，但提交后必须进入关系表；
- 正式评估表单必须明确区分“待确认草稿”和正式结论；
- 正式结论显示方案版本、法域、分析人、确认人、决定人、结论依据和 Gate 影响；
- 失败时保留表单内容并显示可重试错误；
- 旧风险字段必须标明“兼容投影”，不能让用户误以为它是新的正式风险来源；
- 任何 AI 生成内容只能作为草稿，不能触发 `/assessments` 的正式决定。

## 8. 测试门禁

至少覆盖：

1. 方案版本自动编号、变化点和地区关系保存；
2. 已确认方案不能 PUT 修改；
3. 新版本确认后旧版本变为 `superseded`，旧内容仍可读取；
4. 跨数据库专利/方案关联被拒绝；
5. 风险案例必须至少关联一篇专利；
6. 正式评估缺少方案、法域、分析人或确认人时被拒绝；
7. 草稿评估不覆盖案例当前状态；
8. 多版评估按版本追加，旧版本仍可读取；
9. 复核事件追加且不覆盖旧记录；
10. 旧风险投影不能被详情、单元格、批量或外部导入直接写入；
11. 前端 lint、TypeScript、Vite build 和后端全量测试通过。

## 9. 后续扩展入口

下一阶段接入附件时，应新增 `Artifact` / `ArtifactVersion` / `ArtifactLink`，并把会议纪要、邮件、研发描述和检索报告通过受控关系链接到方案、风险案例或评估版本。不得在本模块增加 `attachment_path` 逗号文本或把附件内容直接塞进 JSON。
