"""专利库（Database）API 路由——P0-11 新增。

库是专利数据的顶层品类容器。
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.database_service import DatabaseService

router = APIRouter(prefix="/databases", tags=["database"])


class DatabaseCreateRequest(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class DatabaseUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


@router.get("")
def list_databases(
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    databases = DatabaseService.list_databases(db, include_archived=include_archived)
    return [DatabaseService.to_dict(d) for d in databases]


@router.get("/default")
def get_default_database(db: Session = Depends(get_db)):
    database = DatabaseService.get_default_database(db)
    if not database:
        raise HTTPException(status_code=404, detail="未找到任何数据库")
    return DatabaseService.to_dict(database)


@router.post("")
def create_database(
    req: DatabaseCreateRequest,
    db: Session = Depends(get_db),
):
    database = DatabaseService.create_database(
        db,
        name=req.name,
        code=req.code,
        description=req.description,
        color=req.color,
        icon=req.icon,
    )
    return DatabaseService.to_dict(database)


@router.get("/{database_id}")
def get_database(
    database_id: int,
    db: Session = Depends(get_db),
):
    database = DatabaseService.get_database(db, database_id)
    if not database:
        raise HTTPException(status_code=404, detail="数据库不存在")
    return DatabaseService.to_dict(database)


@router.put("/{database_id}")
def update_database(
    database_id: int,
    req: DatabaseUpdateRequest,
    db: Session = Depends(get_db),
):
    database = DatabaseService.get_database(db, database_id)
    if not database:
        raise HTTPException(status_code=404, detail="数据库不存在")
    updated = DatabaseService.update_database(
        db,
        database,
        name=req.name,
        description=req.description,
        color=req.color,
        icon=req.icon,
        sort_order=req.sort_order,
    )
    return DatabaseService.to_dict(updated)


@router.post("/{database_id}/archive")
def archive_database(
    database_id: int,
    db: Session = Depends(get_db),
):
    database = DatabaseService.get_database(db, database_id)
    if not database:
        raise HTTPException(status_code=404, detail="数据库不存在")
    if database.is_default:
        raise HTTPException(status_code=400, detail="默认数据库不可归档")
    archived = DatabaseService.archive_database(db, database)
    return DatabaseService.to_dict(archived)


@router.delete("/{database_id}")
def delete_database(
    database_id: int,
    db: Session = Depends(get_db),
):
    database = DatabaseService.get_database(db, database_id)
    if not database:
        raise HTTPException(status_code=404, detail="数据库不存在")
    ok = DatabaseService.delete_database(db, database)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="删除失败：库中仍有专利或为默认库（请先迁移专利或归档）",
        )
    return {"success": True}


@router.post("/{database_id}/refresh-count")
def refresh_patent_count(
    database_id: int,
    db: Session = Depends(get_db),
):
    count = DatabaseService.refresh_patent_count(db, database_id)
    return {"success": True, "patent_count": count}
