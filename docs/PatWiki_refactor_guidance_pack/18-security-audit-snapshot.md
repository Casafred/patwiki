# 18 — Security / Audit / Snapshot：权限、审计与发布设计

> 实施约束：参见 `21-implementation-contract.md`。本文件的 RBAC/ACL 是目标控制模型；当前 User/DatabaseMembership 仅为元数据，现有 API 尚未执行认证或服务端授权，不能被视为安全控制。

## 1. 数据责任等级

### L0 — 临时工作信息

例：

- 个人备注
- 临时标签
- 未完成检索式
- AI 草稿

规则：

- 可编辑；
- 普通历史；
- 可设置过期/清理策略。

### L1 — 业务事实

例：

- 项目阶段
- 出货地区
- 专利著录字段
- 研发确认的方案版本

规则：

- 来源明确；
- 保留变更历史；
- 关键事实需要责任人确认。

### L2 — 专业结论

例：

- 相关性
- 是否冲突
- 风险等级
- 风险结论
- 申请策略

规则：

- reviewer；
- confirmed_at；
- version；
- change_reason；
- 必要时 approval。

### L3 — 正式决策

例：

- 风险会结论
- 风险接受
- 领导批准
- 法务意见

规则：

- immutable append-only；
- 不能 delete/overwrite 普通处理；
- 撤销通过新 Decision 指向旧 Decision。

### L4 — 高敏信息

例：

- 未公开产品方案
- 样机图
- 未公开申请文本
- claim chart
- 规避方案
- 申请布局策略

规则：

- 加密；
- 记录级+字段级+附件级 ACL；
- 下载/导出审计；
- 可加水印。

### L5 — 对外发布

例：

- 产品线季度风险分享
- 专题分享
- 外部合作材料

规则：

- 只能从已审核 ReportSnapshot 发布；
- 不直接暴露实时数据库；
- 可脱敏、打水印、设置有效期。

## 2. RBAC + Scope

角色权限只是第一层，还需要 scope：

- department scope
- product category scope
- project scope
- case assignment scope

实施顺序：先统一请求身份、服务端授权函数、`database_id` 范围校验和审计上下文，再开放 L2-L5 写操作或跨设备访问。前端 localStorage 选择用户、UI 隐藏按钮或仅在模型中保存 role 都不构成权限控制。

例如：

- 分析师可看负责品类所有 RiskCase；
- 项目负责人只能看与自己项目相关风险；
- 法务只在被邀请/升级的高风险 Case 中获得完整详情；
- 对外 SharePackage 只包含显式选择字段。

## 3. AuditEvent

建议结构：

- id
- entity_type
- entity_id
- event_type
- field_key
- old_value
- new_value
- actor_id
- acting_role
- source
- source_view_id
- reason
- request_id
- ip/device context（按公司合规政策）
- created_at

审计事件应按追加方式写入；业务服务写入事件而不是由前端补报。`old_value/new_value` 仅保存必要字段，L4 内容在审计中应使用摘要/哈希或受限引用，避免审计日志本身扩大泄露面。

强审计事件：

- confirm
- approve
- reject
- unlock
- export
- publish
- download_sensitive_artifact
- change_risk_conclusion
- change_filing_strategy
- delete/restore

## 4. Approval

建议对象：

- ApprovalRequest
- ApprovalStep
- ApprovalDecision

适用：

- 高风险结论；
- 风险接受；
- 申请保护范围；
- 重大布局国家；
- 放弃申请/不缴费；
- 对外发布；
- 解锁已确认数据。

在 Phase 0-3，Approval 可先以“创建审批请求 + 只读决策记录 + 审计”的最小模型实现；可配置多级审批、委托、SLA 和通知编排延后。没有后端身份与权限时，审批不得用于真实的责任签发。

## 5. Lock Policy

建议：

- draft：责任人可编辑；
- confirmed：锁定主要结论字段；
- approved：只有审批流程能修改；
- published：内容冻结，只能产生新版本；
- archived：只读。

## 6. Artifact 安全

Artifact 本身应记录：

- sensitivity
- owner
- ACL
- content_hash
- malware_scan_status
- storage_provider
- encryption_key_ref
- retention_policy

ArtifactLink 不应该自动扩大权限。

如果用户有权看 RiskCase，但无权看某高度机密附件，详情页应显示“存在受限附件”，而不是泄露文件名/内容。

当前附件模型只绑定 Patent 和字段，且文件存于本地目录。迁移到 Artifact 前，旧附件仍按原路径和兼容 API 读取；新 Artifact 上传、下载、导出必须通过统一服务，执行路径校验、类型/大小检查、访问审计和 `database_id` 一致性校验。加密、恶意文件扫描和水印均是后续能力，不得在当前版本中作已实现宣称。

## 7. ReportSnapshot

发布表格/报告的正确模型：

1. 保存 View/Template；
2. 执行 query；
3. 解析到具体 source entity revision；
4. 生成 Snapshot；
5. reviewer 审核；
6. publish；
7. 冻结。

建议字段：

- id
- report_type
- reporting_period
- source_dataset
- source_revision
- generated_at
- generated_by
- reviewed_by
- reviewed_at
- published_at
- status
- sensitivity
- checksum

SnapshotItem 保存 source reference：

- source_entity_type
- source_entity_id
- source_revision
- rendered_values

这样历史季度报告可完全复现。

## 8. 对外脱敏规则

建议支持 Field Policy：

- remove
- mask
- aggregate
- pseudonymize
- allow

例如对外风险分享：

- 可公开：专利号、权利人、风险主题、处理方式摘要；
- 内部限制：具体 claim chart、研发规避细节、销量、内部意见、领导/法务详细讨论；
- 严禁自动带出：未公开申请策略、未公开方案图。

## 9. 数据保留

建议按类型设置 retention：

- Patent public facts：永久；
- RiskDecision/Assessment：长期/永久；
- Filing/Docket：按法律与公司政策；
- Published Snapshot：长期；
- AuditEvent：长期；
- 临时 AI 草稿：可定期清理；
- 临时 ViewLocalField：可设置失效和迁移策略。

## 10. 发布门禁

对外 SharePackage 或公开链接必须同时满足：

1. 源 Snapshot 已冻结并已审核；
2. 字段脱敏策略已在服务端执行并留下版本记录；
3. 调用者身份、授权范围、导出理由和下载事件可审计；
4. 附件与关联对象已按独立 ACL 复核；
5. 有效期、撤销和重新发布使用新版本的规则已测试。

在上述能力完成前，现有公开分享能力只能用于非敏感演示数据，不能承载 L4/L5 真实业务材料。
