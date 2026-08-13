# 21 - V2 实施契约：从设计目标到可交付开发

> 状态：`approved-for-phase-0-planning`
> 更新：2026-08-13
> 本文是 V2 设计包的实现锚点。若其他文档与本文的现状、术语或阶段门禁冲突，以本文为准；业务目标仍以 15-20 号文档为准。

## 1. 当前仓库的事实基线

| 主题 | 当前已具备 | 尚未具备 | V2 实施决定 |
|---|---|---|---|
| 运行形态 | React/Vite 前端、FastAPI/SQLAlchemy 后端、SQLite 本地文件、Tauri 启动本地后端 | 服务端多租户部署、并发协作控制 | V2 先按本地优先、单机可信边界设计；联网协作另立架构决策，不在本轮隐含实现。 |
| 数据迁移 | `Base.metadata.create_all()` 与 `_ensure_column_migration()` 的容错加列 | 版本化迁移、迁移校验、备份恢复门禁 | 所有 V2 写模型之前先引入受版本控制的迁移账本和 SQLite 备份/恢复验证；禁止继续以吞异常的 `ALTER TABLE` 承担复杂迁移。 |
| 专利与视图 | `Patent`、`PatentFamily`、`PatentDatabase`、`PatentView`、`PatentProjectLink` 已可用 | 跨实体 Dataset/View | 兼容期内物理表 `patents` 继续承担 `PatentDocument` 角色；不做表重命名。新领域读取通过适配层与现有 Patent API 共存。 |
| 字段能力 | `CustomField`、`ViewLocalField`、公式、Link/Lookup/Rollup | 跨实体 Field Registry、别名注册、责任/敏感度/锁定策略 | 先新建字段注册与别名注册；不得把 Risk/Search/Protection 的生命周期对象继续塞入 `Patent.custom_fields`。 |
| 历史与审计 | `PatentHistory` 记录专利字段变更；导入批次和自动化日志存在 | 通用审计、审批、导出审计、不可变决策 | 保留 `PatentHistory` 供兼容读取；新 V2 服务统一写 `AuditEvent`。 |
| 附件 | 附件仅绑定 `database_id + patent_id + attachment field` | 通用 Artifact、版本链、跨实体证据、附件 ACL | 不改旧附件路径；先通过迁移适配到 Artifact/ArtifactLink，再逐步切换上传入口。 |
| 身份与权限 | User、DatabaseMembership、角色元数据 | 身份认证、请求身份注入、后端授权强制 | 现有角色不是安全边界：API 仍公开。L2-L5 写入、外部分享、MCP 写工具均必须等认证和服务端授权后才可上线。 |
| AI 与自动化 | `AITask`、`AIFieldValue`、`AutomationRule/Log` | 通用 AI provenance、连接器游标、MCP 服务 | 复用现有模型做兼容读取；新写入走 `AIExecution`、`SyncRun` 与 draft-only 工具契约。 |

## 2. 术语与兼容映射

| V2 术语 | 当前物理实现/兼容方式 | 规则 |
|---|---|---|
| PatentDocument | 现有 `Patent` / `patents` | V2 新表外键在兼容期使用 `patent_id -> patents.id`；API 文案可以逐步改为“专利文献”，禁止在 Phase 0 重命名主表。 |
| PatentFamily | 现有 `PatentFamily` / `patent_families` | 保留现有同族 ID；分案、续案、PCT/国家阶段关系新增 `FamilyRelation`。 |
| PatentDatabase | 现有 `PatentDatabase` | 是数据集合与工作台归属，不是当前应用的认证隔离边界。新 Case 必须带 `database_id` 作为拥有工作台。 |
| ProjectSolutionVersion | 新实体 | 每个 SearchCase 的 P0 范围只能有一个 `primary_solution_version_id`；需要多方案对比时再引入明确的 scope link，不使用 JSON 数组。 |
| RiskAssessmentVersion | 新实体 | 一条评估必须指向一个 RiskCase、一个具体方案版本和一个法域；缺失上下文只能作为 legacy draft，不能确认。 |
| FieldDefinition | 新实体 | 不是直接替换 `CustomField`。先登记所有 canonical field，再按存储策略映射到系统列、关系表、事件/版本、CustomField 或 ViewLocalField。 |
| Artifact | 新实体 | 与旧 `Attachment` 并行。`ArtifactLink` 使用受控实体类型白名单，并由服务层校验目标实体存在。 |

## 3. 不可协商的数据约束

1. 任何 V2 Case（Search、Risk、Protection、ReportSnapshot）都有 `database_id`、`created_at`、`updated_at`、来源和责任人字段；`database_id` 用于查询归属，不可被误称为强安全隔离。
2. 风险评估的确认态必须包含 `solution_version_id`、`jurisdiction_code`、`input_hash`、`assessed_by`、`confirmed_by`、`confirmed_at` 与证据引用。缺项只能保存为草稿。
3. L3 决策只允许创建新记录或创建 superseding record；不得提供通用 `PUT`、`DELETE` 路由。服务层必须写审计事件，测试必须证明旧记录不可被覆盖。
4. 外部事实同时保存标准化值、`source_system`、`source_timestamp` 与可定位原始引用；AI 不能创建或覆盖外部事实。
5. 多值关系只允许关系表或独立子记录。专利号、项目号、国家、人员、技术特征不得以逗号文本、JSON ID 数组或 ViewLocalField 代替关系。
6. `Patent.has_risk`、`risk_level`、`risk_description` 在 V2 后只作为兼容聚合缓存。任何写入只能由已确认的 RiskAssessment 聚合任务产生，不能由详情页直接修改。
7. `ArtifactLink(entity_type, entity_id)` 是多态关系，数据库无法以普通外键保护所有目标；必须限制 `entity_type` 枚举，并在单一服务入口校验目标存在、权限和审计。

## 4. 迁移与发布门禁

### 4.1 Phase 0A：迁移平台先行

在创建任一 V2 业务表之前完成：

- 引入版本化迁移账本：迁移版本、校验和、执行时间、应用版本、操作者和结果可查。
- 每次 SQLite 迁移前生成带时间戳的备份，并执行 `PRAGMA integrity_check`、迁移、关键表行数校验与恢复演练。
- 对 SQLite 连接显式启用 `foreign_keys=ON`；不能把概念 DDL 中的一次 `PRAGMA` 当成应用运行时保证。
- 迁移失败必须停止启动并给出可操作错误，不能吞掉异常后继续运行。
- 建立 `migration_runs`、`migration_issues`、`legacy_row_links` 或等价审计模型，保留来源文件、工作表、行号、业务键、映射版本和隔离原因。

### 4.2 每个领域阶段的切换门禁

1. **写入前**：有 migration、ORM model、service、API schema、最小权限检查和事务边界。
2. **读模型前**：新查询可生成旧台账的关键列；差异清单按业务键可追踪。
3. **写路径切换前**：完成双读核对、迁移回滚演练、导入重跑幂等测试和历史数据抽样复核。
4. **旧字段降级前**：聚合缓存与正式数据的差异为零，且已有只读兼容页面和导出说明。
5. **发布前**：备份恢复通过、性能基线通过、API 合同测试通过、未解决迁移问题已隔离并被业务负责人接受。

## 5. 首批开发顺序与完成定义

| PR | 范围 | 必须产物 | 完成定义 |
|---|---|---|---|
| 0A | 迁移平台与备份 | 迁移账本、备份/恢复命令、连接 FK 配置 | 空库与含历史数据的升级均可重复执行；失败不污染原库。 |
| 0B | Field Registry / Alias Registry | canonical field、alias、导入映射审计、未识别字段隔离 | 31 类来源表的每列都有 canonical mapping、明确弃用或隔离结论。 |
| 1 | 主数据与技术分类 | ProductCategory、交叉关系、项目成员/地区/阶段事件、taxonomy edge/alias | 关键统计不再用名称文本 join；关系创建、去重和失效规则有测试。 |
| 2 | 方案版本 | ProjectSolutionVersion、Feature link、版本差异、证据链接 | 新建或确认的 Search/Risk/Protection 草稿必须选择版本；变更能生成待复核清单。 |
| 3 | Risk V2 只读后写入 | RiskCase、Assessment、Decision、Watch、旧风险 rollup | 可从 RiskCase 回溯方案、专利、证据、评估、决策；确认评估不覆盖历史。 |
| 4 | Search V2 | SearchCase、Concept、Query、Run、Hit、Review | 同一检索式可重跑并比较结果；命中不再以长文本保存。 |
| 5 | Protection V2 | ProtectionCase、FilingStrategy、FilingCase、Docket | 一个保护主题可展示多法域、多案件和期限来源。 |
| 6 | Artifact / Audit / Snapshot | ArtifactVersion、ArtifactLink、AuditEvent、ReportSnapshot | 跨实体追溯可用；在认证未完成前，L4/L5 只允许本机受控测试，不对外发布。 |

## 6. 测试与性能最低标准

- 迁移：空库、现有 `data/patwiki.db` 副本、重复执行、失败恢复四种场景。
- 约束：业务键、外键、状态机非法跳转、决策不可覆盖、AI 不可确认、导入幂等。
- 血缘：任取一条 RiskAssessment，能查到方案版本、专利/权利要求版本、证据、操作者、来源、前序版本和触发事件。
- 兼容：现有 `/patents`、导入、附件、视图、AI 字段、`PatentHistory` 回归通过；新增 V2 不破坏既有客户数据。
- 性能：以目标规模的脱敏样本验证常用列表、按风险/项目/法域筛选、同族展开、报告快照和导入；阈值由 Phase 0 采样后写入基准，而非凭空承诺。

## 7. 明确延后事项

- 企业 SSO、真实多用户认证、服务端 RBAC/ABAC、字段级加密、外部公开分享和生产 MCP 写入。
- 大规模全文/向量检索、跨设备实时协作、复杂工作流引擎和可配置审批编排。
- 全量重命名 `Patent` 为 `PatentDocument`、一次性重建 UI、把所有旧 Excel 同时迁移。

这些不是放弃，而是为了保证第一轮数据治理先获得可靠的身份、版本、关系和来源基础。
