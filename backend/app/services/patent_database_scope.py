"""Reusable visibility predicates for the global patent index."""
from sqlalchemy import exists, or_

from app.models import Patent, PatentDatabase
from app.models.database_membership import PatentDatabaseMembership


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
