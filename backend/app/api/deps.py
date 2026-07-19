from typing import Generator
from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db


def get_pagination_params(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=1000, description="每页数量"),
):
    return {"page": page, "page_size": page_size}
