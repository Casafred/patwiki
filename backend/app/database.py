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
        # P2-2：ImportBatch 增加库/视图/视图本地字段计数/触发者字段
        ("import_batches", "database_id",
         "ALTER TABLE import_batches ADD COLUMN database_id INTEGER REFERENCES patent_databases(id)"),
        ("import_batches", "view_id",
         "ALTER TABLE import_batches ADD COLUMN view_id INTEGER REFERENCES patent_views(id)"),
        ("import_batches", "view_local_written",
         "ALTER TABLE import_batches ADD COLUMN view_local_written INTEGER DEFAULT 0"),
        ("import_batches", "dedupe_by",
         "ALTER TABLE import_batches ADD COLUMN dedupe_by VARCHAR(20) DEFAULT 'both'"),
        ("import_batches", "triggered_by",
         "ALTER TABLE import_batches ADD COLUMN triggered_by VARCHAR(100)"),
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

        # P2-2：import_batches.database_id / view_id 索引
        if not has_index("import_batches", "ix_import_batches_database_id"):
            try:
                conn.execute(text("CREATE INDEX ix_import_batches_database_id ON import_batches (database_id)"))
            except Exception:
                pass
        if not has_index("import_batches", "ix_import_batches_view_id"):
            try:
                conn.execute(text("CREATE INDEX ix_import_batches_view_id ON import_batches (view_id)"))
            except Exception:
                pass


def init_db():
    import app.models
    Base.metadata.create_all(bind=engine)
    _ensure_column_migration()
