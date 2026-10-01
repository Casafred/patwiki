"""Reusable visibility predicates for the global patent index."""
from sqlalchemy import exists, or_, select

from app.models import Patent, PatentDatabase
from app.models.database_membership import PatentDatabaseMembership


def membership_consistency(db, database_id: int | None = None) -> dict:
    """Report legacy ownership rows missing their authoritative membership."""
    from app.models import Patent
    query = db.query(Patent.id, Patent.database_id).filter(Patent.database_id.is_not(None))
    if database_id is not None:
        query = query.filter(Patent.database_id == database_id)
    missing_query = query.filter(~exists().where(
        PatentDatabaseMembership.patent_id == Patent.id,
        PatentDatabaseMembership.database_id == Patent.database_id,
    ))
    missing = [{"patent_id": row[0], "database_id": row[1]} for row in missing_query.limit(1000).all()]
    return {"legacy_rows": query.count(), "missing_memberships": missing_query.count(), "items": missing}


def repair_membership_consistency(db, database_id: int | None = None) -> int:
    from app.models import Patent
    from sqlalchemy import insert
    query = select(Patent.id, Patent.database_id).where(Patent.database_id.is_not(None), ~exists().where(
        PatentDatabaseMembership.patent_id == Patent.id,
        PatentDatabaseMembership.database_id == Patent.database_id,
    ))
    if database_id is not None:
        query = query.where(Patent.database_id == database_id)
    result = db.execute(insert(PatentDatabaseMembership).from_select(["patent_id", "database_id"], query))
    repaired = result.rowcount
    db.commit()
    return repaired


def in_database(database_id: int):
    """Return the visibility predicate for a library.

    The default library is the canonical department-wide index. Its scope is
    every canonical patent, while regular libraries remain membership-scoped.
    """
    return or_(
        exists().where(
            PatentDatabase.id == database_id,
            PatentDatabase.is_default.is_(True),
        ),
        Patent.database_id == database_id,
        exists().where(
            PatentDatabaseMembership.patent_id == Patent.id,
            PatentDatabaseMembership.database_id == database_id,
        ),
    )
