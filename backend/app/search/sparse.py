from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


FTS_TABLE = "semantic_patent_fts_v2"
_fts_available_by_bind: dict[int, bool] = {}


def _connection_supports_fts5(db: Session) -> bool:
    bind = db.get_bind()
    bind_key = id(bind)
    if _fts_available_by_bind.get(bind_key) is False:
        return False
    try:
        db.execute(text(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5(
                patent_id UNINDEXED,
                title,
                abstract,
                claims,
                description_full,
                applicant,
                inventor,
                classifications,
                technical_text,
                tokenize='trigram'
            )
        """))
        db.execute(text(f"""
            CREATE TRIGGER IF NOT EXISTS semantic_patent_fts_ai AFTER INSERT ON patents BEGIN
                INSERT INTO {FTS_TABLE}(rowid, patent_id, title, abstract, claims, description_full, applicant, inventor, classifications, technical_text)
                VALUES (NEW.id, NEW.id, NEW.title, NEW.abstract, NEW.claims, NEW.description_full, NEW.applicant, NEW.inventor,
                    coalesce(NEW.ipc_main, '') || ' ' || coalesce(NEW.ipc_all, '') || ' ' || coalesce(NEW.cpc_main, '') || ' ' || coalesce(NEW.cpc_all, ''),
                    coalesce(NEW.technical_problem, '') || ' ' || coalesce(NEW.technical_solution, '') || ' ' || coalesce(NEW.technical_effect, '') || ' ' || coalesce(NEW.module, ''));
            END
        """))
        db.execute(text(f"""
            CREATE TRIGGER IF NOT EXISTS semantic_patent_fts_ad AFTER DELETE ON patents BEGIN
                DELETE FROM {FTS_TABLE} WHERE rowid = OLD.id;
            END
        """))
        db.execute(text(f"""
            CREATE TRIGGER IF NOT EXISTS semantic_patent_fts_au AFTER UPDATE OF title, abstract, claims, description_full, applicant, inventor, ipc_main, ipc_all, cpc_main, cpc_all, technical_problem, technical_solution, technical_effect, module ON patents BEGIN
                DELETE FROM {FTS_TABLE} WHERE rowid = OLD.id;
                INSERT INTO {FTS_TABLE}(rowid, patent_id, title, abstract, claims, description_full, applicant, inventor, classifications, technical_text)
                VALUES (NEW.id, NEW.id, NEW.title, NEW.abstract, NEW.claims, NEW.description_full, NEW.applicant, NEW.inventor,
                    coalesce(NEW.ipc_main, '') || ' ' || coalesce(NEW.ipc_all, '') || ' ' || coalesce(NEW.cpc_main, '') || ' ' || coalesce(NEW.cpc_all, ''),
                    coalesce(NEW.technical_problem, '') || ' ' || coalesce(NEW.technical_solution, '') || ' ' || coalesce(NEW.technical_effect, '') || ' ' || coalesce(NEW.module, ''));
            END
        """))
        count = int(db.execute(text(f"SELECT COUNT(*) FROM {FTS_TABLE}")).scalar() or 0)
        patents = int(db.execute(text("SELECT COUNT(*) FROM patents")).scalar() or 0)
        if count != patents:
            db.execute(text(f"DELETE FROM {FTS_TABLE}"))
            db.execute(text(f"""
                INSERT INTO {FTS_TABLE}(rowid, patent_id, title, abstract, claims, description_full, applicant, inventor, classifications, technical_text)
                SELECT id, id, title, abstract, claims, description_full, applicant, inventor,
                    coalesce(ipc_main, '') || ' ' || coalesce(ipc_all, '') || ' ' || coalesce(cpc_main, '') || ' ' || coalesce(cpc_all, ''),
                    coalesce(technical_problem, '') || ' ' || coalesce(technical_solution, '') || ' ' || coalesce(technical_effect, '') || ' ' || coalesce(module, '')
                FROM patents
            """))
        _fts_available_by_bind[bind_key] = True
        return True
    except SQLAlchemyError:
        db.rollback()
        _fts_available_by_bind[bind_key] = False
        return False


def search(db: Session, query: str, limit: int, database_id: int | None = None) -> list[int]:
    """Return patent IDs ordered by SQLite FTS5 BM25 rank.

    FTS5 tokenization is intentionally allowed to fail for unsupported SQLite
    builds; callers retain the SQL keyword fallback in that case.
    """
    if not _connection_supports_fts5(db):
        return []
    query = query.strip().replace('"', ' ').replace("'", " ")
    if not query:
        return []
    try:
        scope_clause = ""
        params: dict[str, object] = {"query": query, "limit": limit}
        if database_id is not None:
            # Keep scope filtering inside the FTS query. Filtering only after
            # LIMIT can let records from another database consume candidates.
            scope_clause = """
                AND f.patent_id IN (
                    SELECT p.id
                    FROM patents AS p
                    WHERE p.database_id = :database_id
                       OR EXISTS (
                           SELECT 1
                           FROM patent_database_memberships AS m
                           WHERE m.patent_id = p.id AND m.database_id = :database_id
                       )
                )
            """
            params["database_id"] = database_id
        rows = db.execute(text(f"""
            SELECT f.patent_id
            FROM {FTS_TABLE} AS f
            WHERE {FTS_TABLE} MATCH :query
            {scope_clause}
            ORDER BY bm25({FTS_TABLE})
            LIMIT :limit
        """), params).all()
        return [int(row[0]) for row in rows]
    except SQLAlchemyError:
        db.rollback()
        return []


def status(db: Session) -> dict[str, bool | str]:
    available = _connection_supports_fts5(db)
    return {"backend": "fts5_trigram" if available else "ilike", "available": available}
