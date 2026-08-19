# PatWiki 开发进度跟踪表

> **规则**：每次代码更新完成后，必须同步更新本文件的状态列和实际完成日期。
> 状态值：`未开始` / `进行中` / `已完成` / `已阻塞`
> 更新时把对应行的"状态"改为已完成并填入"实际完成日期"，同时在底部"变更记录"追加一行。

最近更新：2026-08-19（完成 G0-7c 高频业务视图字段自定义闭环；G0-7b 工作文件下载、G0-7a 身份链追溯和 G0-8 治理恢复保持已完成）

---

## 一、当前迭代（P0 - 必须先做完）

### 1.1 第一阶段（已完成）

| ID | 任务 | 优先级 | 状态 | 计划完成 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|---------|------|
| P0-0 | 修复 GitHub Action 编码报错 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | CI | generate_icon.py emoji + PYTHONUTF8 |
| P0-1 | 专利详情页（查看+编辑+AI字段展示） | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 前端 | 6 个 Tab：基础著录/技术/风险/AI/自定义/关联关系 |
| P0-2 | 设置页（LLM API key 配置）+ 后端配置接口 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 全栈 | GET/PUT /settings + /settings/test-llm，配置持久化到 settings.json |
| P0-3 | AI 批量处理入口 + 任务进度页 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 全栈 | 列表页批量AI按钮 + AITaskMonitor 页面 + GET /ai/tasks + DELETE /ai/tasks/{id} |
| P0-4 | 修 PatentListPage 装饰性按钮 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 前端 | 全选/批量编辑/批量打标签/AI批量/行点击进详情/排序/分类筛选全部接入 |
| P0-5 | Tauri 桌面应用打包构建 | 高 | 已完成 | 2026-07-19 | 2026-08-08 | CI/桌面端 | scripts/build_windows.ps1 已统一图标、PyInstaller、前端和 Tauri 构建；固定 Tauri CLI 2.11.4，配置同时产出 MSI/NSIS；本地 Windows 已实际生成并校验两类安装包 |
| P0-6 | 多维表格核心（字段系统+动态列+内联编辑+筛选） | 高 | 已完成 | 2026-07-20 | 2026-07-20 | 全栈 | 字段元数据API/单元格PATCH/自定义字段筛选排序；前端动态列渲染/列宽拖拽/列头菜单/内联编辑/高级筛选面板/字段显隐配置/新建自定义字段 |
| P0-7 | 修复打包后端启动报错 + 端口冲突排查 | 高 | 已完成 | 2026-07-20 | 2026-07-20 | 全栈 | patwiki_backend.spec 补充 app.api.fields/app.services.field_registry 等 hidden imports；run.py 改为直接传入 app 对象，遇导入错误打印真实 traceback 而非 uvicorn 的 "Could not import module" |

### 1.2 第二阶段（库模型 + Wiki 式增量导入）

| ID | 任务 | 优先级 | 状态 | 计划完成 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|---------|------|
| P0-8 | 拆分 models 目录 + 新增 PatentDatabase 模型 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 后端 | 按 03-项目结构与代码规范.md 拆分为 base/enums/association/organization/project/tag/field/database/patent/ai/importing 11 个子模块；新增 PatentDatabase 表，Patent 增加 database_id 外键 |
| P0-9 | 扩展 patent_project 关联表为多维属性 | 中 | 已完成 | 2026-07-19 | 2026-07-19 | 后端 | PatentProjectLink 替代 Table：relation_type/risk_level/document_role/relevance_score/importance/assigned_to_id |
| P0-10 | 改造 import_service 为 Wiki 式增量合并 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 后端 | 新增 merge_service/relation_service；已知字段按覆盖策略增量合并；未知列保留为来源观察，不自动创建 CustomField；同族/引用号解析入库；confirm_import 接入 database_id 与关系入库统计 |
| P0-11 | 新增 database_service + /databases API | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 后端 | 库 CRUD + 归档 + refresh-count；init_data 创建"默认数据库"；schemas/schemas.py 新增 PatentDatabase 系列 schema；patwiki_backend.spec 补全 hiddenimports |
| P0-12 | 前端 ImportModal + 库切换器改造 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 前端 | 导入首步 chooseDatabase（选/建库）；未匹配列显示"新建字段"徽章+顶栏提示；Sidebar 顶部库切换器+新建库；PatentListPage 查询带 database_id；store 新增 databases/currentDatabaseId；types 新增 PatentDatabase 与 ImportPreview/ImportResult 字段扩展 |

### 1.3 飞书基础架构改造

| ID | 任务 | 优先级 | 状态 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|------|
| P0-13 | 部门总表 + 小表视图后端基础 | 高 | 已完成 | 2026-07-20 | 后端 | 主表/视图模型、视图本地字段、字段来源追溯 |
| P0-14 | 视图工作区基础闭环 | 高 | 已完成 | 2026-08-07 | 全栈 | 视图 API/状态/切换器；layout_type 与多维视图配置契约；列表按视图加载 |
| P0-15 | 看板视图基础闭环 | 高 | 已完成 | 2026-08-08 | 全栈 | 看板分组数据 API、卡片投影、跨列拖拽更新共享/自定义字段、视图内卡片字段配置 |
| P0-16 | 前端 ESLint 历史债务清理 | 高 | 已完成 | 2026-08-08 | 前端 | 原阶段已完成；2026-08-16 导入治理变更后重新出现 10 errors/2 warnings，见 G0-4 |

## 二、下一迭代（P1 - 管理功能）

| ID | 任务 | 优先级 | 状态 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|------|
| P1-1 | 产品管理页（CRUD） | 中 | 已完成 | 2026-08-08 | 管理台 | 产品、状态、产品线、负责人和专利数 |
| P1-2 | 项目管理页（CRUD） | 中 | 已完成 | 2026-08-08 | 管理台 | 项目、产品归属、状态和周期 |
| P1-3 | 标签 + 标签组管理页 | 中 | 已完成 | 2026-08-08 | 管理台 | 标签/标签组 CRUD、颜色和关联维护 |
| P1-4 | 自定义字段管理页 | 中 | 已完成 | 2026-08-08 | 管理台 | 复用既有字段管理页，管理台提供统一入口 |
| P1-5 | 部门/人员管理页 | 中 | 已完成 | 2026-08-08 | 管理台 | 部门/人员 CRUD、归属和启停状态 |
| P1-6 | 后端补齐元数据 CRUD（update/delete） | 中 | 已完成 | 2026-08-08 | 后端 | 部门/人员/标签组/产品线完整 CRUD |
| P1-7 | 修 ImportModal 产品/项目下拉填充 | 中 | 已完成 | 2026-08-08 | 前端 | 从 store 读取并按产品过滤项目 |
| P1-8 | 修后端 bulk-update 入参模型 | 中 | 已完成 | 2026-08-08 | 后端 | 封装为 BulkUpdateRequest |
| P1-9 | 清理 import_service 死代码 | 低 | 已完成 | 2026-08-09 | 后端 | 删除未调用的 preview/process/batch 辅助链路，保留现行导入 API 依赖的方法 |

## 三点五、M1 - 公式字段与数据导出

| ID | 任务 | 优先级 | 状态 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|------|
| M1-1 | 公式字段引擎 | 高 | 已完成 | 2026-08-10 | 全栈 | 安全 AST 求值、函数白名单、依赖图/循环检测、增量与全量重算、公式字段管理和只读表格展示 |
| M1-2 | 数据导出 | 高 | 已完成 | 2026-08-10 | 全栈 | Excel/CSV、UTF-8 BOM、当前库/当前视图筛选、字段选择、Excel 分组拆分 Sheet；旧 GET /export 保持兼容 |

## 三、第二阶段（M3 - 关联字段体系）

| ID | 任务 | 优先级 | 状态 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|------|
| M3 | Link / Lookup / Rollup 通用关联字段 | 高 | 已完成 | 2026-08-09 | 全栈 | CrossTableLink、字段配置、Link CRUD、目标搜索、批量解析 API 及表格展示/编辑；3 项服务/API 回归测试通过并已推送 main |

## 三点六、M4 - 表单视图与甘特视图

| ID | 任务 | 优先级 | 状态 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|------|
| M4-1 | 表单视图 | 高 | 已完成 | 2026-08-10 | 全栈 | 表单配置校验、分区/条件显示、字段类型转换、必填校验、新增/编辑专利、分享链接和公开提交；前端提供两列/单列录入界面与公开表单页 |
| M4-2 | 甘特视图 | 高 | 已完成 | 2026-08-10 | 全栈 | 甘特配置校验、时间线数据、分组、缩放、日期拖拽写回和字段历史追溯；前端支持开始/结束/标题字段选择、日/周/月/季/年缩放 |

## 三点七、M5 - 自动化、附件与可配置仪表盘

| ID | 任务 | 优先级 | 状态 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|------|
| M5-1 | 自动化规则与执行引擎 | 高 | 已完成 | 2026-08-10 | 全栈 | 规则 CRUD、启停/优先级、字段变更/创建/导入/手动/定时触发；条件匹配、字段设置、项目关联、标签、通知日志、递归保护；后端生命周期每分钟轮询定时规则，前端提供规则管理和执行日志 |
| M5-2 | 附件字段 | 高 | 已完成 | 2026-08-10 | 全栈 | 支持 PDF/图片/Word/Excel，50MB 限制、UUID 存储名、下载/预览/删除、元数据与专利字段同步；表格附件单元格接入，补充路径校验和文件响应安全处理 |
| M5-3 | 可配置仪表盘 | 高 | 已完成 | 2026-08-10 | 全栈 | 指标、柱状/饼图分布、趋势、进度、明细排行六类卡片；支持当前库/当前视图数据范围、卡片增删、聚合与字段配置；前端仪表盘工作区与聚合数据 API 完成 |

## 三点八、M6 - 评论系统与架构债务清理

| ID | 任务 | 优先级 | 状态 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|------|
| M6-1 | 评论系统 | 高 | 已完成 | 2026-08-10 | 全栈 | 新增评论/回复模型、CRUD、字段标记、@提及、解决/恢复、线程查询和删除 API；专利详情页新增评论 Tab，支持编辑、回复和待处理数量提示；新增 2 项评论 API 回归测试 |
| M6-2 | 前端路由深化 | 高 | 已完成 | 2026-08-10 | 前端 | 新增 /db/:databaseId/... 作用域路由并保留旧路径兼容；库/视图/产品、搜索、分页、排序、筛选、同族开关同步到 URL，刷新与浏览器前进后退可恢复工作区 |
| M6-3 | 后端统一错误处理 | 高 | 已完成 | 2026-08-10 | 后端 | API 业务路由统一使用 AppException/BadRequestException/NotFoundException；保留 code/message/detail 兼容响应结构 |
| M6-4 | 字段注册表重构 | 中 | 已完成 | 2026-08-10 | 后端 | 新增 FieldHandler、SystemFieldHandler、CustomFieldHandler 和 FieldRegistry；保留旧注册表兼容接口 |
| M6-5 | 前端 Service 层 | 中 | 已完成 | 2026-08-10 | 前端 | 新增 services 层，核心专利列表/详情/仪表盘/自动化页面迁移；字段元数据增加请求复用和失效入口 |
| M6-6 | 类型补全与全量回归 | 高 | 已完成 | 2026-08-10 | 全栈 | 新增架构回归测试；通过全量后端测试、TypeScript、ESLint、Vite build、Python compileall 和 diff check |

## 四、增强迭代（P2 - 锦上添花）

| ID | 任务 | 优先级 | 状态 | 备注 |
|----|------|-------|------|------|
| P2-1 | 统计看板补齐 4 个维度 | 低 | 已完成 | 2026-08-09 已有申请趋势/类型分布/按产品/按分类，并提供库/产品筛选 |
| P2-2 | 导入历史页 + 后端 /import/batches 端点 | 低 | 已完成 | 2026-08-09 导入流程持久化批次状态、来源批次和错误摘要；新增列表/详情 API 与前端历史页 |
| P2-3 | AI 值人工覆盖端点 + UI | 中 | 已完成 | 2026-08-09 完成 GET/PUT/DELETE /patents/{id}/ai-values；AI 引擎普通重算尊重人工值，强制重算可恢复生成值；详情页支持编辑/清除覆盖 |
| P2-4 | 单专利 wiki 分享页 | 低 | 已完成 | 2026-08-09 新增随机 token 分享链接、撤销/过期控制、只读技术主题页与详情页生成/复制入口；公开 API 使用字段白名单，不输出内部 custom/AI JSON |
| P2-5 | 修 /products N+1 查询 | 低 | 已完成 | 2026-08-09 已使用按产品聚合计数查询 |
| P2-6 | 搜索自动补全 | 低 | 已完成 | 2026-08-09 新增 GET /search/suggest，支持标题、申请号、公开号、申请人、发明人、分类建议及数据库过滤；列表搜索框接入防抖、键盘和点击选择 |
| P2-7 | 专利引用/专利族关系图谱 | 低 | 已完成 | 2026-08-10 新增按深度聚合的同族/双向引用图数据 API；详情页关联关系 Tab 接入 AntV G6，支持力导布局、缩放、画布/节点拖拽、节点选择、关系类型开关和 1/2 层深度；G6 按需动态加载 |

---

## 五、当前数据治理重构（G0 - 专利信息中心基础闭环）

> 本节是当前真实状态的优先依据。既有 P0/P1/M 任务记录的是历史阶段交付，不等于新数据治理目标已经完成。

| ID | 任务 | 优先级 | 状态 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|------|
| G0-1 | 导入原始文件、来源行和未知属性保留 | 高 | 已完成 | 2026-08-16 | 后端/导入 | `ImportSourceRow`、`FieldObservation`、文件哈希、来源表/Sheet/行/列、原始文件下载 |
| G0-2 | 已知字段增量合并与 Wiki 来源历史 | 高 | 已完成 | 2026-08-16 | 后端/导入 | 相同值、格式差异、内容差异均保留观察；未知属性不进入正式字段和默认统计 |
| G0-3 | 待治理属性查询与导出 | 高 | 已完成 | 2026-08-16 | 后端/导入 | `/import/unmapped` 默认只给待处理队列；`/import/unmapped/export` 默认导出完整观察证据，支持 `status` 筛选 |
| G0-4 | 前端 lint 回归修复 | 中 | 已完成 | 2026-08-16 | 前端 | `npm run lint` 通过，0 errors / 0 warnings；同时修复异步字段元数据加载相关 Hook 规则问题 |
| G0-5 | 待治理属性人工确认、映射与可审计回填 | 高 | 已完成 | 2026-08-16 | 全栈 | 支持单条/同批次同来源列批量处理、映射已有字段、可选采用来源值、PatentHistory 和 GovernanceDecision |
| G0-6 | 待治理属性工作台 | 高 | 已完成 | 2026-08-16 | 前端 | 已接入 `/governance`；支持批次/来源列筛选、原始/当前/候选值对照、四类治理动作和影响数量提示 |
| G0-7 | 专利统一身份与高频业务视图模板基础 | 高 | 已完成 | 2026-08-17 | 全栈 | 新增 `PatentIdentifier` 身份索引与格式别名；导入联合申请/公开/授权号并隔离跨记录冲突；六类高频 SavedView 幂等初始化；新增 `PatentExportTemplate`、Excel/Word/CSV 模板 API 与字段血缘输出；完成后端初始化和模板 API |
| G0-7a | 专利身份链详情与来源追溯体验 | 高 | 已完成 | 2026-08-19 | 全栈 | 详情页新增“身份与来源”分区，展示身份索引、原始别名、规范化值、法域、kind code、来源时间、字段最近来源和来源表/行；身份冲突行保存候选 Patent ID 并可从详情定位治理工作台；补齐身份 API、旧库列迁移和回归测试 |
| G0-7b | 高频业务视图入口与工作文件下载 | 高 | 已完成 | 2026-08-19 | 全栈 | 六类高频视图增加快捷入口；工作区增加按当前数据库模板选择、预览并下载 Excel/Word/CSV，叠加当前搜索和筛选；下载文件名保留模板版本；补充空状态/失败状态和模板 API 回归 |
| G0-7c | 高频业务视图字段自定义配置 | 高 | 已完成 | 2026-08-19 | 全栈 | 视图级 `column_config` 持久化字段显隐、顺序、宽度；列管理面板支持搜索、上下移动、批量显隐、恢复初始和失败重试；新字段默认不进入已有高频视图；补充视图隔离、未知 key 保留、重复 key 校验和主数据不变回归 |
| G0-8 | 治理撤销恢复、历史面板与分页 | 高 | 已完成 | 2026-08-16 | 全栈 | 新增可恢复决策批次、追加式 `GovernanceReversal`、后续修改冲突保护、决策历史面板和待治理队列分页；统一身份索引已在 G0-7 完成 |

---

## 六、变更记录

| 日期 | 任务ID | 变更内容 |
|------|--------|---------|
| 2026-08-17 | G0-7 | 完成统一专利身份与工作文件基础闭环：新增 `PatentIdentifier`、号码规范化/原始别名、历史身份回填、导入行联合身份匹配和跨 Patent 身份冲突隔离；新增专利身份查询 API；为每个数据库幂等创建六类高频业务 SavedView；新增 `PatentExportTemplate` 及 Excel/Word/CSV 模板 CRUD 和导出字段血缘；补充前端类型/API、身份/模板/视图/导出回归测试。全量后端 46 项通过。 |
| 2026-08-19 | G0-7a | 完成专利详情身份链与来源追溯闭环：修正身份子路由顺序；详情页展示三类号码投影、PatentIdentifier 原始别名/规范化值/法域/kind code/来源时间；字段来源显示最近来源表和来源行；身份冲突持久化候选 Patent ID，提供 `/identity-conflicts` 查询并从详情跳转治理工作台；治理工作台支持 `patent_id` 筛选。身份与导入相关后端 22 项、前端 lint 通过。 |
| 2026-08-19 | G0-7b | 完成高频视图与工作文件前端闭环：补充六类 SavedView 快捷入口、工作文件模板选择/预览/下载弹窗，沿用模板字段、视图、版本和导出血缘；当前搜索和临时筛选作为附加条件传入；通过模板 API 回归、ESLint、TypeScript 和 Vite build。 |
| 2026-08-19 | G0-7c | 完成高频业务视图字段配置闭环：视图列配置经过后端 schema/service 校验；前端新增视图级列管理面板，支持显隐、顺序、列宽和保存状态；表头拖拽宽度写回当前视图；新字段在已有视图中默认隐藏但可主动加入；补充视图 API 回归测试和 Agent 实施契约。 |
| 2026-08-16 | G0-8 | 完成治理恢复切片：每次治理动作生成 `decision_batch_id` 并保存观察/专利字段变更前状态；新增治理批次查询、批次恢复 API、追加式 `GovernanceReversal`、后续修改冲突保护、`governance_revert` Wiki 历史、前端决策历史面板和分页。统一专利身份、六类高频视图和工作文件模板仍未完成。通过导入治理定向测试 15 项、前端 lint、TypeScript 和 compileall。 |
| 2026-08-16 | G0-3~G0-6 | 完成待治理属性确认首版：新增 `GovernanceDecision` 追加式决策记录、四类服务层治理动作、已有字段映射与可选来源值回填、`PatentHistory(source=governance)`、同批次同来源列范围控制、稳定的决策历史 JSON 接口和 `/governance` 工作台；完整证据 CSV 默认包含已保留/已忽略观察。该记录对应首版验收时点，后续 G0-8 已补齐撤销恢复、历史面板和分页。 |
| 2026-08-16 | G0-1~G0-3 | 完成未知导入属性的原始文件、来源行、来源列和值保留；新增 FieldObservation 和来源 Wiki 历史；提供待治理查询与 CSV 导出。更新 P0-10 过期描述，明确未知列不自动创建 CustomField。后端 `backend/tests` 39 项通过；当前前端 lint 仍需修复。 |
| 2026-08-11 | UI-2 | 完成工作台关键交互回归收尾：列表页以 URL 数据库 ID 作为最终作用域，避免切库瞬间读写旧库；表格宽度改为可滚动的 max-content，列拖拽继续持久化；移动端折叠侧栏打开时自动恢复完整抽屉；工具、统计、智能分析页面移除 Emoji 并统一使用内联 SVG 图标；导入确认真实汇总同族/引用关系数量；新增 XLSX/无效上传和 SQLite 同族成员入库回归测试。通过 npm run lint、TypeScript、Vite build、compileall、32 项后端测试和 git diff --check。 |
| 2026-08-11 | UI-2 | 修复工作台关键交互回归：数据库切换改为显式携带目标库路由并按 URL 库加载视图；Excel/CSV 导入修复 multipart boundary、大小写扩展名、编码和 400 错误响应；同族解析支持逗号、分号、竖线、斜杠、反斜杠、换行和去重，并按数据库隔离关系记录；新增真实单元格撤回/重做命令栈与快捷键、列宽拖拽持久化、桌面侧栏折叠；工具区改用内联 SVG 图标；AI 字段创建与执行拆分。新增导入/同族回归测试，lint、TypeScript、Vite build、compileall 和 7 项后端测试通过。 |
| 2026-08-11 | UI-1 | 重构前端工作台界面：统一侧栏、顶部上下文、专利列表工具区、视图工具区、筛选/批量操作区、专利详情页与管理台的层级和响应式布局；保留原有导入、视图、编辑、导出、AI 与管理功能。通过 ESLint、TypeScript、Vite build 与 diff check。 |
| 2026-07-19 | P0-0 | 修复 generate_icon.py 在 Windows cp1252 环境下的 UnicodeEncodeError：脚本顶部 reconfigure stdout/stderr 为 utf-8、去掉 emoji、workflow 加 PYTHONUTF8=1 |
| 2026-07-19 | P0-1 | 新增 PatentDetailPage.tsx（6 个 Tab：基础著录/技术信息/风险与应用/AI 分析/自定义字段/关联关系），支持查看+编辑+保存+删除+AI 单条生成 |
| 2026-07-19 | P0-2 | 新增 backend/app/api/settings.py（GET/PUT /settings + /settings/test-llm），配置持久化到 settings.json；新增前端 SettingsPage.tsx；AI 引擎每次调用前从 settings.json 读最新配置；openai SDK 作为 langchain 兜底 |
| 2026-07-19 | P0-3 | 新增 AITaskMonitor.tsx（自动刷新+进度条+错误详情）；后端新增 GET /ai/tasks、DELETE /ai/tasks/{id}；PatentListPage 接入 AI 批量处理弹窗 |
| 2026-07-19 | P0-4 | 重构 PatentListPage：表头全选 checkbox、行 onClick 进详情、6 列可排序、分类筛选 input、批量编辑弹窗（模块+风险等级）、批量打标签入口、AI 批量处理入口全部接入真实逻辑 |
| 2026-07-19 | - | App.tsx 接入详情页/设置页/AI任务页路由；Sidebar 增加 AI 任务和设置入口；移除顶部死控件搜索框（搜索已在列表页内） |
| 2026-07-19 | P0-5 | 修复 Tauri 构建链路：tauri.conf.json 的 beforeBuildCommand 路径由 `cd frontend` 改为 `cd ../frontend`（tauri 从 src-tauri/ 目录执行命令）；identifier 改为 com.patwiki.desktop；修复 6 个 TS 编译错误（AITask 类型补字段、AIFieldInfo 本地类型替代 CustomField、清理未使用 import/参数、显式 (id: number) 类型注解、删除 StatsPage typeMap 死代码）；本地 `npm run build` 通过 |
| 2026-07-20 | P0-6 | 实现多维表格核心：1) 后端新增 GET /fields 字段元数据API（整合系统字段+自定义字段）、PATCH /patents/{id}/field/{key} 单元格快速更新API、PatentService.list_patents 支持 custom_filters 和自定义字段排序（SQLite json_extract）；2) 前端重构 types/api 层新增 FieldMeta/CellUpdateRequest 类型和 fieldApi/patentApi.updateCell；3) 重构 PatentListPage 为多维表格：动态列渲染、列宽拖拽调整、列头菜单（排序/筛选/隐藏列）、可编辑单元格内联编辑（text/select/boolean/date/longtext）、高级筛选面板、字段配置弹窗（显隐切换/新建自定义字段/删除自定义字段）、选中行高亮、冻结列；4) 全面清理所有页面EMOJI（Sidebar/App/Stats/Settings/Import/Detail/AITaskMonitor）；5) CSS 重构为专业多维表格风格（datagrid-toolbar/datagrid-footer/col-header-menu/status-badge/risk-badge等样式类） |
| 2026-07-20 | P0-7 | 修复打包后端启动失败：patwiki_backend.spec 的 hiddenimports 漏掉 P0-6 新增的 app.api.fields 和 app.services.field_registry，导致打包后 uvicorn 字符串导入 app.main 时静默失败（只报 "Could not import module"）。同时 run.py 改为直接 from app.main import app 并传入 uvicorn.run(app, ...)，遇导入错误打印真实 traceback。诊断中还发现 8765 端口被 7/19 19:04 启动的旧 python 进程（PID 32704）占用，导致新后端被迫使用 1108，而前端 Vite proxy 硬编码 8765，造成前后端错位 |
| 2026-07-19 | P0-8/9/10/11/12 | 启动 P0 第二阶段规划：新增 docs/07-P0阶段-库模型与Wiki式导入设计.md，定义 PatentDatabase 库模型、Wiki 式字段级增量合并、未知列自动创建 CustomField、同族/引用关系解析、patent_project 多维属性扩展、models 目录按 03-项目结构与代码规范.md 拆分为 11 个子模块、前端导入首步 chooseDatabase + Sidebar 库切换器 |
| 2026-07-19 | P0-8/9/10/11/12 | 完成 P0 第二阶段全部任务：1) 后端 models 拆分为 11 子模块，PatentDatabase 库模型 + Patent.database_id 外键，PatentProjectLink 替代简单 patent_project Table 新增多维属性；2) merge_service.Wiki 字段级合并 + ANNOTATION_FIELDS 标注类保护；relation_service 解析同族/引用号、MD5 哈希 family_id、占位 Patent 创建；import_service.suggest_mapping 自动为未知列建 CustomField（cf_ 前缀+短哈希），_row_to_patent_data 拆出虚拟字段（family_members/cited_patents/citing_patents），process_import/confirm_import 接入 merge+relation+database_id；3) DatabaseService 库 CRUD+归档+refresh-count，api/databases 路由，init_data 创建"默认数据库"，schemas 补 PatentDatabase schema；4) 前端 types 新增 PatentDatabase 类型与 ImportPreview/ImportResult 字段扩展，api 新增 databaseApi，store 新增 databases/currentDatabaseId，App.tsx 初始化加载库列表，Sidebar 顶部库切换器+新建库表单，PatentListPage 查询参数带 database_id，ImportModal 新增 chooseDatabase 步骤、显示"将自动创建 N 个新字段"提示、对 cf_ 字段标"新建字段"徽章、对虚拟字段标"关系入库"徽章、完成页显示同族/引用关联统计；5) patwiki_backend.spec 补全 12 个新模块 hiddenimports；6) 前端 npm run build 通过 0 错误，后端 init_db 验证 OK（1 默认库+6 AI字段） |
| 2026-08-07 | P0-14 | 完成视图工作区第二批能力：新增分组查询接口、最多三级嵌套分组、默认折叠、条件格式运算符校验与配置接口；前端新增分组/条件格式配置面板、分组表头折叠和单元格条件着色。通过后端编译、接口回归与前端 npm run build。 |
| 2026-08-08 | P0-15 | 完成看板视图基础闭环：新增看板分组/卡片查询与拖拽换列 API；前端新增 KanbanView，支持分组字段选择、卡片字段配置、详情跳转和跨列更新；自定义字段读取与视图写回链路同步修正。 |
| 2026-08-08 | P0-5 | 新增 scripts/build_windows.ps1 作为本地与 CI 共用的 Windows 打包入口；统一依赖检查、图标生成、PyInstaller 后端构建、前端构建、固定 Tauri CLI 2.11.4 和 MSI/NSIS 产物校验；tauri.conf.json 同步声明 msi 与 nsis 目标，并修正 Tauri 在仓库根目录执行 beforeBuildCommand 的前端路径；本地实际生成 MSI 与 NSIS 安装包；修复 Windows PowerShell 单文件产物在集合相加时的 FileInfo 标量错误。 |
| 2026-08-08 | P1-1~P1-8 | 新增管理台路由和页面，覆盖产品、项目、标签/标签组、部门/人员、产品线 CRUD；补齐对应后端 update/delete 接口和 Pydantic schema；管理台提供自定义字段入口；ImportModal 产品/项目下拉接入 store 并按产品过滤项目；bulk-update 改用 BulkUpdateRequest 请求体。通过 ESLint、TypeScript、Vite build、后端 compileall 和 diff check。 |
| 2026-08-09 | P1-9 | 清理 backend/app/services/import_service.py 中无调用方的 preview_import、process_import、create/list/get_import_batch 方法及专属依赖，保留当前 imports API 使用的解析、映射和行转换链路。通过后端 compileall、前端 lint/build 和 diff check。 |
| 2026-08-09 | M3 | 新增 CrossTableLink 与 Link/Lookup/Rollup 字段配置；新增关联字段 CRUD、目标记录搜索、Lookup/Rollup 单条与批量解析 API；专利表格接入 Link 搜索/添加/移除和 Lookup/Rollup 只读展示；新增 3 项服务/API 回归测试。已通过 unittest、compileall、ESLint、TypeScript、Vite build 与 diff check，并提交 4989752 推送 main。 |
| 2026-08-09 | P2-1/P2-5 | 核对现有实现：StatsPage 与 /stats 已覆盖申请趋势、类型、产品、分类四个维度；/products 已使用一次聚合查询生成专利数，确认两项已完成。 |
| 2026-08-09 | P2-2 | 导入确认流程新增 ImportBatch 持久化、处理进度/统计/错误状态和新专利 source_batch_id；新增 GET /import/batches、GET /import/batches/{id} 与导入历史页面/导航。通过 2 项历史 API 测试、compileall、ESLint、TypeScript、Vite build 和 diff check。 |
| 2026-08-09 | P2-3 | 新增 AI 值人工覆盖 GET/PUT/DELETE API、覆盖状态与原始生成值返回、人工修改历史；AI 引擎普通重算保留人工覆盖，强制重算清除覆盖；详情页 AI Tab 接入编辑、清除和重新生成；新增 2 项回归测试。通过 7 项后端测试、compileall、ESLint、TypeScript、Vite build 和 diff check。 |
| 2026-08-09 | P2-4 | 新增 PatentShare 模型与单专利分享链接 API（创建、列表、撤销、过期校验、访问统计）；新增公开只读技术主题页面、详情页生成/复制链接对话框；公开内容采用字段白名单；新增 2 项分享 API 回归测试。通过分享测试、compileall、ESLint、TypeScript、Vite build 和 diff check。 |
| 2026-08-09 | P2-6 | 新增 GET /search/suggest 自动补全 API，按数据库过滤并对标题、申请号、公开号、申请人、发明人、分类建议去重排序；列表页搜索框接入防抖、鼠标选择、上下箭头与 Enter 选择；新增 2 项搜索 API 回归测试。通过全量后端测试、compileall、ESLint、TypeScript、Vite build 和 diff check。 |
| 2026-08-10 | P2-7 | 新增 GET /patents/{id}/graph 图数据接口，聚合同族与双向引用关系并支持深度/类型开关；新增 PatentGraph G6 组件及详情页关系图谱面板，支持力导布局、缩放、拖拽和节点选择；新增 2 项图谱 API 回归测试；G6 动态加载使主 JS 约 513KB，图谱 chunk 按需加载。通过全量 13 项后端测试、compileall、ESLint、TypeScript、Vite build 和 diff check。 |
| 2026-08-10 | M1 | 新增公式字段与数据导出：安全 AST 公式引擎、函数白名单、字段依赖/循环检测、增量和全量重算；新增 Excel/CSV 导出、当前库/视图筛选、字段选择和 Excel 分组 Sheet；修复普通字段与公式字段互相切换时的依赖、配置和下游重算；补齐 PyInstaller hidden imports。通过全量 18 项后端测试、compileall、ESLint、TypeScript、Vite build 和 diff check。 |
| 2026-08-10 | M4 | 新增表单视图与甘特视图：后端完成表单配置/校验/提交、公开分享链接、甘特时间线查询和日期写回；前端接入工作区视图切换、表单录入/公开页面、甘特分组时间线和拖拽更新；补齐表单/甘特回归测试、界面样式与 PyInstaller hidden imports。通过全量 20 项后端测试、compileall、ESLint（0 errors/0 warnings）、TypeScript、Vite build 和 diff check。 |
| 2026-08-10 | M5 | 完成自动化规则、附件字段与可配置仪表盘：新增规则/日志模型、五类触发器、六类动作、定时轮询、附件安全存储与文件接口、六类仪表盘卡片聚合 API；前端新增自动化规则管理和执行记录、仪表盘配置工作区；新增 3 项 M5 回归测试。通过全量 23 项后端测试、compileall、ESLint（0 errors/0 warnings）、TypeScript 和 diff check。 |
| 2026-08-10 | M6-1 | 新增 Comment 模型与 CommentService，支持评论、回复、字段标记、@提及、编辑、解决/恢复、线程查询和删除；专利详情页新增评论与讨论 Tab。通过全量 25 项后端测试、compileall、ESLint（0 errors/0 warnings）、TypeScript、Vite build 和 diff check。 |
| 2026-08-10 | M6-2 | 深化前端路由：新增按数据库作用域的工作区路由，旧路径保持兼容；当前库、视图、产品、搜索、分页、排序、筛选和同族开关写入 URL，支持刷新和前进/后退恢复。通过全量 25 项后端测试、compileall、ESLint（0 errors/0 warnings）、TypeScript、Vite build 和 diff check。 |
| 2026-08-10 | M6-3 | 完成后端业务路由统一异常迁移：移除 API 层直接抛出的 HTTPException，统一使用应用异常类型；异常处理器保留 code/message/detail 结构，兼容旧客户端和独立 Router 测试。 |
| 2026-08-10 | M6-4 | 完成字段注册表架构重构：系统字段、自定义字段分别由处理器负责，FieldRegistry 统一注册、查询、读取和写入；旧兼容导出保持不变。 |
| 2026-08-10 | M6-5 | 新增 frontend/src/services/index.ts，抽离核心页面的专利、字段、AI、关联、视图、仪表盘和自动化请求；字段元数据服务提供内存复用与失效机制。 |
| 2026-08-10 | M6-6 | 新增架构回归测试并完成 M6 全量验收：后端测试 27 项、Python compileall、ESLint、TypeScript、Vite build 和 git diff --check 均通过。 |
