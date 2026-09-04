"""Reusable visibility predicates for the global patent index."""
from sqlalchemy import exists, or_

from app.models import Patent
from app.models.database_membership import PatentDatabaseMembership


def in_database(database_id: int):
    """Return a predicate that supports legacy and multi-database records."""
    return or_(
        Patent.database_id == database_id,
        exists().where(
            PatentDatabaseMembership.patent_id == Patent.id,
            PatentDatabaseMembership.database_id == database_id,
        ),
    )
