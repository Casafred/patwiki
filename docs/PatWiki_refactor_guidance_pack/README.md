# PatWiki IP 业务数据体系重构指导包

> 目标：把现有 IP 部门的 Excel/表格式管理体系重构为可追溯、可版本化、可审计、可自动化、可被 AI 安全调用的数据平台。
>
> 文档状态：`implementation-guided / v1.1 / 2026-08-13`。本包描述的是目标架构与迁移契约；除明确标注“当前已具备”的能力外，均不得视为当前产品已上线功能。

本指导包配套的文本维护源：

- [`../PatWiki_refactor_data/`](../PatWiki_refactor_data/README.md)：31 类业务表/视图、357 次字段出现、140 个归一化字段概念的 CSV 台账，以及当前代码基线和迁移门禁。
- [`../PatWiki_IP业务数据体系重构指导报告.md`](../PatWiki_IP业务数据体系重构指导报告.md)：从业务职责、字段治理到 PatWiki 架构和迭代路线的完整说明。

## 核心原则

1. **事实只存一次，视图可以有很多。**
2. **关系本身有业务含义时，关系就是实体。**
3. **状态变化保留事件；结论变化保留版本；正式决策只追加不覆盖。**
4. **风险属于“专利 × 项目方案版本 × 地区 × 时间”的上下文，不属于 Patent 本体。**
5. **项目方案必须版本化，ProjectSolutionVersion 是风险、检索和保护共同的上下文。**
6. **产品线和品类允许交叉；技术分类允许多级、多标签和演进。**
7. **过程表可以消失，过程数据不能丢。**
8. **AI 输出必须可追溯、可过期、可人工确认；责任结论不能由 AI 代签。**
9. **报告是快照，不是第二份主数据。**
10. **外部同步必须幂等、可审计、可回放；MCP/Tools 必须最小权限。**

## 文件及建议阅读顺序

1. `15-domain-model-v2.md`：先统一“有哪些对象、它们是什么关系”。
2. `16-field-governance-registry.md`：再确定“每个字段由谁产生、怎么更新、能不能 AI、是否锁定”。
3. `17-risk-search-protection-workflows.md`：将检索组、分析组、保护组流程落到状态机和数据对象。
4. `18-security-audit-snapshot.md`：定义责任字段、审批、历史、附件权限与对外发布。
5. `19-ai-automation-mcp.md`：定义 AI、自动化、外部数据同步及 MCP/Tools 接口边界。
6. `20-migration-roadmap.md`：按 Phase 0~9 分批迁移，保留兼容视图，避免推倒重来。
7. `21-implementation-contract.md`：当前仓库基线、术语映射、迁移门禁、首批 PR 与完成定义。开始开发前必须先读。
8. `schema-v2-draft.sql`：概念性 DDL，用于技术评审和 ORM/Alembic 设计输入，不建议直接生产执行。

## 阅读与决策顺序

1. 先读 `21-implementation-contract.md`，确认当前单机 SQLite 原型的边界及 Phase 0A 门禁。
2. 再读 `15`、`16`，冻结聚合根、关系和字段语义。
3. 按业务组阅读 `17`、`18`、`19`，确认状态机、责任等级和自动化边界。
4. 以 `20` 的阶段验收和 `schema-v2-draft.sql` 的概念模型拆分实现 PR。

## 当前边界

- 当前仓库已具备 Patent/Family/Project、CustomField/ViewLocalField、导入批次、专利级历史、附件、自动化和本地 Tauri 包装。
- 当前仓库尚未具备 V2 的 RiskCase/SearchCase/ProtectionCase、通用 AuditEvent、Field Registry、版本化数据库迁移、认证与服务端强制授权。
- 因此 L2-L5 责任数据、对外发布和 MCP 写入都必须在完成认证、授权与审计强制后才可对真实业务开放。

## P0 建议（已校正）

第一批不要先做“大而全 UI”，也不要先创建大量 V2 表。应按以下顺序完成：

- SQLite 迁移账本、备份/恢复验证、外键运行时配置和迁移问题隔离。
- Field Registry / Alias Registry。
- ProductCategory 与交叉产品线关系。
- ProjectSolutionVersion / TechnicalFeature。
- RiskCase / RiskAssessmentVersion / RiskDecision / RiskWatch 的只读模型与风险 rollup 对账。
- SearchCase / QueryRun / SearchHit 的只读模型与历史检索表对账。
- 旧 Excel/旧页面只读兼容视图。

完成以上项并通过差异核对后，再切换写路径、统一 Artifact/Audit，并把月报、季度表、会议表、专题表转为 SavedView + ReportSnapshot。

## 维护规则

- 领域对象、字段定义和状态机的变更必须同时更新：相关 CSV 台账、指导报告 Markdown、对应指导包 Markdown、`schema-v2-draft.sql` 和本 README 的索引。
- `schema-v2-draft.sql` 只描述目标形态。实际代码必须遵循 `21-implementation-contract.md` 的迁移门禁，以 SQLAlchemy 模型、受版本控制的迁移和测试交付。
- 不允许通过新增同义 CustomField、逗号分隔 ID 或覆盖历史结论绕开治理设计；此类需求必须回到 Field Registry 评审。
