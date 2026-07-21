"""专利库（Database）API 路由——P0-11 新增。

库是专利数据的顶层品类容器。
P0-13：新增 /databases/{id}/master-view 端点，获取或创建部门总表视图。
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.database_service import DatabaseService
from app.services.view_service import ViewService
from app.models import User

router = APIRouter(prefix="/databases", tags=["database"])


class DatabaseCreateRequest(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    owner_id: Optional[int] = None


class DatabaseUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class SetOwnerRequest(BaseModel):
    user_id: int


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
    # 校验 owner_id
    owner_id = req.owner_id
    if owner_id is not None:
        if not db.query(User).filter(User.id == owner_id).first():
            raise HTTPException(status_code=400, detail=f"用户不存在：{owner_id}")
    database = DatabaseService.create_database(
        db,
        name=req.name,
        code=req.code,
        description=req.description,
        color=req.color,
        icon=req.icon,
        owner_id=owner_id,
    )
    return DatabaseService.to_dict(database)


@router.post("/{database_id}/set-owner")
def set_owner(
    database_id: int,
    req: SetOwnerRequest,
    db: Session = Depends(get_db),
):
    """设置/转移库的所有者"""
    database = DatabaseService.get_database(db, database_id)
    if not database:
        raise HTTPException(status_code=404, detail="数据库不存在")
    if not db.query(User).filter(User.id == req.user_id).first():
        raise HTTPException(status_code=400, detail=f"用户不存在：{req.user_id}")
    updated = DatabaseService.set_owner(db, database, req.user_id)
    return DatabaseService.to_dict(updated)


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
    force: bool = False,
    db: Session = Depends(get_db),
):
    """删除库。

    - force=False（默认）：库中有专利时返回 400，需先迁移或清空。
    - force=True：级联删除库内所有专利后删库（用于"整库删除"场景）。
    默认库不可删。
    """
    database = DatabaseService.get_database(db, database_id)
    if not database:
        raise HTTPException(status_code=404, detail="数据库不存在")
    if database.is_default:
        raise HTTPException(status_code=400, detail="默认数据库不可删除")
    # 先查专利数，给前端更友好的提示
    from app.models import Patent as PatentModel
    from sqlalchemy import func as _func
    patent_count = db.query(_func.count(PatentModel.id)).filter(PatentModel.database_id == database_id).scalar()
    if patent_count and patent_count > 0 and not force:
        raise HTTPException(
            status_code=400,
            detail=f"库中仍有 {patent_count} 条专利，无法直接删除。请先清空专利，或使用 force=true 级联删除（将一并删除所有专利）。",
        )
    ok = DatabaseService.delete_database(db, database, force=force)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="删除失败（可能为默认库或发生异常）",
        )
    return {"success": True, "force": force, "deleted_patent_count": patent_count or 0}


@router.post("/{database_id}/refresh-count")
def refresh_patent_count(
    database_id: int,
    db: Session = Depends(get_db),
):
    count = DatabaseService.refresh_patent_count(db, database_id)
    return {"success": True, "patent_count": count}


@router.get("/{database_id}/master-view")
def get_or_create_master_view(database_id: int, db: Session = Depends(get_db)):
    """获取或创建某库的部门总表视图。

    每个库应有且仅有一个 is_department_master=True 的视图。
    若不存在则自动创建，使用全字段、全专利的默认配置。
    """
    database = DatabaseService.get_database(db, database_id)
    if not database:
        raise HTTPException(status_code=404, detail="数据库不存在")

    view = ViewService.get_department_master_view(db, database_id)
    if not view:
        view = ViewService.create_view(
            db,
            name=f"{database.name} - 部门总表",
            database_id=database_id,
            description="部门级综合全属性总表视图，汇总所有专利",
            view_type="department_master",
            is_department_master=True,
            filter_config={},
            column_config=[],
            sort_config={"sort_by": "filing_date", "sort_order": "desc"},
        )
    return ViewService.to_dict(view)
