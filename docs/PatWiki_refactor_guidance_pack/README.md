# PatWiki IP 业务数据体系重构指导包

> 目标：把现有 IP 部门的 Excel/表格式管理体系重构为可追溯、可版本化、可审计、可自动化、可被 AI 安全调用的数据平台。

本指导包配套：

- `PatWiki_IP数据模型与字段治理统计.xlsx`：31 类业务表/视图、357 次字段出现、140 个归一化字段概念的逐项统计。
- `PatWiki_IP业务数据体系重构指导报告.docx`：从业务职责、字段治理到 PatWiki 架构和迭代路线的完整说明。

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
7. `schema-v2-draft.sql`：概念性 DDL，用于技术评审，不建议直接生产执行。

## P0 建议

第一批不要先做“大而全 UI”，而应先完成：

- Field Registry / Alias Registry。
- ProductCategory 与交叉产品线关系。
- ProjectSolutionVersion / TechnicalFeature。
- RiskCase / RiskAssessmentVersion / RiskDecision / RiskWatch。
- SearchCase / QueryRun / SearchHit。
- Artifact / ArtifactLink。
- 通用 AuditEvent。
- 旧 Excel/旧页面只读兼容视图。

完成这些之后，月报、季度表、会议表、专题表可以自然转为 SavedView + ReportSnapshot。
