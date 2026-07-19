# P0 阶段设计方案：库模型 + Wiki 式增量导入

> 核心目标：确立"库"作为专利数据顶层品类归属，导入从"覆盖式"升级为"Wiki 式增量合并"，新列自动成为自定义字段，同族/引用关系入库。
> 创建日期：2026-07-19
> 关联任务：P0-8 / P0-9 / P0-10 / P0-11 / P0-12

---

## 一、背景与问题

### 1.1 当前实现的不足

| 问题 | 现状 | 期望 |
|------|------|------|
| 缺少"库"概念 | 专利直接挂在 Product 上，无顶层品类 | 用户导入时先回答"这是什么库"（如电钻专利数据库），库是品类级容器 |
| 导入是覆盖式 | `update_on_duplicate=True` 时 `PatentService.update_patent` 全量覆盖，已有标注可能被新Excel空值冲掉 | 字段级增量合并：仅更新新Excel中有值的字段，已有数据保留 |
| 未知列被丢弃 | `suggest_mapping` 未匹配的列直接忽略 | 未知列自动创建 CustomField，属性值持续增长形成专利 Wiki |
| 同族/引用未解析 | `PatentFamily` / `Citation` 表存在但导入时不写入 | 导入时识别"同族专利号"列、引用列，写入关系表 |
| 项目关联太简单 | `patent_project` 只有 `role/notes` | 扩展为多维属性：relation_type / risk_level / document_role / relevance_score |

### 1.2 用户原话提炼的核心需求

> "每一个专利导入的时候，都要有一列'同族专利列'……需要解析出这样的关联关系……"
> "几十万条数据，也能很快地抓取出这样的引用关系……"
> "用户凡是导入的信息都要汇总……这个数据的属性值是一直在增长的……不断补入信息，去增加它本身的 Wiki……"
> "首先要问用户这个库是什么库……每个字段都可以像多维表格那样临时增加一个字段……"
> "项目是小表相关的。数据库是一个大表……它和项目的什么相关？是和项目的风险相关，还是和项目的申请相关……"

---

## 二、Database（库）模型设计

### 2.1 数据模型

```python
class PatentDatabase(Base):
    __tablename__ = "patent_databases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)              # "电钻专利数据库"
    code = Column(String(50), unique=True, index=True)      # "DRILL_PATENTS"
    description = Column(Text)
    color = Column(String(20))                              # UI 标识色
    icon = Column(String(50))                               # 图标标识
    is_default = Column(Boolean, default=False)             # 默认库
    is_archived = Column(Boolean, default=False)            # 归档（不再活跃使用）
    patent_count = Column(Integer, default=0)               # 冗余计数（定期刷新）
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    patents = relationship("Patent", back_populates="database")
```

### 2.2 Patent 表改造

新增 `database_id` 外键，可空（兼容历史数据）：

```python
class Patent(Base):
    # ... 原有字段 ...
    database_id = Column(Integer, ForeignKey("patent_databases.id"), index=True, nullable=True)
    database = relationship("PatentDatabase", back_populates="patents")
```

### 2.3 业务规则

1. **导入时强制选择库**：用户上传 Excel 后第一步必须选择/创建一个库，所有导入的专利挂到该库下
2. **去重范围限定在库内**：相同申请号在不同库中允许共存（如"电钻库"和"传感器库"都有同一份基础专利）
3. **库切换**：前端顶部增加"库切换器"，切换后表格只显示该库的专利
4. **默认库**：系统初始化时创建"默认数据库"，旧数据（database_id 为 NULL）视为属于默认库
5. **归档不删除**：库可归档但不可删除（避免专利成为孤儿）

---

## 三、Wiki 式增量导入设计

### 3.1 核心原则

> **"导入即增补，不覆盖"**——同一条专利每次导入都是字段级增补，新字段自动扩展，已有数据保留。

### 3.2 字段级合并策略

```python
def merge_patent_data(existing: Patent, new_data: dict) -> dict:
    """
    Wiki 式字段合并：
    - 系统字段：新值非空则覆盖（著录项目以最新为准）
    - 自定义字段：新值非空则覆盖；新Excel中无此字段则保留原值
    - 标注类字段（has_risk/risk_level/risk_description/notes/technical_*/category/module 等）：
      新值非空才覆盖，避免新Excel缺失字段冲掉人工标注
    """
    merged = {}
    ANNOTATION_FIELDS = {
        "category", "subcategory", "technical_problem", "technical_effect",
        "technical_solution", "has_risk", "risk_level", "risk_description",
        "module", "application_status", "scope_description", "notes",
    }
    for field, new_value in new_data.items():
        if field == "custom_fields":
            continue
        if field in ANNOTATION_FIELDS:
            # 标注类：仅在新值非空时覆盖
            if new_value not in (None, "", []):
                merged[field] = new_value
        else:
            # 著录类：新值非空就覆盖
            if new_value not in (None, "", []):
                merged[field] = new_value

    # 自定义字段：字典级合并
    if "custom_fields" in new_data:
        existing_custom = existing.custom_fields or {}
        new_custom = new_data["custom_fields"] or {}
        for k, v in new_custom.items():
            if v not in (None, "", []):
                existing_custom[k] = v
        merged["custom_fields"] = existing_custom
    return merged
```

### 3.3 未知列自动创建 CustomField

`suggest_mapping` 时，对未匹配的列：

1. 生成 `key`：`cf_` + 列名清洗（去除特殊字符，转 snake_case）+ 短哈希（避免冲突）
2. 自动创建 `CustomField` 记录（field_type 默认 `text`，group_name="导入字段"）
3. 映射表把列指向新 key
4. 前端在 mapping 步骤展示"将创建为新字段"标记

```python
def auto_create_custom_field(db: Session, column_name: str) -> str:
    key = f"cf_{slugify(column_name)}_{short_hash(column_name)}"
    existing = db.query(CustomField).filter(CustomField.key == key).first()
    if not existing:
        cf = CustomField(
            key=key,
            name=column_name,
            field_type=CustomFieldType.TEXT,
            group_name="导入字段",
            description=f"导入时自动创建，源列名：{column_name}",
            is_active=True,
        )
        db.add(cf)
        db.commit()
    return key
```

### 3.4 同族专利列解析

Excel 中的"同族专利号"列可能包含多种格式：

| 格式示例 | 解析策略 |
|---------|---------|
| `CN115000123A; US20230123456A1; EP4123456A1` | 分号/逗号/换行分割 |
| `CN115000123A;;US20230123456A1;;EP4123456A1` | 双分号分割 |
| `CN115000123A(2023.05.01)` | 提取括号内日期作为公开日 |

**入库流程**：
1. 解析当前专利号 → 找/创建当前 `Patent` 记录
2. 解析同族号列表 → 为每个号找/创建 `Patent` 记录
3. 创建/复用 `PatentFamily`（family_id 用同族号列表的哈希作为族编号）
4. 把所有相关 `Patent.family_id` 指向同一个 family

### 3.5 引用专利列解析

类似同族，但写入 `Citation` 表：

- "引用专利"列：当前专利 → 引用列中的专利（`citing_patent_id = 当前`, `cited_patent_id = 列中专利`）
- "被引用专利"列：列中专利 → 引用当前专利（`citing_patent_id = 列中专利`, `cited_patent_id = 当前`）

被引用/同族的专利如果本地不存在，先创建一个**占位 Patent**（只有 `application_number` / `publication_number` + `is_duplicate=False` + `title="待补全"`），后续导入或外部 API 补全时再合并。

### 3.6 标准字段映射扩展

在 `STANDARD_FIELD_MAPPINGS` 中新增：

```python
"同族专利号": "family_members",       # 特殊处理，不直接写 Patent
"同族": "family_members",
"同族公开号": "family_members",
"引用专利": "cited_patents",          # 当前专利引用了这些专利
"引用专利号": "cited_patents",
"被引用专利": "citing_patents",       # 这些专利引用了当前专利
"被引用专利号": "citing_patents",
"引用文献": "cited_patents",
```

这些"虚拟字段"在 `_row_to_patent_data` 中被识别后，从 `patent_data` 移除，单独走关系入库流程。

---

## 四、patent_project 关联表多维属性扩展

### 4.1 表结构扩展

从 `Table` 升级为带 `id` 的关联模型（保持向后兼容）：

```python
class PatentProjectLink(Base):
    __tablename__ = "patent_projects"
    id = Column(Integer, primary_key=True, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    role = Column(SQLEnum(ProjectRole), default=ProjectRole.REFERENCE)
    # 新增多维属性
    relation_type = Column(String(50))       # risk / application / reference / defense
    risk_level = Column(SQLEnum(RiskLevel), default=RiskLevel.NONE)
    document_role = Column(String(50))       # core_patent / prior_art / file_wrapper / cited
    relevance_score = Column(Integer)        # 0-100，相关度评分
    importance = Column(String(20))          # S/A/B/C/D
    notes = Column(Text)
    assigned_to_id = Column(Integer, ForeignKey("people.id"))
    linked_at = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("patent_id", "project_id", name="_patent_project_uc"),)
```

### 4.2 兼容策略

旧表数据通过 Alembic 迁移转换。无 `relation_type` 的旧数据默认为 `reference`。

---

## 五、代码结构拆分（遵循 03-项目结构与代码规范.md）

### 5.1 models 目录拆分

当前 `models/__init__.py` 已达 407 行，超出 300 行限制。拆分如下：

```
backend/app/models/
├── __init__.py          # 仅 re-export，< 50 行
├── base.py              # Base 实例（从 database.py 导入）、公共 mixin
├── enums.py             # LegalStatus / PatentType / ProjectRole / RiskLevel / ImportBatchStatus / CustomFieldType
├── association.py       # patent_tag / patent_project 关联表（或 PatentProjectLink 模型）
├── organization.py      # Department / Person / ProductLine / Product
├── project.py           # Project
├── tag.py               # TagGroup / Tag
├── field.py             # CustomField
├── database.py          # PatentDatabase（新增）
├── patent.py            # Patent / PatentFamily / Citation
├── ai.py                # AITask / AIFieldValue
└── importing.py         # FieldMapping / ImportBatch
```

### 5.2 services 目录调整

```
backend/app/services/
├── __init__.py
├── patent_service.py        # 专利 CRUD（保持）
├── field_registry.py        # 字段元数据（保持）
├── field_service.py         # 自定义字段 CRUD（保持）
├── import_service.py        # 导入主流程（重构：拆出 merge_service）
├── merge_service.py         # 新增：Wiki 式字段合并逻辑
├── relation_service.py      # 新增：同族/引用关系解析与入库
├── database_service.py      # 新增：库 CRUD
├── project_service.py       # 项目（保持）
└── ...
```

### 5.3 API 层

新增 `backend/app/api/databases.py`：

```
GET    /databases                 列表
POST   /databases                 创建
GET    /databases/{id}            详情
PUT    /databases/{id}            更新
DELETE /databases/{id}            删除（仅空库可删）
GET    /databases/{id}/patents    库内专利列表（带分页/筛选）
POST   /databases/{id}/archive    归档
```

---

## 六、前端改造

### 6.1 ImportModal 流程改造

```
原流程：upload → mapping → processing → complete
新流程：chooseDatabase → upload → mapping → processing → complete
```

**chooseDatabase 步骤**：
- 上方"选择已有库"下拉
- 下方"创建新库"快捷表单（名称 + 描述）
- 选定/创建后才进入 upload 步骤

**mapping 步骤增强**：
- 未匹配列显示橙色"新建字段"徽章
- 已匹配列显示绿色"映射到 xxx"
- 顶部信息条："将自动创建 N 个新字段"

### 6.2 库切换器

- Sidebar 顶部增加库选择下拉（默认显示"默认数据库"）
- 切换后通过 store 更新 `currentDatabaseId`
- `PatentListPage` 查询时把 `database_id` 加入筛选

---

## 七、实施步骤（按任务 ID 对应）

### P0-8：拆分 models 目录 + 新增 PatentDatabase 模型
- 拆分 `models/__init__.py` 为 11 个子模块
- 新增 `models/database.py` 定义 `PatentDatabase`
- `models/patent.py` 给 `Patent` 增加 `database_id` 外键
- `__init__.py` 仅做 re-export，确保向后兼容（所有 `from app.models import X` 仍可用）
- 更新 `patwiki_backend.spec` 的 `hiddenimports`

### P0-9：扩展 patent_project 关联表
- `models/association.py` 用 `PatentProjectLink` 模型替代原 `Table`
- 增加多维属性字段
- 保持 SQLAlchemy relationship 配置正确

### P0-10：改造 import_service 为 Wiki 式增量合并
- 新增 `services/merge_service.py`：`merge_patent_data` 函数
- 新增 `services/relation_service.py`：同族/引用解析
- 改造 `import_service.suggest_mapping`：未知列自动创建 CustomField
- 改造 `_row_to_patent_data`：识别"虚拟字段"（family_members / cited_patents / citing_patents）从主数据剥离
- 改造 `api/imports.py` 的 confirm_import：使用 merge_service 替代 update_patent

### P0-11：新增 database_service + database API
- `services/database_service.py`：CRUD
- `api/databases.py`：路由
- `schemas/schemas.py`：增加 Database 相关 schema
- `api/api.py`：注册路由

### P0-12：前端 ImportModal + 库切换器改造
- `ImportModal.tsx` 新增 chooseDatabase 步骤
- `api/index.ts` 新增 `databaseApi`
- `types/index.ts` 新增 `PatentDatabase` 类型
- `Sidebar.tsx` 顶部增加库切换器
- `store/index.ts` 新增 `currentDatabaseId` 状态
- `PatentListPage.tsx` 查询参数加 `database_id`

---

## 八、验证清单

- [ ] 后端启动无报错（init_db 创建新表）
- [ ] `init_default_data` 自动创建"默认数据库"
- [ ] 前端 `npm run build` 0 错误
- [ ] 导入 Excel 时：
  - [ ] 第一步必须选择库
  - [ ] 未识别列显示"新建字段"标记
  - [ ] 重复专利字段级合并（已有标注保留）
  - [ ] 同族专利号列被解析，关系入库
  - [ ] 引用专利号列被解析，关系入库
- [ ] 切换库后表格只显示该库专利
- [ ] `patwiki_backend.spec` 包含新模块

---

*本文档为活文档，实施过程中如有调整需同步更新。*
