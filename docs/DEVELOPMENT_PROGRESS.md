# PatWiki 开发进度跟踪表

> **规则**：每次代码更新完成后，必须同步更新本文件的状态列和实际完成日期。
> 状态值：`未开始` / `进行中` / `已完成` / `已阻塞`
> 更新时把对应行的"状态"改为已完成并填入"实际完成日期"，同时在底部"变更记录"追加一行。

最近更新：2026-07-20（P0 第三阶段完成：部门总表 + 小表视图后端实现；同步完成全项目盘点，详见"五、盘点报告"与"六、冲突与优化项"）

---

## 五、盘点报告（2026-07-20）

### 5.1 必要但未实现的功能

| 编号 | 缺口 | 影响 | 优先级 |
|------|------|------|--------|
| G-1 | **视图功能前端零集成**：后端 `/views` 系列 API 完整可用，但前端 PatentListPage 没有任何"部门总表/小表/视图"入口，`api/index.ts` 未定义 viewApi。用户无法通过 UI 使用部门总表 | 致命：用户核心需求无法落地 | 高 |
| G-2 | **历史记录与字段来源 UI 缺失**：后端 `GET /patents/{id}/history`（已含 source_view_id/name）、`GET /patents/{id}/field-sources` 已就绪，前端详情页无历史 Tab、列表无字段来源标注 | 高：用户明确要求"任意数据可追溯" | 高 |
| G-3 | **视图配置 schema 未标准化**：`PatentView.filter_config` / `column_config` 是无约束 JSON，前端 PatentListPage 已有自己的 filters/columns 结构，两者未对齐 | 高：前端无法稳定保存/还原视图 | 高 |
| G-4 | **前端 PatentListPage 配置无法持久化**：列宽/筛选/排序/字段显隐调整后刷新即丢，需要绑定到后端视图 | 高：与 G-1 同源 | 高 |
| G-5 | **部门总表自动初始化缺失**：首次访问库时应自动创建 `is_department_master=True` 视图（后端幂等端点已有），前端无调用时机 | 中 | 中 |
| G-6 | **PatentHistory.source 无枚举**：当前仅 `manual` / `promote`，缺 `import` / `ai` / `view_edit` / `bulk_update`，溯源不完整 | 中 | 中 |
| G-7 | **P0-5 Tauri 桌面打包仍进行中**：等待 Rust 编译产出 MSI/NSIS，非业务关键路径 | 低 | 低 |
| G-8 | **P1/P2 全部未开始**：管理页 9 项 + 增强功能 7 项均未启动 | 中：MVP 后再做 | 中 |

### 5.2 功能冲突

| 编号 | 冲突点 | 现状 | 建议处理 |
|------|--------|------|----------|
| C-1 | 单字段更新双端点 | `PATCH /patents/{id}/field/{key}`（fields.py） 与 `PATCH /views/{vid}/patents/{pid}/field/{key}`（views.py）都做单字段更新，后者仅多记 source_view_id | **合并**：让 `/patents/{id}/field/{key}` 接受可选 `source_view_id` body 参数，删除 views.py 中的重复端点 |
| C-2 | 导入"未知列自动创建 CustomField" vs 视图本地字段 | import_service 把未知列直接建为全局 CustomField（污染大表）；视图本地字段则不污染。两种模式对立 | **统一**：导入到指定视图时，未知列默认建为该视图的本地字段；导入到大表时维持现状 |
| C-3 | column_config 语义模糊 | `column_config=[]` 是"空"还是"显示全部"？前端 PatentListPage 的列配置结构 vs 后端 column_config 未对齐 | **定义**：`[]` = 显示全部字段（白名单为空等价全选）；非空 = 白名单 + 排序 |
| C-4 | PatentListPage 已有列配置 vs 视图 column_config | 前端表格的列宽/显隐/排序在本地 state，与后端视图 column_config 完全脱节 | **重构**：PatentListPage 必须改为"绑定视图"模式，所有列配置变更自动同步到当前视图 |
| C-5 | 视图列来源类型混合 | 小表中的列可能是 system / custom / view_local 三类，前端无统一接口获知每列来源 | **扩展**：`GET /fields?view_id=xxx` 返回该视图可见的全部字段元数据，每列注明 source |

### 5.3 可合并/优化的项

| 编号 | 优化点 | 说明 |
|------|--------|------|
| O-1 | 字段元数据接口扩展 | `GET /fields` 增加 `?view_id=xxx` 参数，返回系统字段 + custom_fields + 该视图的 view_local_fields，前端统一渲染 |
| O-2 | PatentHistory.source 改为枚举 | 新增 `HistorySource` 枚举：manual / import / ai / promote / view_edit / bulk_update |
| O-3 | 部门总表视图列策略 | `is_department_master=True` 的视图 `column_config` 强制为 `[]`（全字段），不允许列裁剪 |
| O-4 | 视图与权限结合 | `DatabaseMembership.role` 已有 owner/editor/viewer；视图编辑权限应继承库成员角色（owner 可改部门总表，editor 可改自己视图，viewer 只读） |
| O-5 | import_service 死代码清理 | P1-9 已记录，可在做 C-2 时一并清理 |
| O-6 | P1-4 自定义字段管理页 与 字段提升 UI 合并 | 自定义字段管理页应同时展示"从视图提升"的字段及其源视图，避免拆两处管理 |

---

## 六、冲突与优化项（待办池）

> 以下任务来源于第五节盘点，按优先级排序。可在 P0 收尾或 P1 启动时安排。

| 编号 | 任务 | 关联 | 优先级 |
|------|------|------|--------|
| OPT-1 | 合并单字段更新端点（C-1） | C-1, G-6 | 高 |
| OPT-2 | 标准化 filter_config / column_config JSON schema（C-3, G-3） | C-3, G-3 | 高 |
| OPT-3 | 扩展 GET /fields 支持 view_id 参数（C-5, O-1） | C-5 | 高 |
| OPT-4 | PatentHistory.source 改枚举 + 补齐来源（G-6, O-2） | G-6 | 中 |
| OPT-5 | 部门总表视图列策略（C-3, O-3） | C-3 | 中 |
| OPT-6 | 导入支持"未知列建为视图本地字段"（C-2） | C-2 | 中 |
| OPT-7 | 视图编辑权限继承库成员角色（O-4） | O-4 | 中 |
| OPT-8 | 自定义字段管理页含"提升字段"展示（O-6） | O-6 | 低 |

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
| P0-5 | Tauri 桌面应用打包构建 | 高 | 进行中 | 2026-07-19 | - | CI | tauri.conf.json 路径修复 + TS 编译错误清零，等待 Rust 编译产出 MSI/NSIS |
| P0-6 | 多维表格核心（字段系统+动态列+内联编辑+筛选） | 高 | 已完成 | 2026-07-20 | 2026-07-20 | 全栈 | 字段元数据API/单元格PATCH/自定义字段筛选排序；前端动态列渲染/列宽拖拽/列头菜单/内联编辑/高级筛选面板/字段显隐配置/新建自定义字段 |
| P0-7 | 修复打包后端启动报错 + 端口冲突排查 | 高 | 已完成 | 2026-07-20 | 2026-07-20 | 全栈 | patwiki_backend.spec 补充 app.api.fields/app.services.field_registry 等 hidden imports；run.py 改为直接传入 app 对象，遇导入错误打印真实 traceback 而非 uvicorn 的 "Could not import module" |

### 1.2 第二阶段（库模型 + Wiki 式增量导入）

| ID | 任务 | 优先级 | 状态 | 计划完成 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|---------|------|
| P0-8 | 拆分 models 目录 + 新增 PatentDatabase 模型 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 后端 | 按 03-项目结构与代码规范.md 拆分为 base/enums/association/organization/project/tag/field/database/patent/ai/importing 11 个子模块；新增 PatentDatabase 表，Patent 增加 database_id 外键 |
| P0-9 | 扩展 patent_project 关联表为多维属性 | 中 | 已完成 | 2026-07-19 | 2026-07-19 | 后端 | PatentProjectLink 替代 Table：relation_type/risk_level/document_role/relevance_score/importance/assigned_to_id |
| P0-10 | 改造 import_service 为 Wiki 式增量合并 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 后端 | 新增 merge_service/relation_service；未知列自动创建 CustomField（auto_create_custom_field）；同族/引用号解析入库；标注类字段非空才覆盖；_row_to_patent_data 拆出虚拟字段；confirm_import 接入 database_id 与关系入库统计 |
| P0-11 | 新增 database_service + /databases API | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 后端 | 库 CRUD + 归档 + refresh-count；init_data 创建"默认数据库"；schemas/schemas.py 新增 PatentDatabase 系列 schema；patwiki_backend.spec 补全 hiddenimports |
| P0-12 | 前端 ImportModal + 库切换器改造 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 前端 | 导入首步 chooseDatabase（选/建库）；未匹配列显示"新建字段"徽章+顶栏提示；Sidebar 顶部库切换器+新建库；PatentListPage 查询带 database_id；store 新增 databases/currentDatabaseId；types 新增 PatentDatabase 与 ImportPreview/ImportResult 字段扩展 |

### 1.3 第三阶段（部门总表 + 小表视图 - 后端已完成）

> 用户需求：底层综合全属性大表 + 可拉取指定意图小表，小表与大表共享属性实时更新，小表持续存在便于同主题维护，非大表属性注明来源小表，任意数据可历史追溯。

| ID | 任务 | 优先级 | 状态 | 计划完成 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|---------|------|
| P0-13 | 视图模型 + 服务 + API（后端） | 高 | 已完成 | 2026-07-20 | 2026-07-20 | 后端 | 新增 models/view.py：PatentView/ViewLocalField/PatentViewFieldValue 三模型；扩展 PatentHistory 加 source_view_id/source_view_name；新增 view_service.py：视图 CRUD + 共享字段写入 + 字段提升（vlf_→cf_）+ 字段来源追溯；新增 api/views.py 路由；api/databases.py 新增 GET /databases/{id}/master-view 幂等端点；patent_service.update_patent 支持 source_view_id 参数；patwiki_backend.spec 补 hiddenimports；16 步 E2E 测试全部通过 |

### 1.4 第四阶段（视图前端集成 - 待启动，关键路径）

> ⚠️ 这是用户核心需求落地的最后一公里。后端完整可用，但前端 0 集成，必须先做。

| ID | 任务 | 优先级 | 状态 | 计划完成 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|---------|------|
| P0-14 | 前端 viewApi + 类型定义 + store | 高 | 未开始 | - | - | 前端 | api/index.ts 新增 viewApi（list/get/create/update/delete/archive/local-fields/promote/field-sources）；types 新增 PatentView/ViewLocalField/FieldSource；store 新增 views/currentViewId |
| P0-15 | Sidebar 视图切换器 + 部门总表入口 | 高 | 未开始 | - | - | 前端 | 库下方加"视图"区：部门总表（自动获取/创建）+ 我的小表 + 新建小表按钮；点击切换 currentViewId |
| P0-16 | PatentListPage 绑定视图（重构） | 高 | 未开始 | - | - | 前端 | 列宽/显隐/筛选/排序全部同步到当前视图 column_config/filter_config/sort_config；首次进入库自动加载部门总表；新增"小表本地字段"列渲染+编辑；新增"提升为全局字段"右键菜单 |
| P0-17 | PatentDetailPage 历史记录 Tab + 字段来源标注 | 高 | 未开始 | - | - | 前端 | 详情页新增"历史记录"Tab（时间轴展示 PatentHistory）；每个字段右侧加"来源"角标（直接编辑/来自 XX 小表/AI 生成/导入） |
| P0-18 | 视图管理页（新建/编辑/归档/删除） | 中 | 未开始 | - | - | 前端 | 简单弹窗：名称/描述/筛选/列选择/排序；部门总表禁删禁归档提示 |

## 二、下一迭代（P1 - 管理功能 + 架构优化）

> P1 在 P0-14~P0-18 视图前端落地后启动。P1-10/P1-11/P1-12 来自第六节优化池，应在视图前端开发时一并完成以避免返工。

| ID | 任务 | 优先级 | 状态 | 备注 |
|----|------|-------|------|------|
| P1-1 | 产品管理页（CRUD） | 中 | 未开始 | 接入 productApi 全套 |
| P1-2 | 项目管理页（CRUD） | 中 | 未开始 | 接入 projectApi 全套 |
| P1-3 | 标签 + 标签组管理页 | 中 | 未开始 | 接入 tagApi + tagGroupApi |
| P1-4 | 自定义字段管理页（含"提升字段"展示） | 中 | 未开始 | 合并 O-6：展示从视图提升的字段及源视图 |
| P1-5 | 部门/人员管理页 | 中 | 未开始 | 接入 departmentApi + personApi |
| P1-6 | 后端补齐元数据 CRUD（update/delete） | 中 | 未开始 | 部门/人员/标签组/产品线 |
| P1-7 | 修 ImportModal 产品/项目下拉填充 | 中 | 未开始 | 从 store 读取 |
| P1-8 | 修后端 bulk-update 入参模型 | 中 | 未开始 | 封装为 BulkUpdateRequest |
| P1-9 | 清理 import_service 死代码 | 低 | 未开始 | process_import 等未被调用，与 P1-12 一并做 |
| P1-10 | 合并单字段更新端点（OPT-1） | 高 | 未开始 | /patents/{id}/field/{key} 接受 source_view_id，删除 views.py 重复端点 |
| P1-11 | 标准化 filter_config / column_config schema（OPT-2） | 高 | 未开始 | 定义 JSON schema，前后端共用；明确 column_config=[] 表示全字段 |
| P1-12 | 扩展 GET /fields 支持 view_id（OPT-3） | 高 | 未开始 | 返回系统+custom+view_local 字段统一元数据，每列注明 source |
| P1-13 | PatentHistory.source 改枚举（OPT-4） | 中 | 未开始 | 新增 HistorySource 枚举，补齐 import/ai/view_edit/bulk_update 来源 |
| P1-14 | 部门总表视图列策略（OPT-5） | 中 | 未开始 | is_department_master=True 强制 column_config=[] 全字段 |
| P1-15 | 导入支持"未知列建为视图本地字段"（OPT-6） | 中 | 未开始 | 导入到指定视图时未知列默认建为 vlf_，避免污染大表 |
| P1-16 | 视图编辑权限继承库成员角色（OPT-7） | 中 | 未开始 | owner 可改部门总表，editor 可改自己视图，viewer 只读 |

## 三、增强迭代（P2 - 锦上添花）

| ID | 任务 | 优先级 | 状态 | 备注 |
|----|------|-------|------|------|
| P2-1 | 统计看板补齐 4 个维度 | 低 | 未开始 | 申请趋势/类型分布/按产品/按分类 |
| P2-2 | 导入历史页 + 后端 /import/batches 端点 | 低 | 未开始 | |
| P2-3 | AI 值人工覆盖端点 + UI | 中 | 未开始 | GET/PUT/DELETE /patents/{id}/ai-values |
| P2-4 | 单专利 wiki 分享页 | 低 | 未开始 | 技术主题分享 |
| P2-5 | 修 /products N+1 查询 | 低 | 未开始 | |
| P2-6 | 搜索自动补全 | 低 | 未开始 | GET /search/suggest |
| P2-7 | 专利引用/专利族关系图谱 | 低 | 未开始 | AntV G6 |

---

## 四、变更记录

| 日期 | 任务ID | 变更内容 |
|------|--------|---------|
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
| 2026-07-20 | P0-13 | 完成 P0 第三阶段视图后端：新增 models/view.py（PatentView/ViewLocalField/PatentViewFieldValue 三模型 + view_type/is_department_master/is_archived/is_promoted 字段）；扩展 PatentHistory 加 source_view_id/source_view_name 列（FK patent_views.id ON DELETE SET NULL + 冗余视图名）；新增 services/view_service.py（视图 CRUD + 共享字段写入 + 视图本地字段 + 字段提升 vlf_→cf_ + 字段来源追溯）；新增 api/views.py 路由（14 个端点）；api/databases.py 新增 GET /databases/{id}/master-view 幂等端点；patent_service.update_patent 支持 source_view_id/source_view_name 参数；patwiki_backend.spec 补 hiddenimports；16 步 E2E 测试全部通过（部门总表创建/幂等、个人小表、视图共享大表数据、本地字段不污染大表、视图内编辑共享字段记录来源、历史含 source_view、字段来源追溯、字段提升值迁移+历史、归档/部门总表保护） |
| 2026-07-20 | - | 全项目盘点：新增"五、盘点报告"（G-1~G-8 未实现缺口、C-1~C-5 冲突点、O-1~O-6 优化项）和"六、冲突与优化项待办池"（OPT-1~OPT-8）；新增 P0-14~P0-18 视图前端集成任务（关键路径）；P1 调整为"管理功能+架构优化"，新增 P1-10~P1-16 把 OPT 项纳入正式迭代；P1-4 合并 O-6、P1-9 关联 P1-12 一并做 |
