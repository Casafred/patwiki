"""视图（小表）服务——P0-13 新增。

核心架构：单源大表 + 视图小表（Master + View）
- 视图是 PatentDatabase（大表）上的"保存的查询"：filter + column_config + sort
- 共享字段编辑实时写入大表，并在 PatentHistory 中记录来源视图
- 视图本地字段独立存储，不污染大表
- 视图本地字段可一键 promote 为全局 CustomField（同时在历史中注明来源视图）
"""
import hashlib
from typing import Optional, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models import (
    PatentView, ViewLocalField, PatentViewFieldValue,
    Patent, CustomField, PatentHistory, PatentDatabase,
    DatabaseMembership,
)
from app.services.patent_service import PatentService
from app.services.field_registry import get_all_fields_meta


class ViewService:
    # ========== 视图 CRUD ==========

    @staticmethod
    def list_views(
        db: Session,
        database_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        include_archived: bool = False,
        view_type: Optional[str] = None,
    ) -> list[PatentView]:
        """列出视图。

        - 不传 owner_id：返回该库所有视图（部门总表 + 共享 + 所有人个人视图）
        - 传 owner_id：返回该用户可见的视图（自己拥有的 + shared + department_master）
        """
        query = db.query(PatentView)
        if database_id is not None:
            query = query.filter(PatentView.database_id == database_id)
        if not include_archived:
            query = query.filter(PatentView.is_archived == False)
        if view_type:
            query = query.filter(PatentView.view_type == view_type)
        if owner_id is not None:
            # 自己拥有的 + 共享的 + 部门总表
            query = query.filter(
                (PatentView.owner_id == owner_id) |
                (PatentView.view_type == "shared") |
                (PatentView.view_type == "department_master")
            )
        query = query.order_by(
            PatentView.is_department_master.desc(),  # 部门总表优先
            PatentView.view_type,  # shared 次之
            PatentView.updated_at.desc(),
        )
        return query.all()

    @staticmethod
    def get_view(db: Session, view_id: int) -> Optional[PatentView]:
        return db.query(PatentView).filter(PatentView.id == view_id).first()

    @staticmethod
    def get_department_master_view(db: Session, database_id: int) -> Optional[PatentView]:
        """获取某库的部门总表视图（每个库应有唯一一个）。"""
        return db.query(PatentView).filter(
            PatentView.database_id == database_id,
            PatentView.is_department_master == True,
        ).first()

    @staticmethod
    def create_view(
        db: Session,
        name: str,
        database_id: int,
        description: Optional[str] = None,
        owner_id: Optional[int] = None,
        view_type: str = "personal",
        filter_config: Optional[dict] = None,
        column_config: Optional[list] = None,
        sort_config: Optional[dict] = None,
        is_department_master: bool = False,
    ) -> PatentView:
        # 部门总表视图每库唯一
        if is_department_master:
            existing = ViewService.get_department_master_view(db, database_id)
            if existing:
                raise ValueError(f"库 {database_id} 已存在部门总表视图（id={existing.id}）")
            view_type = "department_master"

        view = PatentView(
            name=name,
            description=description,
            database_id=database_id,
            owner_id=owner_id,
            view_type=view_type,
            is_department_master=is_department_master,
            filter_config=filter_config or {},
            column_config=column_config or [],
            sort_config=sort_config or {},
        )
        db.add(view)
        db.commit()
        db.refresh(view)
        return view

    @staticmethod
    def update_view(db: Session, view: PatentView, updates: dict) -> PatentView:
        for k, v in updates.items():
            if v is not None and hasattr(view, k):
                setattr(view, k, v)
        db.add(view)
        db.commit()
        db.refresh(view)
        return view

    @staticmethod
    def archive_view(db: Session, view: PatentView) -> PatentView:
        view.is_archived = True
        db.add(view)
        db.commit()
        db.refresh(view)
        return view

    @staticmethod
    def delete_view(db: Session, view: PatentView) -> bool:
        # 部门总表视图不允许删除
        if view.is_department_master:
            return False
        db.delete(view)
        db.commit()
        return True

    @staticmethod
    def to_dict(view: PatentView, include_fields: bool = True) -> dict:
        result = {
            "id": view.id,
            "name": view.name,
            "description": view.description,
            "database_id": view.database_id,
            "owner_id": view.owner_id,
            "view_type": view.view_type,
            "is_department_master": view.is_department_master,
            "is_archived": view.is_archived,
            "filter_config": view.filter_config or {},
            "column_config": view.column_config or [],
            "sort_config": view.sort_config or {},
            "created_at": view.created_at.isoformat() if view.created_at else None,
            "updated_at": view.updated_at.isoformat() if view.updated_at else None,
        }
        if include_fields:
            result["local_fields"] = [
                ViewService.local_field_to_dict(f) for f in view.local_fields
            ]
        return result

    # ========== 视图数据查询 ==========

    @staticmethod
    def list_view_patents(
        db: Session,
        view: PatentView,
        page: int = 1,
        page_size: int = 50,
        extra_filters: Optional[dict] = None,
    ) -> tuple[list[Patent], int]:
        """获取视图中的专利列表。

        - 应用视图自身的 filter_config
        - 合并 extra_filters（前端临时筛选）
        - 应用视图的 sort_config 作为默认排序
        """
        merged_filters = dict(view.filter_config or {})
        if extra_filters:
            merged_filters.update(extra_filters)

        sort_by = (view.sort_config or {}).get("sort_by")
        sort_order = (view.sort_config or {}).get("sort_order", "asc")

        patents, total = PatentService.list_patents(
            db,
            page=page,
            page_size=page_size,
            database_id=view.database_id,
            filters=merged_filters if merged_filters else None,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return patents, total

    @staticmethod
    def get_view_patent_with_local_fields(
        db: Session, view: PatentView, patent: Patent
    ) -> dict:
        """返回单个专利在视图中可见的所有字段值（共享字段 + 视图本地字段）。"""
        # 共享字段：直接读 Patent
        patent_dict = _patent_to_dict(patent)

        # 视图本地字段：从 PatentViewFieldValue 读
        local_values = db.query(PatentViewFieldValue).filter(
            PatentViewFieldValue.patent_id == patent.id,
            PatentViewFieldValue.view_id == view.id,
        ).all()
        local_values_map = {lv.field_key: lv.value for lv in local_values}

        # 拼装：view_local.{key}
        patent_dict["view_local_fields"] = {
            f.key: local_values_map.get(f.key) for f in view.local_fields
        }
        return patent_dict

    # ========== 视图本地字段 CRUD ==========

    @staticmethod
    def create_local_field(
        db: Session,
        view: PatentView,
        key: str,
        name: str,
        field_type: str,
        options: Optional[list] = None,
        description: Optional[str] = None,
        default_value: Optional[str] = None,
        is_required: bool = False,
        sort_order: Optional[int] = None,
    ) -> ViewLocalField:
        # key 唯一性：vlf_ 前缀 + 短哈希
        if not key.startswith("vlf_"):
            key = f"vlf_{key}"
        existing = db.query(ViewLocalField).filter(
            ViewLocalField.view_id == view.id,
            ViewLocalField.key == key,
        ).first()
        if existing:
            raise ValueError(f"视图 {view.id} 已存在字段 key={key}")

        if sort_order is None:
            sort_order = (db.query(func.count(ViewLocalField.id))
                          .filter(ViewLocalField.view_id == view.id).scalar() or 0)

        field = ViewLocalField(
            view_id=view.id,
            key=key,
            name=name,
            field_type=field_type,
            options=options,
            description=description,
            default_value=default_value,
            is_required=is_required,
            sort_order=sort_order,
        )
        db.add(field)
        db.commit()
        db.refresh(field)
        return field

    @staticmethod
    def update_local_field(db: Session, field: ViewLocalField, updates: dict) -> ViewLocalField:
        for k, v in updates.items():
            if v is not None and hasattr(field, k):
                setattr(field, k, v)
        db.add(field)
        db.commit()
        db.refresh(field)
        return field

    @staticmethod
    def delete_local_field(db: Session, field: ViewLocalField) -> bool:
        # 已提升的字段不允许直接删除（需先取消提升）
        if field.is_promoted:
            return False
        # 删除字段值
        db.query(PatentViewFieldValue).filter(
            PatentViewFieldValue.view_id == field.view_id,
            PatentViewFieldValue.field_key == field.key,
        ).delete()
        db.delete(field)
        db.commit()
        return True

    @staticmethod
    def local_field_to_dict(field: ViewLocalField) -> dict:
        return {
            "id": field.id,
            "view_id": field.view_id,
            "key": field.key,
            "name": field.name,
            "field_type": field.field_type,
            "options": field.options,
            "description": field.description,
            "default_value": field.default_value,
            "is_required": field.is_required,
            "sort_order": field.sort_order,
            "is_promoted": field.is_promoted,
            "promoted_field_key": field.promoted_field_key,
            "created_at": field.created_at.isoformat() if field.created_at else None,
            "updated_at": field.updated_at.isoformat() if field.updated_at else None,
        }

    # ========== 视图本地字段值 ==========

    @staticmethod
    def set_local_field_value(
        db: Session,
        view: PatentView,
        patent_id: int,
        field_key: str,
        value: Any,
        changed_by: Optional[str] = None,
    ) -> PatentViewFieldValue:
        """设置视图本地字段值（不影响大表）。"""
        # 校验 field_key 属于该视图
        field = db.query(ViewLocalField).filter(
            ViewLocalField.view_id == view.id,
            ViewLocalField.key == field_key,
        ).first()
        if not field:
            raise ValueError(f"视图 {view.id} 无本地字段 {field_key}")

        existing = db.query(PatentViewFieldValue).filter(
            PatentViewFieldValue.patent_id == patent_id,
            PatentViewFieldValue.view_id == view.id,
            PatentViewFieldValue.field_key == field_key,
        ).first()

        if existing:
            existing.value = _stringify(value)
            existing.updated_by = changed_by
            db.add(existing)
        else:
            existing = PatentViewFieldValue(
                patent_id=patent_id,
                view_id=view.id,
                field_key=field_key,
                value=_stringify(value),
                updated_by=changed_by,
            )
            db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    @staticmethod
    def get_local_field_values(
        db: Session, view: PatentView, patent_id: int
    ) -> dict[str, Any]:
        """读取某专利在某视图中的所有本地字段值。"""
        rows = db.query(PatentViewFieldValue).filter(
            PatentViewFieldValue.patent_id == patent_id,
            PatentViewFieldValue.view_id == view.id,
        ).all()
        return {r.field_key: r.value for r in rows}

    # ========== 共享字段编辑（写入大表 + 记录来源视图） ==========

    @staticmethod
    def update_shared_field_in_view(
        db: Session,
        view: PatentView,
        patent_id: int,
        field_key: str,
        value: Any,
        changed_by: Optional[str] = None,
    ) -> Patent:
        """在视图中编辑共享字段——写入大表，并在 PatentHistory 中记录 source_view_id。

        - 系统字段：直接 setattr
        - custom_fields.{key}：更新 Patent.custom_fields
        - 历史记录 source_view_id / source_view_name 自动填充
        """
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        if not patent:
            raise ValueError(f"专利 {patent_id} 不存在")

        # 构造 update_data
        if field_key.startswith("custom_fields."):
            cf_key = field_key[len("custom_fields."):]
            update_data = {"custom_fields": {cf_key: value}}
        else:
            update_data = {field_key: value}

        # 通过 PatentService.update_patent 写入（自动产生历史并注入来源视图信息）
        updated_patent = PatentService.update_patent(
            db, patent, update_data,
            source="manual",
            changed_by=changed_by,
            source_view_id=view.id,
            source_view_name=view.name,
        )
        return updated_patent

    # ========== 字段提升（Promote） ==========

    @staticmethod
    def promote_local_field(
        db: Session,
        view: PatentView,
        field: ViewLocalField,
        global_name: Optional[str] = None,
        global_group: str = "从小表提升",
    ) -> CustomField:
        """将视图本地字段提升为全局 CustomField。

        - 创建 CustomField（key 用 cf_ 前缀，确保唯一）
        - 把该视图所有专利的本地字段值迁移到 Patent.custom_fields
        - 在 PatentHistory 中记录每个值的迁移（source='promote', source_view_id=视图）
        - 标记 ViewLocalField.is_promoted=True, promoted_field_key=新 key
        """
        from app.models.enums import CustomFieldType

        # 1. 生成全局唯一 key
        base = field.key.replace("vlf_", "cf_")
        # 去重
        suffix_hash = hashlib.md5(f"{view.id}_{field.key}".encode()).hexdigest()[:6]
        global_key = f"{base}_{suffix_hash}"
        # 极小概率冲突时再加后缀
        idx = 1
        while db.query(CustomField).filter(CustomField.key == global_key).first():
            global_key = f"{base}_{suffix_hash}_{idx}"
            idx += 1

        # 2. 字段类型映射（vlf 类型 → CustomFieldType 枚举）
        type_str = field.field_type
        try:
            field_type_enum = CustomFieldType(type_str)
        except ValueError:
            field_type_enum = CustomFieldType.TEXT

        # 3. 创建 CustomField
        cf = CustomField(
            key=global_key,
            name=global_name or field.name,
            field_type=field_type_enum,
            group_name=global_group,
            description=f"从视图「{view.name}」提升。{field.description or ''}".strip(),
            options=field.options,
            default_value=field.default_value,
            is_required=field.is_required,
            sort_order=999,  # 提升的字段排在末尾
        )
        db.add(cf)
        db.flush()  # 拿到 cf.id

        # 4. 迁移值：把每个 patent 的 view_local_field_value 复制到 Patent.custom_fields
        # 同时写入 PatentHistory（source='promote', source_view_id=view.id）
        field_display_map = {fm["key"]: fm.get("name") for fm in get_all_fields_meta(db)}
        field_display_map[global_key] = cf.name

        all_values = db.query(PatentViewFieldValue).filter(
            PatentViewFieldValue.view_id == view.id,
            PatentViewFieldValue.field_key == field.key,
        ).all()

        for vfv in all_values:
            patent = db.query(Patent).filter(Patent.id == vfv.patent_id).first()
            if not patent:
                continue
            old_custom = dict(patent.custom_fields or {})
            old_value = old_custom.get(global_key)
            if old_value == vfv.value:
                continue  # 值相同，跳过
            old_custom[global_key] = vfv.value
            patent.custom_fields = old_custom
            db.add(patent)

            history = PatentHistory(
                patent_id=patent.id,
                field_key=f"custom_fields.{global_key}",
                field_display_name=cf.name,
                old_value=old_value,
                new_value=vfv.value,
                source="promote",
                changed_by=vfv.updated_by,
                source_view_id=view.id,
                source_view_name=view.name,
            )
            db.add(history)

        # 5. 标记 ViewLocalField 为已提升
        field.is_promoted = True
        field.promoted_field_key = global_key
        db.add(field)

        db.commit()
        db.refresh(cf)
        return cf

    # ========== 字段来源追溯 ==========

    @staticmethod
    def get_field_sources(db: Session, patent_id: Patent) -> list[dict]:
        """返回某专利每个字段的来源信息（最后一次修改来自哪里）。"""
        # 取每条字段最新的一条历史
        # SQLite 不支持 DISTINCT ON，用 group by + max(id) 模拟
        latest_ids = (
            db.query(
                PatentHistory.field_key,
                func.max(PatentHistory.id).label("max_id"),
            )
            .filter(PatentHistory.patent_id == patent_id)
            .group_by(PatentHistory.field_key)
            .all()
        )
        if not latest_ids:
            return []

        ids = [r.max_id for r in latest_ids]
        latest_histories = (
            db.query(PatentHistory)
            .filter(PatentHistory.id.in_(ids))
            .all()
        )

        # 字段显示名
        field_display_map = {fm["key"]: fm.get("name") for fm in get_all_fields_meta(db)}

        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        result = []
        for h in latest_histories:
            # 当前值
            fk = h.field_key
            if fk.startswith("custom_fields."):
                ck = fk[len("custom_fields."):]
                cur_val = (patent.custom_fields or {}).get(ck) if patent else None
                display = field_display_map.get(ck, ck)
            else:
                cur_val = getattr(patent, fk, None) if patent else None
                display = field_display_map.get(fk, fk)

            result.append({
                "field_key": h.field_key,
                "field_display_name": h.field_display_name or display,
                "current_value": _stringify(cur_val),
                "last_source": h.source,
                "last_changed_by": h.changed_by,
                "last_changed_at": h.created_at.isoformat() if h.created_at else None,
                "last_source_view_id": h.source_view_id,
                "last_source_view_name": h.source_view_name,
            })
        return result


# ========== 内部工具 ==========

def _stringify(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        import json
        try:
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return str(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _patent_to_dict(patent: Patent) -> dict:
    """轻量级 Patent → dict，包含主要字段。"""
    return {
        "id": patent.id,
        "application_number": patent.application_number,
        "publication_number": patent.publication_number,
        "grant_number": patent.grant_number,
        "title": patent.title,
        "abstract": patent.abstract,
        "applicant": patent.applicant,
        "inventor": patent.inventor,
        "country": patent.country,
        "patent_type": patent.patent_type.value if patent.patent_type else None,
        "filing_date": patent.filing_date.isoformat() if patent.filing_date else None,
        "publication_date": patent.publication_date.isoformat() if patent.publication_date else None,
        "grant_date": patent.grant_date.isoformat() if patent.grant_date else None,
        "legal_status": patent.legal_status.value if patent.legal_status else None,
        "category": patent.category,
        "subcategory": patent.subcategory,
        "module": patent.module,
        "has_risk": patent.has_risk,
        "risk_level": patent.risk_level.value if patent.risk_level else None,
        "notes": patent.notes,
        "custom_fields": dict(patent.custom_fields or {}),
        "database_id": patent.database_id,
    }
