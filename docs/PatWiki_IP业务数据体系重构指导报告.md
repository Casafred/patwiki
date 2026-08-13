# PatWiki IP 业务数据体系重构指导报告

> 文本化维护版。由历史 Office 版本转换并经当前仓库架构复核；后续以本 Markdown 与 `PatWiki_refactor_guidance_pack/` 为准。

- 历史来源：2026-08-13 前的 Office 版本（可由 Git 历史追溯）
- 文本化日期：2026-08-13
- 当前状态：`implementation-guided`

## 本文的维护边界

本文负责解释业务决策、领域边界和开发优先级；字段和来源表的逐项事实以 [`PatWiki_refactor_data/`](PatWiki_refactor_data/README.md) 中的 CSV 为准；模型、迁移和上线门禁以 [`PatWiki_refactor_guidance_pack/21-implementation-contract.md`](PatWiki_refactor_guidance_pack/21-implementation-contract.md) 为准。

原始 Office 文件自 2026-08-13 起不再保留在工作树中，内容由本报告 Markdown 和 `PatWiki_refactor_data/` 内的 CSV 接管；需要追溯转换前表达时使用 Git 历史。后续修改不得只保留在 Office 副本中。

## 当前仓库基线与关键校正

当前 PatWiki 是本地优先的单机组合：Tauri 拉起本地 FastAPI，React/Vite 提供界面，SQLAlchemy 使用 SQLite 数据文件。已有 Patent/PatentFamily、PatentDatabase/PatentView、CustomField/ViewLocalField、PatentProjectLink、导入批次、专利级历史、附件、AI 任务和自动化规则。

这为 V2 提供了可复用基础，但以下能力尚未实现：版本化数据库迁移、通用 Field Registry、ProjectSolutionVersion、RiskCase/SearchCase/ProtectionCase、通用 AuditEvent、认证与服务端授权、通用 Artifact、Connector 和 MCP server。因此本文的 V2 设计是目标状态，不能被误解为当前功能清单。

开发的第一条校正原则是：**先完成迁移平台、备份恢复和字段治理，再创建新的业务聚合根。** 当前以 `create_all + 容错 ADD COLUMN` 演进 SQLite 的方式只能兼容简单加列，不能承担多表回填、外键、数据拆分、回滚和审计要求。

PatWiki IP业务数据体系
重构、治理与前瞻设计指导报告

面向检索组、分析组、保护组及跨部门风险决策协同

基于31类业务表/视图与 PatWiki 当前仓库结构梳理（2026-08-13）

## 一、执行摘要：真正要重构的不是表，而是数据事实

本次盘点覆盖 31 类业务表/视图，累计 357 次字段出现，归一化为约 140 个字段概念，其中 31 个字段在4张以上表中重复出现。重复并非问题本身，真正的问题是：同一个事实被多处手工维护、同义字段缺乏统一ID、关系被塞入文本、变化字段被覆盖、正式结论与临时记录混杂。

- 高频共用事实进入核心实体：项目、产品、专利、人员、技术模块等。
- 多对多信息进入带属性的关系实体：专利-项目、项目-技术特征、风险-专利、风险-方案版本、产品线-品类。
- 法律状态、风险等级、风险结论、项目阶段、规避状态等会变化的信息必须保留事件/版本历史。
- 月报、季报、年度统计、对外分享由保存视图生成并冻结为快照，不再维护独立副本。
- AI输出和人工责任结论必须分层，AI只能辅助风险分析和决策，不能代替责任人确认。
- ProjectSolutionVersion（项目方案版本）是把项目、检索、风险、保护、技术模块打通的关键中间层。
## 二、宏观业务模型：IP部门是三个互相耦合的控制回路

PatWiki 因此不应只有 Patent 一个业务中心。专利是关键锚点，但 SearchCase、RiskCase、ProtectionCase、ProjectSolutionVersion 也必须是一级聚合根。

## 三、31类表格应归入五类用途体系

## 四、字段设计要从“一列”升级为12维元数据

- 语义归属：属于哪个实体/关系/事件，而不是属于哪张表
- 数据性质：标识、事实、状态、判断、派生、引用、附件、快照
- 生产方式：外部自动采集、内部人工事实、AI加工、专业判断、跨部门反馈、正式决策
- 时间属性：不可变、稳定、事件驱动、周期刷新、临时有效、会过期
- 更新策略：never/on_event/scheduled/manual/recompute/confirm-and-lock
- 责任等级：随手记、工作记录、专业结论、正式决策、对外发布
- 审计策略：普通历史、来源审计、严格审计、审批、不可变追加
- 权限/敏感度：记录级、字段级、附件级；内部/机密/高度机密
- 数据验证：唯一、格式、枚举、分类树、条件必填、法域标准状态
- AI策略：禁止生成/可提取/可总结/仅建议/必须复核
- 自动化策略：API/Connector/MCP/规则引擎/人工采集
- 存储层级：核心列、关系表、事件表、CustomField、ViewLocalField、Snapshot
## 五、目标领域模型：多聚合根 + 统一关系层

## 六、产品线、产品品类和部门：必须支持交叉

业务现实中，商用/家用可能覆盖同一品类，不同产品线也可能共享产品类型。现有 PatWiki 的 ProductLine 只有单 department_id、Product 只有单 product_line_id，未来会迫使用户复制对象或滥用文本字段。

- Department ↔ ProductLine 建议N:M，或至少保留primary_department并增加协作/覆盖关系。
- 新增独立 ProductCategory，ProductLine ↔ ProductCategory 为N:M。
- Product/Variant引用主品类并可额外挂多个分类；Patent ↔ Product/ProductCategory 也应N:M。
- “产品类型/产品品类/产品分类”统一引用分类ID，不再自由文本。
- 每条产品/专利关系可带 role、relevance、source、confirmed_by，表达“覆盖、重点、参考、风险”等不同语义。
## 七、ProjectSolutionVersion：建议作为本轮P0新增实体

一旦方案版本存在，系统就能实现：新增模块/特征→自动匹配历史风险、竞对专利、既有我司申请→提示检索师/分析师/保护师复核。

## 八、风险域：风险不是Patent属性，而是上下文关系

同一专利对不同项目、不同方案版本、不同国家可能风险完全不同；专利授权/分案或项目方案变化后，结论也可能反转。因此风险必须从 Patent.has_risk/risk_level/risk_description 的全局单值中剥离。

- Patent.risk_level最多保留为rollup缓存，例如“所有开放RiskCase中的最高风险”等。
- Assessment记录assessment_input_hash，方案、权利要求或证据变化后，旧版本自动标记outdated。
- 高风险未规避可阻止项目通过Gate，除非产生显式RiskDecision接受风险。
- 风险会应生成正式Decision，而非只在备注里覆盖原结论。
## 九、检索域：把检索策略、结果和沟通统一成一条血缘链

- “检索结果数量”是QueryRun属性，不是检索式永久属性。
- “检索式找到的专利号”应拆为QueryRun↔SearchHit关系，不能用长文本。
- 历史风险、分案续案风险可自动联查RiskCase/PatentFamily，减少人工重复。
## 十、保护域：保护主题与申请案必须分层

- 一个保护主题可能拆多件专利、多国申请，所以“申请保护主题+申请号+布局国家+状态”不是一个对象。
- 布局国家后续有独立期限/代理/费用/状态，应拆成FilingCase或JurisdictionCase。
- ProtectionCase绑定ProjectSolutionVersion后，才能分析某模块的保护覆盖和空白。
## 十一、专利公共数据：原始事实、标准化、派生、AI与专业判断分层

法律状态采用 LegalStatusEvent + current_legal_status缓存。这样既能快速筛选，又能还原某次分析时的真实状态。

## 十二、技术分类与专题分享：大主题/细分支应该是字段，不是Sheet结构

- 建立TechnicalDomain→Module→Submodule→Feature分类，但允许多父节点、别名和版本。
- 大主题和细分支用topic_id/branch_id表示，Sheet只负责分组展示。
- Patent↔TechnicalModule关系带来源（人工、AI、IPC映射、检索）和确认状态。
- ProjectSolutionVersion使用同一套TechnicalFeature，使“产品方案—竞对风险—我司申请”在同一语义层连接。
## 十三、附件/证据：统一Artifact模型

ArtifactLink 通过 entity_type + entity_id + role 关联Patent、RiskCase、Assessment、ProjectSolutionVersion、SearchCase、ProtectionCase、Meeting，从任何对象一键追溯邮件、PPT、Word、样机、报告和专利原文。

## 十四、时间模型：回答“当时为什么这么判断”

## 十五、权限、锁定、审批与责任等级

- 记录级权限：按负责品类/项目/部门裁剪。
- 字段级权限：风险详细分析、申请策略、研发特征等限制角色。
- 动作级权限：编辑、确认、审批、解锁、导出、分享分别授权。
- 责任字段变更需change_reason；必要时创建ApprovalRequest。
## 十六、AI治理：AI是一种生产来源，不是万能字段类型

建议把现有 Patent.ai_fields 的溯源能力抽象为通用 AIProvenance：model、prompt_version、input_hash、output_schema、latency、cost、reviewer、review_status、superseded_by。

## 十七、自动化、Connector与MCP/Tools

- MCP不直接暴露任意SQL，只暴露语义化tool。
- 所有tool调用记录用户、权限上下文、输入引用、输出、写入记录和AI版本。
- 外部Connector保留cursor、last_success_at、source_version、retry_count。
- RiskWatch监听法律状态/同族变化，ProjectSolutionVersion监听研发方案变化；两者都能触发Assessment重评估草稿。
## 十八、月报/季报/年度/对外分享：统一为SavedView + Snapshot

1. SavedView只保存过滤、列、排序、分组、聚合和布局。
1. 生成报告时冻结引用到具体实体版本，形成ReportSnapshot。
1. Snapshot记录snapshot_at、source_revision、generator、reviewer、publish_status。
1. 发布后冻结；源数据后续变化不修改历史报告。
1. 更新报告时生成新Snapshot版本，而不是覆盖旧报告。
1. 对外发布增加脱敏、水印、导出审计和访问权限。
这与 PatWiki 当前 Master + View 路线兼容，但需要把 View 从只针对 Patent 扩展为跨领域 DataSet/View。

## 十九、CustomField与ViewLocalField：什么时候该实体化

建议 CustomFieldDefinition 新增：owner_entity_type、semantic_type、source_type、source_system、source_timestamp、volatility、update_policy、freshness_ttl、validation_schema、sensitivity、read_roles、write_roles、approval_policy、lock_policy、audit_policy、ai_policy、retention_policy、index_policy。

## 二十、PatWiki当前仓库：哪些方向正确，哪些需要调整

### 可复用的基础

- `PatentDatabase + PatentView` 已建立单源大表与小表视图模式。V2 应把它扩展到跨实体 Dataset/View，而不是继续把所有业务写入 Patent。
- `PatentProjectLink` 已证明“关系带业务属性”的方向可行。产品线-品类、方案-特征、风险-专利、风险-方案版本等关系应沿用同一模式。
- `CustomField`、公式和 Link/Lookup/Rollup 适合简单可配置属性；`ViewLocalField` 适合临时、局部、可过期的工作信息。
- `PatentHistory`、导入批次、附件和自动化日志可作为通用审计、Artifact、SyncRun 的兼容来源，但不能直接等同于目标能力。

### 必须先纠正的边界

| 现状 | 风险 | V2 决策 |
| --- | --- | --- |
| `Patent.has_risk/risk_level/risk_description` 是全局单值 | 同一专利在不同方案、法域和时间的风险相互覆盖 | 正式风险迁入 `RiskCase + RiskAssessmentVersion`；Patent 风险列仅保留 confirmed 评估的兼容 rollup。 |
| Project 只有基础属性 | 无法定位结论所依据的具体研发方案 | 引入 `ProjectSolutionVersion`、特征、地区、阶段事件和证据关系。 |
| ProductLine 单部门、Product 单产品线 | 无法表达交叉产品线和品类 | 增加 `ProductCategory` 与关系实体；不通过复制对象或文本字段绕过。 |
| User/DatabaseMembership 不强制认证 | 角色数据容易被误当作权限控制 | L2-L5 的确认、审批、导出、公开分享和 MCP 写入必须等待真实身份及服务端授权。 |
| 附件只绑定 Patent 字段和本地路径 | 无法跨实体追溯、版本化或独立控制访问 | 旧附件保留兼容读取；新附件逐步改为 `Artifact + ArtifactLink`。 |

完整逐项基线见 [`12-实施基线与迁移门禁.csv`](PatWiki_refactor_data/12-实施基线与迁移门禁.csv)。

## 二十一、推荐迭代路线：逐步替换，不推倒重来

### Phase 0A：迁移平台与安全门禁

先引入受版本控制的迁移账本、SQLite 备份恢复、运行时外键检查、迁移问题隔离和真实历史库副本回归。没有这层能力，不允许启动 V2 业务表的生产迁移。

### Phase 0B：字段与业务键冻结

为 31 类来源表的每一列明确 canonical field、别名、主存储位置、业务键范围、迁移状态和业务负责人。每列只能是 `mapped`、`deprecated` 或 `quarantined`；不允许“以后再处理”的隐性状态。

### Phase 1-2：先建立可引用的主数据和方案上下文

依次完成产品/品类交叉关系、技术分类、项目成员/地区/阶段事件和 `ProjectSolutionVersion`。所有新的检索、风险、保护草稿只能选择一个 primary solution version；多方案对比必须显式建关系，不能使用多选文本。

### Phase 3-6：以只读模型和双读核对切换核心域

风险、检索、保护、附件审计各自先完成 schema、服务、只读工作台和旧台账差异报告，再切写路径。每次写入切换都必须通过迁移回滚演练、导入幂等、旧 API 回归和业务键级差异核对。

### Phase 7-9：在可靠数据基础上做报表、同步和 AI

SavedView/ReportSnapshot、外部 Connector 和 MCP/AI 都是后续阶段。自动化和 AI 只能生成草稿、待办或 WatchEvent，不能确认专业结论、创建正式决策、改变申请策略或对外发布。

每阶段的交付物、门禁和 PR 切分见 [`20-migration-roadmap.md`](PatWiki_refactor_guidance_pack/20-migration-roadmap.md) 与 [`21-implementation-contract.md`](PatWiki_refactor_guidance_pack/21-implementation-contract.md)。

## 二十二、迁移方法：先打通引用，再消灭复制

1. 给旧表每行增加稳定source_row_id，保留原始来源。
1. 建立Field Alias Registry，把同义字段映射统一概念。
1. 优先迁移Department/Person/ProductCategory/Product/Project/PatentDocument。
1. 把“相关项目、风险专利号（含同族）、布局国家、技术模块”等多值文本拆关系。
1. 引入ProjectSolutionVersion；历史无法完全还原时标记provenance=legacy_inferred。
1. 按风险主题+项目/方案+专利族聚合RiskCase；历史会议/报告迁Decision/Artifact。
1. 按TC号迁移SearchCase；命中文献拆SearchHit；检索式拆Query/Run。
1. 按保护主题迁ProtectionCase；国家布局拆FilingCase。
1. 旧Excel先保留只读兼容视图；新模型生成结果核对一致后停止人工维护。
1. 最后删除重复字段和旧台账；全程可回滚。
## 二十三、值得提前采集的新字段

新增字段必须先进入 Field Registry，再决定其存储位置。首批高价值字段/关系如下：

- 方案版本：`version_no`、`effective_from/to`、`change_summary`、`change_reason`、`confirmed_by/at`；
- 技术特征关系：稳定 feature ID、来源、确认人、变更类型和重要度；
- 风险评估：法域、权利要求版本、输入哈希、证据引用、复核状态、重评估触发原因；
- 外部事实：原始值、标准化值、来源系统、来源时间、有效期和内容哈希；
- 决策与规避：参与人、依据、条件、复审时间、验证证据和 supersedes 关系；
- 数据质量：`provenance`、`confidence`、`review_status`、`migration_status` 和来源行定位。

不要以字段解决本应属于实体或关系的问题。若信息有独立生命周期、负责人、状态、附件、权限、审计或多对多关系，就应建实体/关系，而不是新增 `CustomField`。

## 二十四、字段交叉后可形成的新数据资产

- 方案版本 × 技术模块 × 风险专利 → 自动发现“新方案触发历史风险”。
- 技术模块 × 我司申请 × 竞对专利 → 保护空白、拥挤区、竞对强势区。
- 风险专利 × 法律状态事件 × Assessment → 哪类状态变化最常导致风险反转。
- SearchConcept × QueryRun × RelevanceReview → 哪些检索式对哪些技术模块最有效。
- ProtectionCase × SolutionVersion × 授权范围 → 反向评价挖掘和撰写质量。
- RiskDecision × Mitigation × 项目进度 → 风险处置对研发周期的真实影响。
- Competitor × ProductCategory × Country × TechnicalModule → 竞对技术路线与国家布局地图。
- Worklog × Case类型 × 复杂度 → 资源配置和产能预测。
## 二十五、严禁的反模式

- 用逗号文本、JSON ID 数组或多选字段保存多个专利、项目、国家、人员或技术特征；
- 用当前风险等级覆盖历史风险结论，或允许 AI/自动化直接确认结论；
- 在未完成认证和服务端授权时，声称已有字段级 ACL、审批安全或对外发布控制；
- 通过继续扩展 `_ensure_column_migration()` 并吞掉异常处理复杂迁移；
- 让新 Case 绕过 `database_id`、来源、责任人、时间和审计；
- 先重写所有 UI，再验证新读模型是否能复现旧台账；
- 只修改离线 Office 副本，不更新 Markdown/CSV 文本源。

## 二十六、验收指标

### 迁移质量

- 每个来源表记录行数、业务键、null rate、多值拆分数、未识别 alias、隔离项、附件链接、责任人和时间字段；
- 每次迁移有版本、校验和、备份 ID、运行结果和恢复验证；
- 新旧读模型按业务键生成差异报告，差异要么为零，要么有业务负责人接受的例外。

### 领域正确性

- 已确认的风险评估可回溯至方案版本、法域、专利/权利要求版本、证据、分析人、确认人、触发事件和前序版本；
- RiskDecision 只追加不覆盖；重新决策通过 supersedes 关系表达；
- 检索可保存查询版本、输入范围、运行时间、结果哈希和命中文献；
- 任何 Risk/Search/Protection 新写入都不破坏现有 Patent、导入、附件、视图、AI 字段和历史接口。

### 治理与安全

- 责任字段已登记来源、验证、更新、敏感度、审计和 AI 策略；
- 未完成认证、授权和审计的环境不开放 L2-L5 真实业务确认、外部分享或 MCP 写入；
- 自动化与 AI 输出可关闭、可重放、可判定过期，并能区分草稿与人工确认值。

## 二十七、建议新增到PatWiki仓库的指导文件

当前已新增并应持续维护：

- `PatWiki_refactor_guidance_pack/15-domain-model-v2.md`：领域对象、关系和兼容边界；
- `PatWiki_refactor_guidance_pack/16-field-governance-registry.md`：字段注册、别名、存储决策和门禁；
- `PatWiki_refactor_guidance_pack/17-risk-search-protection-workflows.md`：三组状态机、确认门槛和联动规则；
- `PatWiki_refactor_guidance_pack/18-security-audit-snapshot.md`：责任等级、审计、审批、发布门禁；
- `PatWiki_refactor_guidance_pack/19-ai-automation-mcp.md`：AI、Connector 和工具边界；
- `PatWiki_refactor_guidance_pack/20-migration-roadmap.md`：分阶段迁移与验收；
- `PatWiki_refactor_guidance_pack/21-implementation-contract.md`：当前架构基线、术语映射和首批 PR 完成定义；
- `PatWiki_refactor_data/`：CSV 治理数据集和实施基线。

## 二十八、最终设计原则

- 事实只存一次，视图可以有很多。
- 关系本身有业务含义时，关系就是实体。
- 状态变化保留事件，结论变化保留版本，决策只追加不覆盖。
- 风险属于具体方案上下文，而不是属于专利本身。
- 产品分类允许交叉，技术分类允许演进。
- 过程数据要沉淀，临时表可以消失。
- AI输出可追溯、可过期、可人工确认，责任结论不能由AI替代。
- 发布数据必须快照化，历史报告必须可复现。
- 自动化必须幂等、可审计、可回放；MCP必须最小权限。
- 先建立统一ID和数据血缘，再追求智能化。
## 附录A：PatWiki仓库对照基线

## 附录B：配套 CSV 数据集

历史表格已转换为 [`PatWiki_refactor_data/`](PatWiki_refactor_data/README.md) 的 13 份 CSV：使用说明、表格目录、357 条字段逐项盘点、140 个归一化字段字典、领域实体、关系模型、数据治理、旧表重构映射、仓库差距、迭代路线、字段元数据扩展、自动化与 MCP 建议，以及基于当前代码复核新增的实施基线与迁移门禁。

## 附录：原报告表格

### 表 1

| 总目标：把分散在大量Excel式表格中的字段、流程、风险结论、申请信息、知识库与附件，统一为可追溯、可版本化、可审计、可自动化、可被AI安全调用的数据资产，并直接指导 PatWiki 的下一阶段重构。 |
| --- |

### 表 2

| 核心架构结论：表格必须降级为视图。数据库中的“真相”应由 Entity（实体）、Relation（关系）、Event/Version（事件/版本）、Artifact（附件证据）和 Snapshot（发布快照）构成。 |
| --- |

### 表 3

| 控制回路 | 主链路 | 主要输入 | 核心处理 | 主要输出 | 失控后果 |
| --- | --- | --- | --- | --- | --- |
| 风险防御 | 检索→分析→领导/法务→研发 | 项目方案、竞对专利、法律状态 | 检索、claim分析、规避、决策、持续监控 | 风险结论、规避动作、决策、重评估 | 侵权、返工、延期 |
| 专利保护 | 保护→研发/产品→领导→代理所 | 创新点、技术模块、商业策略 | 挖掘、保护范围、撰写、布局、答复、维护 | 申请组合、国家布局、授权 | 保护空白/抢占 |
| 知识沉淀 | 三组共同 | 专利库、检索策略、分析、会议、附件 | 标准化、关联、专题化、复用 | 知识库、技术地图、经验资产 | 重复劳动/经验丢失 |

### 表 4

| 用途体系 | 本质 | 典型现有表 | 系统化目标 |
| --- | --- | --- | --- |
| 风险 | 责任结论+动态跟踪 | 风险会统计、平台风险总表、单项目风险表、分析结论 | RiskCase/Assessment/Decision/Watch工作台 |
| 布局 | 保护主题+申请生命周期 | 挖掘、品类申请、申请总表、单项目申请 | ProtectionCase/FilingCase/Docketing |
| 流程性 | 任务/工时/SLA/会议 | 个人事务、待办、项目进程、会议召开 | Task/Worklog/Meeting/StageEvent |
| 过程性 | 为结论服务的中间数据 | 检索策略、检索结果、相关性复核、沟通、特征比对 | 过程实体保留，临时视图可删除 |
| 分享阐释 | 某时间点重组表达 | 月报、季度分享、专题分享、会议精选 | SavedView + ReportSnapshot |

### 表 5

| 重要区别：过程性“表”可以消失，但过程数据不能消失。检索式、QueryRun、命中文献、相关性复核、沟通背景、证据出处都是未来复用和AI检索最有价值的数据资产。 |
| --- |

### 表 6

| 领域 | 建议实体 | 核心职责 |
| --- | --- | --- |
| 组织 | Department / Person / Role / Team | 人员、角色、组织层级、责任边界 |
| 产品 | ProductLine / ProductCategory / Product / ProductVariant | 交叉产品线/品类/型号 |
| 项目 | Project / ProjectMember / ProjectStageEvent | 项目生命周期、负责人、阶段 |
| 方案版本 | ProjectSolutionVersion / TechnicalFeature / InheritanceLink | 继承、变更、方案特征、有效期 |
| 技术分类 | TechnicalDomain / Module / Submodule / Feature | 技术主题/大主题细分支/模块树 |
| 专利公共数据 | PatentFamily / PatentDocument / PriorityClaim / LegalStatusEvent / Party | 同族、法域、权利要求、状态、申请人 |
| 检索 | SearchCase / Strategy / Query / QueryRun / SearchHit / RelevanceReview | 检索全过程 |
| 风险 | RiskCase / AssessmentVersion / ClaimAnalysis / Mitigation / Decision / Watch | 发现→分析→规避→决策→持续监控 |
| 保护 | ProtectionCase / FilingCase / OfficeAction / Docket / Fee | 挖掘→申请→答复→维护 |
| 协作 | Task / Worklog / Meeting / Communication | 个人事务、工时、会议、跨部门沟通 |
| 附件 | Artifact / ArtifactVersion / ArtifactLink | 邮件、PPT、Word、图片、表格、原文、链接 |
| 报告 | SavedView / ReportSnapshot / SharePackage | 月度/季度/年度/对外发布 |
| 治理/AI | AuditEvent / Approval / AIProvenance / AutomationRule / Connector | 审计、审批、AI、外部更新 |

### 表 7

| 为什么它是关键：风险和检索针对的是某个时间点的具体方案，不是抽象项目号。项目持续迭代、继承旧方案、局部规避，如果没有方案版本，旧风险结论就没有上下文。 |
| --- |

### 表 8

| 建议字段/关系 | 作用 |
| --- | --- |
| project_id + version_no | 项目内稳定版本 |
| effective_from/effective_to | 方案实际有效期 |
| stage | 当时项目阶段 |
| source_version_id / inherited_product | 继承来源 |
| change_summary / change_reason | 与上一版差异及原因 |
| SolutionFeatureLink | 结构/电子/算法等特征，可多选 |
| regions | 出货国家/地区，多值关系 |
| evidence_artifacts | 图纸、定义、样机、会议材料 |
| confirmed_by / confirmed_at | 研发/项目确认 |

### 表 9

| 层级 | 实体 | 内容 | 历史策略 |
| --- | --- | --- | --- |
| 风险事项 | RiskCase | 主题、发现原因、影响范围、负责人、总状态 | 持续存在 |
| 风险专利 | RiskPatentLink | PatentFamily/Document、法域、角色、监控优先级 | 可增删 |
| 评估版本 | RiskAssessmentVersion | 方案版本、权利要求版本、分析日期、等级、结论 | 只追加版本 |
| 逐项比对 | ClaimAnalysis/ClaimElement | claim拆解、待检特征、落入判断、证据 | 跟随评估版本 |
| 规避 | MitigationPlan/Action | 规避方案、采用状态、样机证据、验证 | 事件更新 |
| 正式决策 | RiskDecision | 会议结论、领导/法务意见、风险接受条件 | 不可覆盖 |
| 跟踪 | RiskWatch/WatchEvent | 授权、无效、分案、续案、权利人变化 | 外部事件触发 |

### 表 10

| 实体 | 包含 | 为什么重要 |
| --- | --- | --- |
| SearchCase | TC号、用途、项目/方案版本、地区、责任检索师 | 检索工作的聚合根 |
| SearchCommunication | 研发背景、方案描述、沟通人/时间、确认材料 | 解释“当时搜什么” |
| SearchConcept | 要素、同义词、分类号、申请人、技术模块 | 跨项目复用 |
| SearchQuery | 检索式、平台、数据库字段、筛选策略 | 可复制/优化 |
| QueryRun | 运行时间、数据源版本、命中数、结果hash | 可重跑、做差异 |
| SearchHit | SearchCase×PatentDocument | 避免复制专利著录字段 |
| RelevanceReview | 相关性、备注、复核人、对应方案版本 | 沉淀人工判断 |

### 表 11

| 层级 | 实体 | 主要字段 |
| --- | --- | --- |
| 创新/保护主题 | ProtectionCase / InventionTheme | 项目方案版本、技术模块、创新点、保护主题/范围策略、价值级别 |
| 布局策略 | FilingStrategy | 国家、申请类型、时间、预算、核心/外围/防御角色 |
| 具体申请 | FilingCase | 内部卷号、申请号、代理机构、承办人、程序状态 |
| 审查阶段 | OfficeAction/Response | 通知书、答复期限、答复稿、修改点 |
| 维护 | Docket/Fee/MaintenanceEvent | 年费、期限、缴费证据、放弃决策 |

### 表 12

| 层次 | 示例 | 规则 |
| --- | --- | --- |
| 原始外部事实 | 原始申请人、原始法律状态、原文权利要求 | 保留数据源、抓取时间、原始文本，不可AI覆盖 |
| 标准化事实 | 标准申请人、标准法域、统一法律状态 | 规则/人工标准化，可追溯原值 |
| 派生事实 | 预计失效日、同族代表、当前权利人 | 算法计算并记录规则版本 |
| AI加工 | 翻译、技术问题/方案/效果、实施例摘要 | AIProvenance+人工确认 |
| 业务判断 | 相关性、风险等级、是否冲突、保护价值 | 责任人确认+版本化 |

### 表 13

| 字段 | 建议 |
| --- | --- |
| artifact_type | email/ppt/patent_pdf/image/spreadsheet/word/external_link/sample_evidence/report |
| storage_uri/external_url | 本地加密存储或外链 |
| content_hash | 去重、完整性、版本判断 |
| version/parent_version_id | 文档版本链 |
| source/owner | 来源和责任人 |
| created_at/captured_at | 创建/采集时间 |
| sensitivity/ACL | 附件级权限 |
| extracted_text/index_status | 全文检索/AI索引 |

### 表 14

| 信息类型 | 时间/版本策略 | 例子 |
| --- | --- | --- |
| 基本事实 | 确认后稳定 | 申请号、项目号、优先权日 |
| 状态 | 事件表+current缓存 | 法律状态、项目阶段、跟踪状态 |
| 专业结论 | 版本对象，旧版只读 | 风险结论、相关性、claim chart |
| 决策 | 不可变事件 | 风险会、领导、法务意见 |
| AI输出 | 执行版本+outdated | 摘要、翻译、分类 |
| 外部数据 | source_timestamp+freshness | 竞对状态、同族、权利人 |
| 临时信息 | expires_at/retention | 个人随手记、临时标签 |
| 发布材料 | snapshot_at+frozen revision | 月报、季报、对外分享 |

### 表 15

| 判断规则：任何会被未来事件“推翻”的字段，都不应以覆盖式单值成为唯一历史。 |
| --- |

### 表 16

| 等级 | 典型信息 | 控制建议 |
| --- | --- | --- |
| L0 草稿 | 个人备注、临时标签、未完成检索式 | 个人/小组编辑，普通历史 |
| L1 事实 | 项目阶段、出货地、专利著录数据 | 来源明确，变更记录 |
| L2 专业结论 | 是否冲突、风险等级、分析结论、保护策略 | 签名确认、严格版本、必要审批 |
| L3 决策 | 风险接受、规避决定、申请策略批准 | 领导/法务权限，不可覆盖 |
| L4 高敏 | 未公开方案、样机、申请文本、内部策略 | 字段/附件级ACL、加密、导出审计 |
| L5 发布 | 季度分享、专题分享 | Snapshot发布、脱敏/水印/导出日志 |

### 表 17

| 内容 | AI角色 | 最终责任 | 控制 |
| --- | --- | --- | --- |
| 翻译 | 生成 | 可自动写草稿 | 原文版本+模型+术语表 |
| 技术问题/方案/效果 | 结构化总结 | 人工确认 | provenance+human_confirmed |
| 实施例/保护点摘要 | 总结 | 人工复核 | 允许多版本 |
| 技术模块分类 | 分类建议 | 人工确认后用于统计 | confidence+reviewer |
| 相关性 | 筛选建议 | 检索师复核 | 不能自动成为风险依据 |
| 风险等级/冲突 | 辅助分析 | 分析师 | 禁止AI直接签发 |
| 规避方案 | 建议 | 研发/分析师 | 禁止自动执行 |
| 领导/法务决策 | 材料整理 | 领导/法务 | AI不可替代 |

### 表 18

| 能力 | 输入 | 动作/输出 | 安全边界 |
| --- | --- | --- | --- |
| sync_patent_status | cursor/source | 新增LegalStatusEvent并更新缓存 | 幂等、可回放、记录来源 |
| discover_family_changes | family_id | 发现分案/续案/新同族 | 触发RiskWatch |
| get_project_ip_context | project/solution version | 风险、专利、申请、模块、历史结论 | 只读、按权限裁剪 |
| create_search_case | 方案版本/用途/地区 | 检索Case草稿 | 人工确认写入 |
| suggest_risk_links | 技术特征 | 候选风险/竞对专利 | 仅建议 |
| create_assessment_draft | risk_case+version | 分析草稿/待复核项 | 不写最终结论 |
| get_filing_coverage | 项目/模块 | 保护主题与国家布局 | 只读 |
| generate_monthly_snapshot | 月份/范围 | 月报快照草稿 | 审核后发布 |

### 表 19

| 场景 | 存储建议 |
| --- | --- |
| 单个临时视图出现、无跨表关联 | ViewLocalField |
| 多个视图复用的简单属性 | CustomField |
| 高频筛选/统计、跨多表反复出现 | 实体字段/索引字段 |
| 多对多关系 | 关系实体，禁止ID数组/逗号字符串 |
| 独立生命周期/负责人/状态/附件 | 独立实体 |
| 会产生正式历史版本 | Version/Event |
| AI输出且会过期 | AIProvenance+缓存字段 |
| 只为报告临时计算 | Snapshot派生字段 |

### 表 20

| 模块 | 判断 | 当前情况 | 建议 |
| --- | --- | --- | --- |
| PatentDatabase + PatentView | 正确基础 | 单源大表+小表视图、layout_type、ViewLocalField | 扩展为跨实体DataSet/View |
| PatentProjectLink | 正确基础 | 关系已带risk/relevance/role等属性 | 推广“关系实体化” |
| Patent.risk_* | 需要重构 | 专利本体存全局风险单值 | 降级为rollup缓存，正式风险迁RiskCase |
| Project | 明显不足 | 字段仅name/code/product/module/date/status | 新增成员、阶段事件、地区、SolutionVersion |
| ProductLine/Product | 与业务冲突 | 单department、单product_line | 加入ProductCategory和N:M |
| CustomField | 基础好 | AI/公式/Link/Lookup/Rollup均已支持 | 补治理元数据和owner_entity_type |
| PatentHistory | 范围过窄 | 只审计Patent字段 | 升级通用AuditEvent/Approval/Export |
| AutomationRule | 可复用 | trigger/condition/action+日志 | 用于状态同步、风险重评估、报表、提醒 |
| AI规范 | 方向正确 | 已要求模型/提示词/输入hash/人工覆盖 | 抽象成通用AIProvenance |

### 表 21

| 阶段 | 主题 | 核心动作 | 验收 |
| --- | --- | --- | --- |
| 0A | 迁移平台与基线冻结 | 迁移账本、SQLite 备份/恢复、外键运行时配置、字段与业务键冻结 | 空库/历史库升级可重复执行，失败可恢复 |
| 0B | 字段注册与导入隔离 | Field Registry、Alias Registry、来源字段映射、未识别字段隔离 | 31类来源表每列均有映射、弃用或隔离结论 |
| 1 | 主数据/分类 | 组织、产品线-品类、产品、项目、技术taxonomy | 核心对象不再自由文本 |
| 2 | 方案版本 | SolutionVersion、Feature、Inheritance | 检索/风险绑定具体版本 |
| 3 | 风险域 | RiskCase/Assessment/Decision/Mitigation/Watch | 旧风险表可自动生成 |
| 4 | 检索域 | SearchCase/Strategy/Run/Hit/Relevance | 策略可复用/重跑 |
| 5 | 保护域 | ProtectionCase/FilingCase/Docket | 挖掘到维护闭环 |
| 6 | 附件/审计 | ArtifactLink、Audit、最小审批模型 | 任一对象一键追溯材料；认证前不用于真实 L2-L5 签发 |
| 7 | 报表快照 | SavedView/ReportSnapshot | 取消重复台账 |
| 8 | 外部自动化 | 状态、同族、竞对增量同步 | 变化自动触发复核 |
| 9 | AI Tools/MCP | 受范围限制的只读工具、draft 写工具 | AI 输出可追溯；认证前不开放责任数据写入 |

### 表 22

| 建议字段 | 直接价值 |
| --- | --- |
| ProjectSolutionVersion.version_no/effective_at | 让风险结论有时间上下文 |
| TechnicalFeature标准ID | 项目、专利、风险、申请自动关联 |
| relation_source/confirmed_by | 区分AI建议与人工确认 |
| risk_trigger_type | 记录授权/分案/方案变更等重评原因 |
| assessment_input_hash | 准确判断旧结论是否过期 |
| legal_status_source_timestamp | 识别外部数据新鲜度 |
| claim_version/claim_source | 权利要求修改后定位分析依据 |
| decision_conditions/review_at | 风险接受可设条件与复审时间 |
| mitigation_verification_evidence | 规避是否落地有证据 |
| protection_gap_reason | 记录为何未布局/空白原因 |
| competitor_role/market_region | 竞对与国家/产品建立语义 |
| data_confidence/provenance | 区分事实、推断、AI、历史遗留 |

### 表 23

| 反模式 | 后果 |
| --- | --- |
| 所有新业务都塞Patent.custom_fields | 风险/项目/申请等独立生命周期消失 |
| 逗号分隔多个专利号/项目号/国家 | 无法维护引用完整性、筛选、增量更新 |
| 只保存当前风险结论 | 历史不可解释，旧结论无法判断过期 |
| AI字段和人工确认值混为一个值 | 责任不清，模型升级可能覆盖人工结论 |
| 月报/对外表维护独立副本 | 数据漂移 |
| 产品线强制单部门/产品单产品线 | 无法表达交叉业务 |
| 附件只存路径 | 无法版本、权限、全文索引、跨实体追溯 |
| MCP直接暴露数据库表/SQL | 权限和语义边界失控 |

### 表 24

| 维度 | 建议目标 |
| --- | --- |
| 重复维护 | 同一关键事实多表人工重复维护下降>80% |
| 风险追溯 | 一个页面看到专利→方案版本→claim分析→决策→规避证据→后续变化 |
| 结论版本 | 重评估不覆盖历史；可还原任意时点结论 |
| 项目联动 | 方案变化后自动列出需复核风险/专利 |
| 检索复用 | 可查询历史TC、策略、QueryRun和相关性结果 |
| 保护联动 | 项目/模块可见我司保护主题、国家布局和状态 |
| 附件追溯 | 专利/风险/项目/申请任一入口可找到相关材料 |
| 发布一致 | 月报/季报/分享从源数据生成快照 |
| 数据新鲜度 | 法律状态显示来源和更新时间，过期可识别 |
| AI治理 | 每个AI输出可追溯模型/提示词/输入，并区分草稿/人工确认 |

### 表 25

| 文件 | 内容 |
| --- | --- |
| 15-domain-model-v2.md | 统一领域模型、聚合根、关系、事件与版本 |
| 16-field-governance-registry.md | 字段字典、12维元数据、实体化规则 |
| 17-risk-search-protection-workflows.md | 三组工作流、状态机和重评估触发 |
| 18-security-audit-snapshot.md | 权限、锁定、审批、审计、发布快照 |
| 19-ai-automation-mcp.md | AI provenance、Connector、MCP/tools边界 |
| 20-migration-roadmap.md | 旧表迁移、兼容视图、阶段验收和回滚 |
| schema-v2-draft.sql | 核心新实体DDL草案，仅供技术评审 |

### 表 26

| 参考 | URL |
| --- | --- |
| 项目首页/README | https://github.com/Casafred/patwiki |
| 专利业务模型设计 | https://github.com/Casafred/patwiki/blob/main/docs/04-%E4%B8%93%E5%88%A9%E4%B8%9A%E5%8A%A1%E6%A8%A1%E5%9E%8B%E8%AE%BE%E8%AE%A1.md |
| AI开发规范 | https://github.com/Casafred/patwiki/blob/main/docs/05-AI%E5%BC%80%E5%8F%91%E8%A7%84%E8%8C%83.md |
| 改造启动方案 | https://github.com/Casafred/patwiki/blob/main/docs/14-%E6%94%B9%E9%80%A0%E5%90%AF%E5%8A%A8%E6%96%B9%E6%A1%88.md |
| Patent模型 | https://github.com/Casafred/patwiki/blob/main/backend/app/models/patent.py |
| Project模型 | https://github.com/Casafred/patwiki/blob/main/backend/app/models/project.py |
| Organization模型 | https://github.com/Casafred/patwiki/blob/main/backend/app/models/organization.py |
| Association模型 | https://github.com/Casafred/patwiki/blob/main/backend/app/models/association.py |
| CustomField模型 | https://github.com/Casafred/patwiki/blob/main/backend/app/models/field.py |
| View模型 | https://github.com/Casafred/patwiki/blob/main/backend/app/models/view.py |
| History模型 | https://github.com/Casafred/patwiki/blob/main/backend/app/models/history.py |
| Automation模型 | https://github.com/Casafred/patwiki/blob/main/backend/app/models/automation.py |
