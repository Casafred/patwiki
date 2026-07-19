# PatWiki 开发进度跟踪表

> **规则**：每次代码更新完成后，必须同步更新本文件的状态列和实际完成日期。
> 状态值：`未开始` / `进行中` / `已完成` / `已阻塞`
> 更新时把对应行的"状态"改为已完成并填入"实际完成日期"，同时在底部"变更记录"追加一行。

最近更新：2026-07-19（P0 已完成，Tauri 打包构建进行中）

---

## 一、当前迭代（P0 - 必须先做完）

| ID | 任务 | 优先级 | 状态 | 计划完成 | 实际完成 | 负责模块 | 备注 |
|----|------|-------|------|---------|---------|---------|------|
| P0-0 | 修复 GitHub Action 编码报错 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | CI | generate_icon.py emoji + PYTHONUTF8 |
| P0-1 | 专利详情页（查看+编辑+AI字段展示） | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 前端 | 6 个 Tab：基础著录/技术/风险/AI/自定义/关联关系 |
| P0-2 | 设置页（LLM API key 配置）+ 后端配置接口 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 全栈 | GET/PUT /settings + /settings/test-llm，配置持久化到 settings.json |
| P0-3 | AI 批量处理入口 + 任务进度页 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 全栈 | 列表页批量AI按钮 + AITaskMonitor 页面 + GET /ai/tasks + DELETE /ai/tasks/{id} |
| P0-4 | 修 PatentListPage 装饰性按钮 | 高 | 已完成 | 2026-07-19 | 2026-07-19 | 前端 | 全选/批量编辑/批量打标签/AI批量/行点击进详情/排序/分类筛选全部接入 |
| P0-5 | Tauri 桌面应用打包构建 | 高 | 进行中 | 2026-07-19 | - | CI | tauri.conf.json 路径修复 + TS 编译错误清零，等待 Rust 编译产出 MSI/NSIS |

## 二、下一迭代（P1 - 管理功能）

| ID | 任务 | 优先级 | 状态 | 备注 |
|----|------|-------|------|------|
| P1-1 | 产品管理页（CRUD） | 中 | 未开始 | 接入 productApi 全套 |
| P1-2 | 项目管理页（CRUD） | 中 | 未开始 | 接入 projectApi 全套 |
| P1-3 | 标签 + 标签组管理页 | 中 | 未开始 | 接入 tagApi + tagGroupApi |
| P1-4 | 自定义字段管理页 | 中 | 未开始 | 含 AI 字段定义 |
| P1-5 | 部门/人员管理页 | 中 | 未开始 | 接入 departmentApi + personApi |
| P1-6 | 后端补齐元数据 CRUD（update/delete） | 中 | 未开始 | 部门/人员/标签组/产品线 |
| P1-7 | 修 ImportModal 产品/项目下拉填充 | 中 | 未开始 | 从 store 读取 |
| P1-8 | 修后端 bulk-update 入参模型 | 中 | 未开始 | 封装为 BulkUpdateRequest |
| P1-9 | 清理 import_service 死代码 | 低 | 未开始 | process_import 等未被调用 |

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
