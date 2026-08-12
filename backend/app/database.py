from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings


connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_column_migration():
    """SQLite 轻量级列迁移：create_all 不会修改已存在的表，需手动 ADD COLUMN。

    P0-8：patents.database_id
    P0-9：patent_projects.relation_type / risk_level / document_role / relevance_score / importance / assigned_to_id / linked_at
    P0-9：patent_projects.id（主键，旧表无此列时无法迁移主键，改为容忍式：不强制）
    """
    from sqlalchemy import text, inspect

    inspector = inspect(engine)

    def has_column(table: str, column: str) -> bool:
        if table not in inspector.get_table_names():
            return False
        return column in [c["name"] for c in inspector.get_columns(table)]

    def has_index(table: str, index_name: str) -> bool:
        if table not in inspector.get_table_names():
            return False
        return index_name in [i["name"] for i in inspector.get_indexes(table)]

    migrations = [
        # (table, column, ddl)
        ("patents", "database_id",
         "ALTER TABLE patents ADD COLUMN database_id INTEGER REFERENCES patent_databases(id)"),
        ("patent_projects", "relation_type", "ALTER TABLE patent_projects ADD COLUMN relation_type VARCHAR(20)"),
        ("patent_projects", "risk_level", "ALTER TABLE patent_projects ADD COLUMN risk_level VARCHAR(20)"),
        ("patent_projects", "document_role", "ALTER TABLE patent_projects ADD COLUMN document_role VARCHAR(50)"),
        ("patent_projects", "relevance_score", "ALTER TABLE patent_projects ADD COLUMN relevance_score INTEGER"),
        ("patent_projects", "importance", "ALTER TABLE patent_projects ADD COLUMN importance VARCHAR(20)"),
        ("patent_projects", "assigned_to_id", "ALTER TABLE patent_projects ADD COLUMN assigned_to_id INTEGER REFERENCES people(id)"),
        ("patent_projects", "linked_at", "ALTER TABLE patent_projects ADD COLUMN linked_at DATETIME"),
        ("patent_projects", "created_at_p9", "ALTER TABLE patent_projects ADD COLUMN created_at_p9 DATETIME"),
        ("patent_projects", "updated_at_p9", "ALTER TABLE patent_projects ADD COLUMN updated_at_p9 DATETIME"),
        # 权限管理 MVP：库的所有者
        ("patent_databases", "owner_id",
         "ALTER TABLE patent_databases ADD COLUMN owner_id INTEGER REFERENCES users(id)"),
        # P0-13：PatentHistory 增加来源视图字段
        ("patent_histories", "source_view_id",
         "ALTER TABLE patent_histories ADD COLUMN source_view_id INTEGER REFERENCES patent_views(id)"),
        ("patent_histories", "source_view_name",
         "ALTER TABLE patent_histories ADD COLUMN source_view_name VARCHAR(200)"),
        # 视图展示类型与多维视图配置。view_type 继续保留为可见范围。
        ("patent_views", "layout_type",
         "ALTER TABLE patent_views ADD COLUMN layout_type VARCHAR(30) DEFAULT 'table'"),
        ("patent_views", "group_by_config",
         "ALTER TABLE patent_views ADD COLUMN group_by_config JSON"),
        ("patent_views", "conditional_formatting",
         "ALTER TABLE patent_views ADD COLUMN conditional_formatting JSON"),
        ("patent_views", "kanban_config",
         "ALTER TABLE patent_views ADD COLUMN kanban_config JSON"),
        ("patent_views", "form_config",
         "ALTER TABLE patent_views ADD COLUMN form_config JSON"),
        ("patent_views", "gantt_config",
         "ALTER TABLE patent_views ADD COLUMN gantt_config JSON"),
        # M3：通用关联字段配置
        ("custom_fields", "link_config",
         "ALTER TABLE custom_fields ADD COLUMN link_config JSON"),
        ("custom_fields", "lookup_config",
         "ALTER TABLE custom_fields ADD COLUMN lookup_config JSON"),
        ("custom_fields", "rollup_config",
         "ALTER TABLE custom_fields ADD COLUMN rollup_config JSON"),
        ("custom_fields", "formula_config",
         "ALTER TABLE custom_fields ADD COLUMN formula_config JSON"),
        # P0-14：专利归属视图（导入到指定视图）
        ("patents", "view_id",
         "ALTER TABLE patents ADD COLUMN view_id INTEGER REFERENCES patent_views(id)"),
        # P0-14：人员与用户打通
        ("people", "user_id",
         "ALTER TABLE people ADD COLUMN user_id INTEGER REFERENCES users(id)"),
        # 用户与部门打通
        ("users", "department_id",
         "ALTER TABLE users ADD COLUMN department_id INTEGER REFERENCES departments(id)"),
        ("users", "employee_no", "ALTER TABLE users ADD COLUMN employee_no VARCHAR(50)"),
        ("users", "group_id", "ALTER TABLE users ADD COLUMN group_id INTEGER REFERENCES departments(id)"),
        ("users", "product_line_id", "ALTER TABLE users ADD COLUMN product_line_id INTEGER REFERENCES product_lines(id)"),
        ("users", "organization_role", "ALTER TABLE users ADD COLUMN organization_role VARCHAR(100)"),
        ("departments", "code", "ALTER TABLE departments ADD COLUMN code VARCHAR(50)"),
        ("departments", "department_type", "ALTER TABLE departments ADD COLUMN department_type VARCHAR(30) DEFAULT 'other'"),
        ("departments", "parent_id", "ALTER TABLE departments ADD COLUMN parent_id INTEGER REFERENCES departments(id)"),
        ("product_lines", "department_id", "ALTER TABLE product_lines ADD COLUMN department_id INTEGER REFERENCES departments(id)"),
    ]

    with engine.begin() as conn:
        for table, column, ddl in migrations:
            actual_col = column if not column.endswith("_p9") else column[:-3]
            if not has_column(table, actual_col):
                try:
                    conn.execute(text(ddl))
                except Exception:
                    # 列已存在或语法不兼容时跳过
                    pass

        # patents.database_id 索引
        if not has_index("patents", "ix_patents_database_id"):
            try:
                conn.execute(text("CREATE INDEX ix_patents_database_id ON patents (database_id)"))
            except Exception:
                pass

        # patent_databases.owner_id 索引
        if not has_index("patent_databases", "ix_patent_databases_owner_id"):
            try:
                conn.execute(text("CREATE INDEX ix_patent_databases_owner_id ON patent_databases (owner_id)"))
            except Exception:
                pass

        # P0-13：patent_histories.source_view_id 索引
        if not has_index("patent_histories", "ix_patent_histories_source_view_id"):
            try:
                conn.execute(text("CREATE INDEX ix_patent_histories_source_view_id ON patent_histories (source_view_id)"))
            except Exception:
                pass

        # P0-14：patents.view_id 索引
        if not has_index("patents", "ix_patents_view_id"):
            try:
                conn.execute(text("CREATE INDEX ix_patents_view_id ON patents (view_id)"))
            except Exception:
                pass

        # P0-14：people.user_id 索引
        if not has_index("people", "ix_people_user_id"):
            try:
                conn.execute(text("CREATE INDEX ix_people_user_id ON people (user_id)"))
            except Exception:
                pass

        # 用户与部门打通：users.department_id 索引
        if not has_index("users", "ix_users_department_id"):
            try:
                conn.execute(text("CREATE INDEX ix_users_department_id ON users (department_id)"))
            except Exception:
                pass
        for table, index_name, column in [
            ("users", "ix_users_employee_no", "employee_no"),
            ("users", "ix_users_group_id", "group_id"),
            ("users", "ix_users_product_line_id", "product_line_id"),
            ("departments", "ix_departments_parent_id", "parent_id"),
            ("product_lines", "ix_product_lines_department_id", "department_id"),
        ]:
            if not has_index(table, index_name):
                try:
                    conn.execute(text(f"CREATE INDEX {index_name} ON {table} ({column})"))
                except Exception:
                    pass


def init_db():
    import app.models
    Base.metadata.create_all(bind=engine)
    _ensure_column_migration()
    _ensure_master_views()


def _ensure_master_views():
    """P0-14：为已有库补建主视图（建库时自动创建，此函数兼容历史库）。"""
    try:
        from app.services.database_service import DatabaseService
        from app.services.view_service import ViewService
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            for d in DatabaseService.list_databases(db, include_archived=True):
                if not ViewService.get_department_master_view(db, d.id):
                    ViewService.create_view(
                        db,
                        name=f"{d.name} · 主表",
                        database_id=d.id,
                        view_type="department_master",
                        is_department_master=True,
                        filter_config={},
                        column_config=[],
                        sort_config={"sort_by": "filing_date", "sort_order": "desc"},
                    )
        finally:
            db.close()
    except Exception:
        # 启动期不因补建视图失败而中断
        pass
