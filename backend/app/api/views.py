"""视图（小表/部门总表）API 路由——P0-13 新增。

路由组织：
- /views                                 视图 CRUD
- /views/{view_id}/patents               视图中的专利列表
- /views/{view_id}/patents/{pid}/field/{key}    在视图中编辑共享字段（写入大表+记录来源）
- /views/{view_id}/local-fields          视图本地字段 CRUD
- /views/{view_id}/local-fields/{fid}/values/{pid}   设置视图本地字段值
- /views/{view_id}/local-fields/{fid}/promote    提升为全局字段
- /databases/{db_id}/master-view         获取/创建部门总表视图
- /patents/{pid}/field-sources           字段来源追溯
"""
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Optional
import json

from app.database import get_db
from app.api.deps import get_pagination_params
from app.schemas.schemas import (
    PatentView, PatentViewCreate, PatentViewUpdate,
    ViewLocalField, ViewLocalFieldCreate, ViewLocalFieldUpdate,
    ViewFieldValueUpdate, ViewPatentCellUpdate,
    PromoteFieldRequest, FieldSourceInfo,
)
from app.services.view_service import ViewService
from app.models import PatentView, ViewLocalField

router = APIRouter(prefix="/views", tags=["views"])


# ========== 视图 CRUD ==========

@router.get("")
def list_views(
    database_id: Optional[int] = None,
    owner_id: Optional[int] = None,
    view_type: Optional[str] = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    """列出视图。"""
    views = ViewService.list_views(
        db,
        database_id=database_id,
        owner_id=owner_id,
        include_archived=include_archived,
        view_type=view_type,
    )
    return [ViewService.to_dict(v) for v in views]


@router.post("")
def create_view(view_in: PatentViewCreate, db: Session = Depends(get_db)):
    try:
        view = ViewService.create_view(
            db,
            name=view_in.name,
            database_id=view_in.database_id,
            description=view_in.description,
            owner_id=None,
            view_type=view_in.view_type or "personal",
            filter_config=view_in.filter_config,
            column_config=view_in.column_config,
            sort_config=view_in.sort_config,
            is_department_master=view_in.is_department_master or False,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ViewService.to_dict(view)


@router.get("/{view_id}")
def get_view(view_id: int, db: Session = Depends(get_db)):
    view = ViewService.get_view(db, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    return ViewService.to_dict(view)


@router.put("/{view_id}")
def update_view(view_id: int, view_in: PatentViewUpdate, db: Session = Depends(get_db)):
    view = ViewService.get_view(db, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    updates = view_in.model_dump(exclude_unset=True)
    view = ViewService.update_view(db, view, updates)
    return ViewService.to_dict(view)


@router.delete("/{view_id}")
def delete_view(view_id: int, db: Session = Depends(get_db)):
    view = ViewService.get_view(db, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    if not ViewService.delete_view(db, view):
        raise HTTPException(status_code=400, detail="部门总表视图不允许删除")
    return {"success": True}


@router.post("/{view_id}/archive")
def archive_view(view_id: int, db: Session = Depends(get_db)):
    view = ViewService.get_view(db, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    if view.is_department_master:
        raise HTTPException(status_code=400, detail="部门总表视图不允许归档")
    ViewService.archive_view(db, view)
    return ViewService.to_dict(view)


# ========== 视图数据查询 ==========

@router.get("/{view_id}/patents")
def list_view_patents(
    view_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    extra_filters: Optional[str] = Query(None, description="JSON 字符串：临时筛选，与视图自身 filter 合并"),
    db: Session = Depends(get_db),
):
    view = ViewService.get_view(db, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")

    ef = None
    if extra_filters:
        try:
            ef = json.loads(extra_filters)
        except (json.JSONDecodeError, TypeError):
            ef = None

    patents, total = ViewService.list_view_patents(
        db, view, page=page, page_size=page_size, extra_filters=ef,
    )

    # 返回时附带视图本地字段值
    items = []
    for p in patents:
        item = ViewService.get_view_patent_with_local_fields(db, view, p)
        items.append(item)

    return {
        "total": total,
        "items": items,
        "page": page,
        "page_size": page_size,
        "view_id": view_id,
        "view_filter_config": view.filter_config or {},
        "view_column_config": view.column_config or [],
    }


@router.patch("/{view_id}/patents/{patent_id}/field/{field_key}")
def update_patent_field_in_view(
    view_id: int,
    patent_id: int,
    field_key: str,
    body: ViewPatentCellUpdate = Body(...),
    db: Session = Depends(get_db),
):
    """在视图中编辑共享字段——写入大表并记录来源视图。

    P1-10：此端点保留为视图语义入口，但实际逻辑已合并到
    PATCH /patents/{pid}/field/{key}（接受 source_view_id）。
    内部直接复用 ViewService.update_shared_field_in_view 调用统一的 PatentService.update_patent。
    """
    view = ViewService.get_view(db, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    try:
        patent = ViewService.update_shared_field_in_view(
            db, view, patent_id, field_key, body.value, changed_by=body.changed_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "success": True,
        "patent_id": patent.id,
        "field_key": field_key,
        "source_view_id": view.id,
        "source_view_name": view.name,
    }


# ========== 视图本地字段 CRUD ==========

@router.get("/{view_id}/local-fields")
def list_local_fields(view_id: int, db: Session = Depends(get_db)):
    view = ViewService.get_view(db, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    return [ViewService.local_field_to_dict(f) for f in view.local_fields]


@router.post("/{view_id}/local-fields")
def create_local_field(
    view_id: int,
    field_in: ViewLocalFieldCreate,
    db: Session = Depends(get_db),
):
    view = ViewService.get_view(db, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    try:
        field = ViewService.create_local_field(
            db, view,
            key=field_in.key,
            name=field_in.name,
            field_type=field_in.field_type,
            options=field_in.options,
            description=field_in.description,
            default_value=field_in.default_value,
            is_required=field_in.is_required or False,
            sort_order=field_in.sort_order,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ViewService.local_field_to_dict(field)


@router.put("/{view_id}/local-fields/{field_id}")
def update_local_field(
    view_id: int,
    field_id: int,
    field_in: ViewLocalFieldUpdate,
    db: Session = Depends(get_db),
):
    field = db.query(ViewLocalField).filter(
        ViewLocalField.id == field_id,
        ViewLocalField.view_id == view_id,
    ).first()
    if not field:
        raise HTTPException(status_code=404, detail="Local field not found")
    updates = field_in.model_dump(exclude_unset=True)
    field = ViewService.update_local_field(db, field, updates)
    return ViewService.local_field_to_dict(field)


@router.delete("/{view_id}/local-fields/{field_id}")
def delete_local_field(view_id: int, field_id: int, db: Session = Depends(get_db)):
    field = db.query(ViewLocalField).filter(
        ViewLocalField.id == field_id,
        ViewLocalField.view_id == view_id,
    ).first()
    if not field:
        raise HTTPException(status_code=404, detail="Local field not found")
    if not ViewService.delete_local_field(db, field):
        raise HTTPException(status_code=400, detail="已提升的字段不允许直接删除，请先取消提升")
    return {"success": True}


# ========== 视图本地字段值 ==========

@router.put("/{view_id}/local-fields/{field_key}/values/{patent_id}")
def set_local_field_value(
    view_id: int,
    field_key: str,
    patent_id: int,
    body: ViewFieldValueUpdate = Body(...),
    db: Session = Depends(get_db),
):
    view = ViewService.get_view(db, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    try:
        vfv = ViewService.set_local_field_value(
            db, view, patent_id, field_key, body.value, changed_by=body.changed_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "success": True,
        "patent_id": vfv.patent_id,
        "view_id": vfv.view_id,
        "field_key": vfv.field_key,
        "value": vfv.value,
    }


@router.get("/{view_id}/local-fields/{field_key}/values/{patent_id}")
def get_local_field_value(
    view_id: int,
    field_key: str,
    patent_id: int,
    db: Session = Depends(get_db),
):
    view = ViewService.get_view(db, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    values = ViewService.get_local_field_values(db, view, patent_id)
    return {
        "patent_id": patent_id,
        "view_id": view_id,
        "field_key": field_key,
        "value": values.get(field_key),
    }


# ========== 字段提升（Promote） ==========

@router.post("/{view_id}/local-fields/{field_id}/promote")
def promote_local_field(
    view_id: int,
    field_id: int,
    body: PromoteFieldRequest = Body(default=PromoteFieldRequest()),
    db: Session = Depends(get_db),
):
    view = ViewService.get_view(db, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    field = db.query(ViewLocalField).filter(
        ViewLocalField.id == field_id,
        ViewLocalField.view_id == view_id,
    ).first()
    if not field:
        raise HTTPException(status_code=404, detail="Local field not found")
    if field.is_promoted:
        raise HTTPException(status_code=400, detail=f"字段已提升为全局字段：{field.promoted_field_key}")
    cf = ViewService.promote_local_field(
        db, view, field,
        global_name=body.global_name,
        global_group=body.global_group or "从小表提升",
    )
    return {
        "success": True,
        "global_field_key": cf.key,
        "global_field_name": cf.name,
        "global_field_id": cf.id,
        "source_view_id": view.id,
        "source_view_name": view.name,
    }


# 注意：部门总表视图的获取/创建端点 /databases/{id}/master-view
# 已在 app/api/databases.py 中定义（更符合 REST 路径层级）
