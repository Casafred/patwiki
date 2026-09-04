"""Database engine, session dependency and startup migration boundary."""
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings


connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """SQLite disables FK enforcement by default; every connection opts in."""
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize schema through the versioned migration safety platform.

    MigrationError intentionally escapes this function. A local database
    cannot safely serve requests when its schema upgrade failed.
    """
    import app.models  # noqa: F401 - registers every model with Base.metadata
    from app.services.migration_service import run_pending_migrations

    run_pending_migrations(engine)
    _ensure_master_views()


def _ensure_master_views():
    """Backfill the default master view for existing databases."""
    from app.services.database_service import DatabaseService
    from app.services.view_service import ViewService

    db = SessionLocal()
    try:
        _backfill_database_memberships(db)
        for database in DatabaseService.list_databases(db, include_archived=True):
            if not ViewService.get_department_master_view(db, database.id):
                ViewService.create_view(
                    db,
                    name=f"{database.name} · 主表",
                    database_id=database.id,
                    view_type="department_master",
                    is_department_master=True,
                    filter_config={},
                    column_config=[],
                    sort_config={"sort_by": "filing_date", "sort_order": "desc"},
                )
    finally:
        db.close()


def _backfill_database_memberships(db):
    """Backfill the multi-database visibility projection once at startup."""
    from app.models import Patent, PatentDatabaseMembership

    rows = db.query(Patent.id, Patent.database_id).filter(Patent.database_id.isnot(None)).all()
    if not rows:
        return
    existing = {
        (patent_id, database_id)
        for patent_id, database_id in db.query(
            PatentDatabaseMembership.patent_id,
            PatentDatabaseMembership.database_id,
        ).all()
    }
    additions = [
        PatentDatabaseMembership(patent_id=patent_id, database_id=database_id)
        for patent_id, database_id in rows
        if (patent_id, database_id) not in existing
    ]
    if additions:
        db.add_all(additions)
        db.commit()
