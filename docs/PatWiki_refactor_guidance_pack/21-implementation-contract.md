# 21 - V2 实施契约：从设计目标到可交付开发

> 状态：`approved-for-phase-0-planning`
> 更新：2026-08-17
> 本文是 V2 设计包的实现锚点。执行开发任务的 Agent 必须先阅读 `25-agent-development-protocol.md`；2026 年业务范围以 `23-2026-product-scope-and-business-rules.md` 为最高优先级；若长期目标模型与当年范围冲突，不得用长期能力阻塞专利信息中心。

## 0. 2026 范围硬约束

1. 当前产品先服务单人本地使用，保持 Tauri + FastAPI + SQLite 主路径；暂不设计云端、跨设备和复杂多人协作。
2. 产品入口和交付结果以每篇专利为中心，P0 是专利身份、事实、来源、关系、详情、查询、导入和导出。
3. 31 类真实台账都要被覆盖，但优先通过统一数据、保存视图和输出模板支持，不为每类台账复制一套独立业务系统。
4. Search、Risk、Protection 只先建设与专利锚定的高频信息和必要历史；完整 Case、Docket、期限、费用、审批和工作流引擎属于后续增强。
5. ProjectSolutionVersion 当前只做轻量方案快照和变更上下文，不作为普通专利数据录入、导入、分类、查询和导出的前置条件。
6. 外部 Excel 导入只能按字段策略更新著录等外部事实；人工分类、分析、风险、保护和内部关系不得被静默覆盖。
7. 同一申请链的申请号、申请公开号和授权公告号归入同一专利；不同国家/地区同族只关联不合并。每次导入都必须进入 Wiki 来源历史，即使没有修改当前值。
8. 导入内容中出现系统尚未认识的属性时，必须保留原始文件/行/列/值和来源观察，并允许查询、导出和后续映射；未知属性不能被静默丢弃，也不能未经治理进入正式统计。
9. 人工录入是数据治理的核心路径；任何录入功能必须支持低门槛草稿、字段级保存状态、空值不覆盖、Excel 粘贴/导入、批量维护、失败重试和来源追溯，具体交互以 `26-human-data-entry-interaction-spec.md` 为准。

### 0.1 开发者执行口径

实现导入、字段、详情、表格或导出功能前，Agent 必须阅读 `25-agent-development-protocol.md`、本契约、`23-2026-product-scope-and-business-rules.md`，并按任务阅读 `24-patent-information-hub-functional-spec.md` 和 `26-human-data-entry-interaction-spec.md`。遇到未注册列时，代码必须走以下分支：

- 行身份可识别、原始值可读取：保存为 `unmapped_retained`，在导入结果中显示“已保留，待治理”；
- 字段可映射到已注册属性：按字段覆盖策略处理，并保留 `FieldObservation`；
- 身份冲突、文件损坏、行解析失败：进入 `quarantined`，保留原始行并给出可重试原因；
- 用户确认新语义：创建或更新 Field Registry，再对历史观察执行可审计回填。

禁止用“未识别列直接忽略”“未知列自动写入 Patent.custom_fields”“只保留错误文本不保留原始值”来简化实现。任何实现取舍若违反此口径，必须先更新本文和 24 号规格。

### 0.2 文档到代码的执行机制

- 涉及导入、字段、专利详情、交互视图或导出的 PR，必须在描述中引用本契约、23 号业务规则或 24 号功能规格的具体章节，并说明对应的验收场景；没有对应文档依据的新增字段或状态不得直接进入正式模型。
- 实现前先确认输入属于 `mapped`、`candidate`、`unmapped_retained`、`deprecated` 或 `quarantined` 哪一种状态；状态、覆盖策略和审计信息必须在服务层统一决定，不能由单个页面自行定义。
- “系统目前不知道它的含义”不是删除、报错或擅自设计语义的理由。应先保留来源证据并进入待治理视图；只有业务确认后才更新 Field Registry，并通过可回放的映射/回填任务升级历史观察。
- 文档与现有代码冲突时，开发者必须在 PR 中列出冲突、影响和采用的兼容方案；若要改变业务规则，先更新权威文档和验收用例，再修改实现。禁止以“当前代码就是这样”为理由绕过本契约。
- 完成定义不仅是页面能显示，还必须能从测试或可重复的检查中证明：未知属性未丢失、真实异常可定位、原始值可反查、后续映射不覆盖历史观察、默认统计不会使用未经确认的未知属性。
- 人工录入还必须通过 26 号规格中的快速收录、部分保存、Excel 粘贴、批量编辑、失败恢复和来源追溯场景；没有这些闭环，不能把录入功能标记为完成。

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
| PatentIdentifier | 新实体 | 保存 application/publication/grant/external 标识及原始写法；主值投影到现有三个号码列。精确规范标识唯一，号码根和同族只能用于候选匹配。 |
| PatentFamily | 现有 `PatentFamily` / `patent_families` | 保留现有同族 ID；分案、续案、PCT/国家阶段关系新增 `FamilyRelation`。 |
| PatentDatabase | 现有 `PatentDatabase` | 是数据集合与工作台归属，不是当前应用的认证隔离边界。新 Case 必须带 `database_id` 作为拥有工作台。 |
| ProjectSolutionVersion | 新实体，当前降为轻量 P1 | 仅在判断确实依赖具体项目方案时引用；普通专利导入、分类和检索结果不强制绑定。需要多方案对比时使用明确关系，不使用 JSON 数组。 |
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
8. 导入必须分离来源观察值、候选规范值和当前采用值。相同值也写 `FieldObservation`；格式差异不覆盖，内容冲突待确认，身份冲突阻断整行；未注册属性进入 `unmapped_retained`，而非丢弃。

## 4. 迁移与发布门禁

## 4.0 当前 G0 实施切片：待治理属性确认闭环

当前代码已经完成来源证据保留，但 Agent 不得把“可以查询/导出”误判为“治理已完成”。下一批实现必须遵守以下固定数据路径：

1. `GET /import/unmapped` 读取 `FieldObservation`，默认只展示 `field_resolution=unmapped_retained`；传入 `status=all` 才读取完整观察集合。原始 `ImportSourceRow.raw_row` 和导入附件永不删除。`GET /import/unmapped/export` 默认使用 `status=all`，用于完整证据留档；治理队列需要导出时必须显式传 `status=unmapped_retained`。
2. 人工决策必须经过服务层接口，不能由前端直接修改 `Patent.custom_fields`。允许的动作是：`retain_source`、`ignore`、`map_existing`、`propose_field`。
3. `map_existing` 必须校验目标字段已在当前字段注册范围内；用户确认后才可回填专利当前值，并写入 `PatentHistory`，同时记录观察原始列、候选值、决定人、决定时间和映射版本。
4. 按来源列批量映射只能影响同一 `ImportBatch + source_field_name` 的观察；不能把一个来源列无提示地应用到其他批次或其他同名列。
5. `retain_source` 和 `ignore` 都不得删除观察记录；`ignore` 只改变默认治理展示，不得从原始证据和导出结果中消失。
6. 尚未识别专利身份的观察可以先治理字段语义，但不得伪造 `patent_id` 或写入正式专利记录。
7. 前端工作台至少要显示：来源文件、来源表、Sheet、行号、列名、原始值、当前值、候选值、差异类型、当前状态、最近决策；批量操作必须显示影响数量。请求失败时原观察必须仍在待处理队列并可重试。当前已实现待治理队列分页、逐观察决策历史和最近治理批次恢复。

8. 当前已实现接口的固定语义：`PATCH /import/observations/{id}` 的 `action` 只能是 `retain_source`、`ignore`、`map_existing`、`propose_field`；`apply_to_batch=true` 的范围严格为当前观察的 `import_batch_id + source_field_name`，不跨批次、不跨来源列。`map_existing` 必须提供已注册且可编辑的 `canonical_field_key`；`adopted_value=true` 才允许来源候选覆盖已有非空值，空当前值可以按确认结果补入。

9. 每个决策都追加 `GovernanceDecision`，不得更新或删除旧决策；查询 `/import/observations/{id}/decisions` 必须返回稳定 JSON。采用来源值造成实际变化时追加 `PatentHistory`，但任何正式字段回填都不能删除对应 `FieldObservation` 或原始附件。

10. 每个 PATCH 决策批次必须返回 `decision_batch_id`，并保存观察状态和专利字段变更前值。`GET /import/governance/batches` 提供批次历史；`POST /import/governance/batches/{decision_batch_id}/revert` 只能追加 `GovernanceReversal` 并恢复变更前状态，不能修改或删除原决策。

11. 恢复前必须验证：观察没有后续决策、观察状态仍等于该批次产生的状态、专利字段仍等于该批次最后采用值。任一条件不满足必须拒绝恢复并保留现值；禁止用“强制恢复”覆盖后续人工修改。恢复专利字段时追加 `PatentHistory(source=governance_revert)`。

本切片的完成定义：单条确认、同来源列批量确认、已有字段映射回填、来源专用字段保留、决策历史查询、完整证据导出、分页、可恢复批次和冲突保护全部可重复验证。统一专利身份、高频业务视图和工作文件模板在 G0-7 章节定义；只有 G0-1 至 G0-8 的代码、测试和文档门禁全部满足后，Agent 才能把 G0 整体标成完成。

### 4.0.1 G0-7：统一专利身份、高频视图与工作文件

本节是 G0-7 的执行合同，优先级高于任何“方便但会猜测合并”的实现。

#### A. PatentIdentifier

- `PatentIdentifier` 是独立索引实体；`Patent.application_number`、`publication_number`、`grant_number` 是兼容投影，不得把身份链塞入 `custom_fields`。
- 官方身份类型固定为 `application`、`publication`、`grant`；外部平台编号使用 `external` 并必须带来源系统。每条身份保存 `raw_value`、`raw_values`、`normalized_value`、法域、kind code、来源系统和来源时间。
- 规范化只用于匹配：Unicode NFKC、大写、去除空格和展示分隔符；原始写法永远保留。号码根只能提示候选，不能独立创建合并结论。
- 同一国家申请链中，申请号、公开号和授权号命中同一 Patent；不同国家/地区同族必须保持独立 Patent，只建立 `PatentFamily` 关联。
- 一行导入中的身份标识命中多个 Patent 时，整行进入 `quarantined`，不得先更新部分字段；原始文件、`ImportSourceRow`、`FieldObservation` 和行号必须保留。
- 身份冲突行必须持久化全部候选 Patent ID 和可读原因；详情页可以按 Patent ID 查询相关冲突，治理工作台按原批次和来源行继续处理，不得只保留临时错误文本。
- 创建、详情编辑、关系占位创建、导入确认都必须调用身份服务；新增或格式变化的号码只能通过服务写入身份索引。身份冲突必须返回候选 Patent ID 和可人工确认的原因。
- 详情使用 `GET /patents/{patent_id}/identifiers` 展示身份类型、原始写法、规范化值和来源，不得只显示三个投影列而隐藏身份冲突。

#### B. 高频保存视图

视图是同一 Patent 主表的查询/列投影，不是复制台账。每个数据库初始化以下稳定 `template_key`，允许用户继续调整列、筛选和分组：

`risk_meeting_statistics`、`company_filing_category`、`ip_risk_control`、`ip_application_control`、`product_category_master`、`daily_patent_accumulation`。

视图名称可以被用户改写，但 key 用于幂等初始化和后续 Agent 识别。任何新增高频表先作为保存视图评估，不得新建第二份专利事实表。

#### C. Excel/Word 工作文件

- `PatentExportTemplate` 保存数据库、可选视图、字段 key、筛选、排序、分组、输出格式和版本；模板不保存数据快照。
- 系统初始化的工作文件模板包括风险会统计 Excel、申请管控 Excel、专利检索分析 Word 和日常积累 CSV。用户模板通过 `/export/templates` CRUD 管理。
- `/export/excel`、`/export/csv`、`/export/word` 支持 `template_id`；Excel 必须附带“导出说明”页，列出字段 key、列标题、字段分组、系统/自定义来源、模板版本、视图、筛选和导出时间；Word 必须在开头写出模板版本、数据库/视图和字段来源说明。
- Word 只负责可编辑的数据工作文件装配，不在 G0-7 引入复杂报告编辑器、自动法律结论或不可追溯的摘要改写。

G0-7 完成定义：身份服务接管新增/编辑/导入/关系号码；格式差异可复用且原始写法可查；跨 Patent 身份冲突整行隔离；六个保存视图幂等可用；至少 Excel/Word 模板可按视图输出且字段血缘随文件交付；相关规则有自动化测试。

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
| 0B | Field Registry / Alias Registry | canonical field、alias、导入映射审计、未知属性保留、真正异常隔离 | 31 类来源表的每列都有 mapped、candidate、unmapped_retained、deprecated 或 quarantined 结论；未知列可查询、可导出、可后续映射。 |
| 0C | 专利身份与事实核心 | PatentIdentifier、号码规范化、ImportBatch 来源扩展、PatentImportEvent、FieldObservation、差异确认 | 公开/授权号码正确归并；同族不误合并；重复导入不重复建专利；每次来源观察进入 Wiki 历史。 |
| 0D | 专利详情与交互视图 | 24 号规格的十页详情、26 号规格的快速录入/就地编辑、组合筛选、排序、分组、列配置、批量操作、六个首批保存视图 | 任一专利可从一个入口查看和补充已录入信息；六类高频列表不需人工拼表；部分录入可保存并恢复。 |
| 0E | 工作文件输出 | Excel 导出模板、Word 报告数据装配、来源引用 | 选中专利或保存视图可稳定生成可复用工作文件，导出字段可追溯。 |
| 1 | 专利关联与分类 | Product/Project/TechnicalFeature/Competitor/Topic 关系、来源和确认状态 | 多值信息不再依赖逗号文本；关系可筛选、钻取和批量维护。 |
| 2 | 轻量风险跟踪 | 风险线索、初判、分析版本、决定、复核触发、专利/项目/地区关联 | 初判、分析确认和正式决定不互相覆盖；接受风险继续推进可长期跟踪。 |
| 3 | 检索与保护关联信息 | 检索来源/相关性/报告附件；挖掘/撰写/申请/保护状态 | 专利详情可调用高频过程信息；不要求先建完整 SearchCase 或 Docket 工作流。 |
| 4 | 轻量方案快照与通用证据 | ProjectSolutionVersion、ArtifactVersion、ArtifactLink、必要 AuditEvent | 依赖具体方案的风险可复原上下文；普通专利操作不被方案快照阻塞。 |

## 6. 测试与性能最低标准

- 迁移：空库、现有 `data/patwiki.db` 副本、重复执行、失败恢复四种场景。
- 约束：号码规范化、公开/授权归并、同族不合并、业务键、外键、状态机非法跳转、决策不可覆盖、AI 不可确认、导入幂等、未知属性保留和受保护字段不可覆盖。
- 血缘：任取一篇专利，能查到外部事实来源、最近导入批次、人工关系、关键判断、附件和修改历史；任取一条正式风险评估还能查到方案快照、法域、证据和前序版本。
- 兼容：现有 `/patents`、导入、附件、视图、AI 字段、`PatentHistory` 回归通过；新增 V2 不破坏既有客户数据。
- 性能：以可获得的真实本地数据验证常用专利列表、快速搜索、组合筛选、同族展开、详情聚合、批量导入和导出；暂无样本规模时先记录基线，不凭空承诺阈值。

## 7. 明确延后事项

- 企业 SSO、真实多用户认证、服务端 RBAC/ABAC、字段级加密、外部公开分享和生产 MCP 写入。
- 大规模全文/向量检索、跨设备实时协作、复杂工作流引擎和可配置审批编排。
- 完整 SearchCase 重放平台、全量 Docket/期限/费用/OfficeAction、ERP/PLM/代理系统集成和独立管理驾驶舱。
- 全量重命名 `Patent` 为 `PatentDocument`、一次性重建 UI、把所有旧 Excel 同时迁移。

这些不是放弃，而是为了保证第一轮数据治理先获得可靠的身份、版本、关系和来源基础。
