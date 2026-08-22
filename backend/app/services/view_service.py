"""视图（小表）服务——P0-13 新增。

核心架构：单源大表 + 视图小表（Master + View）
- 视图是 PatentDatabase（大表）上的"保存的查询"：filter + column_config + sort
- 共享字段编辑实时写入大表，并在 PatentHistory 中记录来源视图
- 视图本地字段独立存储，不污染大表
- 视图本地字段可一键 promote 为全局 CustomField（同时在历史中注明来源视图）
"""
import hashlib
import json
from typing import Optional, Any
from datetime import datetime, date, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models import (
    PatentView, ViewLocalField, PatentViewFieldValue,
    Patent, CustomField, PatentHistory, PatentDatabase,
    DatabaseMembership,
)
from app.services.patent_service import PatentService, SYSTEM_FIELDS
from app.services.field_registry import get_all_fields_meta


class ViewService:
    SUPPORTED_LAYOUT_TYPES = {"table", "kanban", "form", "gantt", "calendar"}
    CONDITION_OPERATORS = {
        "==", "!=", ">", "<", ">=", "<=", "contains", "starts_with",
        "ends_with", "is_empty", "is_not_empty", "date_within",
        "date_before", "date_after",
    }
    CONDITION_STYLE_KEYS = {
        "bgColor", "color", "fontWeight", "fontStyle", "textDecoration",
        "opacity",
    }
    DEFAULT_KANBAN_CONFIG = {
        "group_by_field": "legal_status",
        "group_values": [],
        "card_fields": ["application_number", "title", "legal_status"],
        "card_title_field": "title",
    }
    DEFAULT_FORM_CONFIG = {
        "layout": "two_column",
        "submit_label": "提交专利",
        "sections": [],
    }
    DEFAULT_GANTT_CONFIG = {
        "start_field": "filing_date",
        "end_field": "grant_date",
        "title_field": "title",
        "group_by_field": "applicant",
        "time_scale": "month",
        "bar_color_field": "risk_level",
        "bar_color_map": {},
    }

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
        layout_type: str = "table",
        group_by_config: Optional[dict] = None,
        conditional_formatting: Optional[list] = None,
        kanban_config: Optional[dict] = None,
        form_config: Optional[dict] = None,
        gantt_config: Optional[dict] = None,
        is_department_master: bool = False,
        membership_based: bool = False,
        template_key: Optional[str] = None,
    ) -> PatentView:
        if layout_type not in ViewService.SUPPORTED_LAYOUT_TYPES:
            raise ValueError(f"不支持的视图展示类型：{layout_type}")

        column_config = ViewService.validate_column_config(column_config or [])

        # 部门总表视图每库唯一
        group_by_config = ViewService.validate_group_by_config(group_by_config or {})
        conditional_formatting = ViewService.validate_conditional_formatting(
            conditional_formatting or []
        )
        kanban_config = ViewService.validate_kanban_config(kanban_config or {})
        form_config = ViewService.validate_form_config(form_config or {})
        gantt_config = ViewService.validate_gantt_config(gantt_config or {})

        if is_department_master:
            existing = ViewService.get_department_master_view(db, database_id)
            if existing:
                raise ValueError(f"库 {database_id} 已存在部门总表视图（id={existing.id}）")
            view_type = "department_master"

        view = PatentView(
            name=name,
            description=description,
            template_key=template_key,
            database_id=database_id,
            owner_id=owner_id,
            view_type=view_type,
            layout_type=layout_type,
            is_department_master=is_department_master,
            filter_config=filter_config or {},
            column_config=column_config,
            sort_config=sort_config or {},
            group_by_config=group_by_config or {},
            conditional_formatting=conditional_formatting or [],
            kanban_config=kanban_config or {},
            form_config=form_config or {},
            gantt_config=gantt_config or {},
        )
        db.add(view)
        db.commit()
        db.refresh(view)

        # P0-14：成员型视图——自动在 filter_config 中注入 view_id 过滤
        if membership_based and not is_department_master:
            merged_filter = dict(view.filter_config or {})
            merged_filter["view_id"] = view.id
            view.filter_config = merged_filter
            db.add(view)
            db.commit()
            db.refresh(view)
        return view

    @staticmethod
    def update_view(db: Session, view: PatentView, updates: dict) -> PatentView:
        layout_type = updates.get("layout_type")
        if layout_type is not None and layout_type not in ViewService.SUPPORTED_LAYOUT_TYPES:
            raise ValueError(f"不支持的视图展示类型：{layout_type}")
        if "column_config" in updates:
            updates["column_config"] = ViewService.validate_column_config(
                updates["column_config"] or []
            )
        if "group_by_config" in updates:
            updates["group_by_config"] = ViewService.validate_group_by_config(
                updates["group_by_config"]
            )
        if "conditional_formatting" in updates:
            updates["conditional_formatting"] = ViewService.validate_conditional_formatting(
                updates["conditional_formatting"]
            )
        if "kanban_config" in updates:
            updates["kanban_config"] = ViewService.validate_kanban_config(
                updates["kanban_config"]
            )
        if "form_config" in updates:
            updates["form_config"] = ViewService.validate_form_config(updates["form_config"])
        if "gantt_config" in updates:
            updates["gantt_config"] = ViewService.validate_gantt_config(updates["gantt_config"])
        for k, v in updates.items():
            if v is not None and hasattr(view, k):
                setattr(view, k, v)
        db.add(view)
        db.commit()
        db.refresh(view)
        return view

    @staticmethod
    def validate_column_config(config: list[dict]) -> list[dict]:
        """校验视图列投影，但不限制字段 key 必须已经注册。

        未注册 key 需要保留，便于字段注册表演进和旧视图兼容；真正的字段
        是否可展示由前端字段元数据和视图配置共同决定。
        """
        if not isinstance(config, list):
            raise ValueError("column_config 必须是数组")
        normalized = []
        seen = set()
        for item in config:
            if not isinstance(item, dict) or not isinstance(item.get("key"), str) or not item["key"].strip():
                raise ValueError("column_config 中每项必须包含非空 key")
            key = item["key"].strip()
            if key in seen:
                raise ValueError(f"column_config 存在重复字段：{key}")
            seen.add(key)
            visible = item.get("visible", True)
            if not isinstance(visible, bool):
                raise ValueError(f"字段 {key} 的 visible 必须是布尔值")
            width = item.get("width")
            if width is not None and (not isinstance(width, int) or isinstance(width, bool) or width < 40 or width > 1200):
                raise ValueError(f"字段 {key} 的 width 必须在 40-1200 之间")
            order = item.get("order", 0)
            if not isinstance(order, int) or isinstance(order, bool) or order < 0:
                raise ValueError(f"字段 {key} 的 order 必须是非负整数")
            normalized.append({"key": key, "visible": visible, "width": width, "order": order})
        return normalized

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
            "template_key": view.template_key,
            "database_id": view.database_id,
            "owner_id": view.owner_id,
            "view_type": view.view_type,
            "layout_type": view.layout_type or "table",
            "is_department_master": view.is_department_master,
            "is_archived": view.is_archived,
            "filter_config": view.filter_config or {},
            "column_config": view.column_config or [],
            "sort_config": view.sort_config or {},
            "group_by_config": view.group_by_config or {},
            "conditional_formatting": view.conditional_formatting or [],
            "kanban_config": view.kanban_config or {},
            "form_config": view.form_config or {},
            "gantt_config": view.gantt_config or {},
            "created_at": view.created_at.isoformat() if view.created_at else None,
            "updated_at": view.updated_at.isoformat() if view.updated_at else None,
        }
        if include_fields:
            result["local_fields"] = [
                ViewService.local_field_to_dict(f) for f in view.local_fields
            ]
        return result

    @staticmethod
    def ensure_default_business_views(db: Session, database_id: int) -> list[PatentView]:
        """为每个专利库建立六个可直接使用、可继续修改的高频业务视图。

        视图只保存筛选/列/排序配置，不复制 Patent 数据；用户可以在前端
        继续调整列和筛选，导出时仍从同一专利主表取数。
        """
        common = [
            ("application_number", 150), ("publication_number", 140),
            ("title", 300), ("country", 70),
        ]
        definitions = [
            {
                "key": "risk_meeting_statistics",
                "name": "风险会风险统计表",
                "description": "风险会议统计底表；以风险等级分组，可继续叠加项目/国家筛选。",
                "columns": common + [("risk_level", 100), ("risk_description", 260), ("legal_status", 100)],
                "filter": {"has_risk": {"eq": True}},
                "group": {"fields": [{"field": "risk_level", "direction": "asc"}]},
            },
            {
                "key": "company_filing_category",
                "name": "品类我司专利申请类",
                "description": "按品类整理我司申请/布局专利的工作底表；不预设公司名称，避免把业务判断硬编码。",
                "columns": common + [("category", 130), ("subcategory", 130), ("applicant", 180), ("filing_date", 110), ("legal_status", 100)],
                "filter": {},
                "group": {"fields": [{"field": "category", "direction": "asc"}]},
            },
            {
                "key": "ip_risk_control",
                "name": "IP事务管控表之风险管控表",
                "description": "风险管控工作底表；显示产品、关联项目、风险描述和法律状态，关系实体仍由详情页维护。",
                "columns": common + [("product_id", 150), ("projects", 220), ("category", 130), ("risk_level", 100), ("risk_description", 300), ("has_risk", 80), ("application_status", 120)],
                "filter": {"has_risk": {"eq": True}},
                "group": {"fields": [{"field": "risk_level", "direction": "desc"}, {"field": "category", "direction": "asc"}]},
            },
            {
                "key": "ip_application_control",
                "name": "IP事务管控表之申请管控表",
                "description": "申请管控工作底表；申请号、公开号、日期、代理和状态来自同一专利记录。",
                "columns": common + [("applicant", 180), ("inventor", 160), ("agent", 160), ("filing_date", 110), ("publication_date", 110), ("grant_date", 110), ("application_status", 120)],
                "filter": {},
                "group": {"fields": [{"field": "application_status", "direction": "asc"}]},
            },
            {
                "key": "product_category_master",
                "name": "产品品类数据总库",
                "description": "产品/品类维度专利总库；视图是查询投影，不另建一份数据。",
                "columns": common + [("category", 130), ("subcategory", 130), ("module", 160), ("ipc_main", 120), ("applicant", 180), ("legal_status", 100)],
                "filter": {},
                "group": {"fields": [{"field": "category", "direction": "asc"}, {"field": "subcategory", "direction": "asc"}]},
            },
            {
                "key": "daily_patent_accumulation",
                "name": "日常相关专利积累",
                "description": "日常检索、分析和撰写调用的宽口径专利积累视图；允许逐步补充人工字段。",
                "columns": common + [("abstract", 260), ("applicant", 180), ("inventor", 160), ("ipc_main", 120), ("priority_date", 110), ("legal_status", 100), ("notes", 220)],
                "filter": {},
                "group": {"fields": [{"field": "country", "direction": "asc"}]},
            },
        ]
        created: list[PatentView] = []
        for definition in definitions:
            existing = db.query(PatentView).filter(
                PatentView.database_id == database_id,
                PatentView.template_key == definition["key"],
            ).first()
            if existing:
                # Default templates are additive: introduce newly required
                # business projections without overwriting user column choices.
                if definition["key"] == "ip_risk_control":
                    configured = list(existing.column_config or [])
                    configured_keys = {item.get("key") for item in configured if isinstance(item, dict)}
                    next_order = max((item.get("order", 0) for item in configured if isinstance(item, dict)), default=-1) + 1
                    for key, width in (("product_id", 150), ("projects", 220)):
                        if key not in configured_keys:
                            configured.append({"key": key, "visible": True, "width": width, "order": next_order})
                            next_order += 1
                    if configured != (existing.column_config or []):
                        existing.column_config = configured
                        db.add(existing)
                        db.commit()
                created.append(existing)
                continue
            column_config = [
                {"key": key, "visible": True, "width": width, "order": index}
                for index, (key, width) in enumerate(definition["columns"])
            ]
            created.append(ViewService.create_view(
                db,
                name=definition["name"],
                description=definition["description"],
                database_id=database_id,
                view_type="shared",
                layout_type="table",
                filter_config=definition["filter"],
                column_config=column_config,
                sort_config={"sort_by": "filing_date", "sort_order": "desc"},
                group_by_config=definition["group"],
                template_key=definition["key"],
            ))
        return created

    # ========== 视图数据查询 ==========

    @staticmethod
    def list_view_patents(
        db: Session,
        view: PatentView,
        page: int = 1,
        page_size: int = 50,
        extra_filters: Optional[dict] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        group_by_family: bool = False,
    ) -> tuple[list[Patent], int]:
        """获取视图中的专利列表。

        - 应用视图自身的 filter_config
        - 合并 extra_filters（前端临时筛选）
        - 应用视图的 sort_config 作为默认排序
        """
        merged_filters = dict(view.filter_config or {})
        if extra_filters:
            merged_filters.update(extra_filters)

        sort_by = sort_by or (view.sort_config or {}).get("sort_by")
        sort_order = sort_order or (view.sort_config or {}).get("sort_order", "asc")

        patents, total = PatentService.list_patents(
            db,
            page=page,
            page_size=page_size,
            database_id=view.database_id,
            search=search,
            filters=merged_filters if merged_filters else None,
            sort_by=sort_by,
            sort_order=sort_order,
            group_by_family=group_by_family,
        )
        return patents, total

    @staticmethod
    def validate_kanban_config(config: Any) -> dict:
        """Normalize the persisted configuration for a kanban view."""
        if config in (None, {}):
            return dict(ViewService.DEFAULT_KANBAN_CONFIG)
        if not isinstance(config, dict):
            raise ValueError("kanban_config must be an object")

        group_by_field = str(config.get("group_by_field", "legal_status")).strip()
        if not group_by_field:
            raise ValueError("kanban_config.group_by_field is required")
        if group_by_field.startswith("view_local."):
            raise ValueError("看板分组字段暂不支持视图本地字段")

        group_values = config.get("group_values") or []
        if not isinstance(group_values, list) or len(group_values) > 100:
            raise ValueError("kanban_config.group_values must be an array with at most 100 values")
        if any(isinstance(value, (dict, list)) for value in group_values):
            raise ValueError("kanban group values must be scalar values")

        card_fields = config.get("card_fields") or [group_by_field]
        if not isinstance(card_fields, list) or not card_fields or len(card_fields) > 12:
            raise ValueError("kanban_config.card_fields must contain 1 to 12 fields")
        normalized_card_fields = []
        for field in card_fields:
            key = str(field).strip()
            if key and key not in normalized_card_fields:
                normalized_card_fields.append(key)
        if not normalized_card_fields:
            raise ValueError("kanban_config.card_fields must contain field keys")

        card_title_field = str(
            config.get("card_title_field") or normalized_card_fields[0]
        ).strip()
        if card_title_field not in normalized_card_fields:
            normalized_card_fields.insert(0, card_title_field)

        return {
            "group_by_field": group_by_field,
            "group_values": group_values,
            "card_fields": normalized_card_fields[:12],
            "card_title_field": card_title_field,
        }

    @staticmethod
    def validate_form_config(config: Any) -> dict:
        """Normalize the persisted form layout without coupling to field metadata."""
        if config in (None, {}):
            return dict(ViewService.DEFAULT_FORM_CONFIG)
        if not isinstance(config, dict):
            raise ValueError("form_config must be an object")
        layout = str(config.get("layout", "two_column"))
        if layout not in {"single_column", "two_column"}:
            raise ValueError("form_config.layout must be single_column or two_column")
        raw_sections = config.get("sections") or []
        if not isinstance(raw_sections, list) or len(raw_sections) > 50:
            raise ValueError("form_config.sections must contain at most 50 sections")
        sections = []
        for raw_section in raw_sections:
            if not isinstance(raw_section, dict):
                raise ValueError("form sections must be objects")
            raw_fields = raw_section.get("fields") or []
            if not isinstance(raw_fields, list) or len(raw_fields) > 100:
                raise ValueError("form section fields must be an array with at most 100 fields")
            fields = []
            for raw_field in raw_fields:
                if isinstance(raw_field, str):
                    raw_field = {"key": raw_field}
                if not isinstance(raw_field, dict) or not str(raw_field.get("key", "")).strip():
                    raise ValueError("form field configuration requires a key")
                field = {
                    "key": str(raw_field["key"]).strip(),
                    "required": bool(raw_field.get("required", False)),
                    "col_span": 2 if int(raw_field.get("col_span", 1) or 1) == 2 else 1,
                }
                if isinstance(raw_field.get("default"), (str, int, float, bool, type(None), list)):
                    field["default"] = raw_field.get("default")
                if raw_field.get("visible_when") is not None:
                    if not isinstance(raw_field["visible_when"], dict):
                        raise ValueError("form field visible_when must be an object")
                    field["visible_when"] = raw_field["visible_when"]
                fields.append(field)
            section = {
                "title": str(raw_section.get("title") or "未命名分区").strip(),
                "fields": fields,
            }
            if raw_section.get("visible_when") is not None:
                if not isinstance(raw_section["visible_when"], dict):
                    raise ValueError("form section visible_when must be an object")
                section["visible_when"] = raw_section["visible_when"]
            sections.append(section)
        return {
            "layout": layout,
            "submit_label": str(config.get("submit_label") or "提交专利").strip(),
            "sections": sections,
        }

    @staticmethod
    def validate_gantt_config(config: Any) -> dict:
        """Normalize date fields and visual options for a gantt view."""
        if config in (None, {}):
            return dict(ViewService.DEFAULT_GANTT_CONFIG)
        if not isinstance(config, dict):
            raise ValueError("gantt_config must be an object")
        time_scale = str(config.get("time_scale", "month"))
        if time_scale not in {"day", "week", "month", "quarter", "year"}:
            raise ValueError("gantt_config.time_scale is invalid")
        start_field = str(config.get("start_field", "filing_date")).strip()
        end_field = str(config.get("end_field", "grant_date")).strip()
        if not start_field or not end_field or start_field == end_field:
            raise ValueError("甘特视图需要不同的开始和结束日期字段")
        group_by_field = str(config.get("group_by_field", "")).strip()
        color_map = config.get("bar_color_map") or {}
        if not isinstance(color_map, dict):
            raise ValueError("gantt_config.bar_color_map must be an object")
        return {
            "start_field": start_field,
            "end_field": end_field,
            "title_field": str(config.get("title_field", "title")).strip() or "title",
            "group_by_field": group_by_field,
            "time_scale": time_scale,
            "bar_color_field": str(config.get("bar_color_field", "")).strip(),
            "bar_color_map": {str(key): str(value) for key, value in color_map.items()},
        }

    @staticmethod
    def get_kanban_data(
        db: Session,
        view: PatentView,
        page_size: int = 200,
        extra_filters: Optional[dict] = None,
        search: Optional[str] = None,
    ) -> dict:
        """Return configured kanban groups with projected patent cards."""
        config = ViewService.validate_kanban_config(view.kanban_config)
        patents, total = ViewService.list_view_patents(
            db, view, page=1, page_size=min(max(page_size, 1), 1000),
            extra_filters=extra_filters, search=search,
        )
        group_field = config["group_by_field"]
        card_fields = config["card_fields"]
        # 批量预加载本地字段值，避免 N+1
        items = ViewService.get_view_patents_with_local_fields_batch(db, view, patents)
        cards = []
        for patent, item in zip(patents, items):
            group_value = _get_item_field_value(item, group_field)
            card_values = {
                field: _get_item_field_value(item, field) for field in card_fields
            }
            title_value = card_values.get(config["card_title_field"])
            cards.append({
                "id": patent.id,
                "title": str(title_value or patent.title or "未命名专利"),
                "group_value": group_value,
                "fields": card_values,
            })

        groups_by_key: dict[str, dict] = {}
        ordered_keys: list[str] = []

        def add_group(value: Any) -> None:
            key = _group_key(value)
            if key in groups_by_key:
                return
            groups_by_key[key] = {
                "key": None if value in (None, "") else value,
                "label": "未设置" if value in (None, "") else str(value),
                "count": 0,
                "cards": [],
            }
            ordered_keys.append(key)

        for value in config["group_values"]:
            add_group(value)
        for card in cards:
            add_group(card["group_value"])
        add_group(None)

        for card in cards:
            group = groups_by_key[_group_key(card["group_value"])]
            group["cards"].append(card)
            group["count"] += 1

        return {
            "view_id": view.id,
            "total": total,
            "returned": len(cards),
            "truncated": total > len(cards),
            "group_by_field": group_field,
            "config": config,
            "groups": [groups_by_key[key] for key in ordered_keys],
        }

    @staticmethod
    def move_kanban_card(
        db: Session,
        view: PatentView,
        patent_id: int,
        to_value: Any,
        changed_by: Optional[str] = None,
    ) -> Patent:
        """Move a card by updating its configured shared/custom field."""
        config = ViewService.validate_kanban_config(view.kanban_config)
        if config["group_values"] and to_value is not None:
            allowed = {_group_key(value) for value in config["group_values"]}
            if _group_key(to_value) not in allowed:
                raise ValueError("目标看板列不在当前视图配置中")
        patent = db.query(Patent).filter(
            Patent.id == patent_id,
            Patent.database_id == view.database_id,
        ).first()
        if not patent:
            raise ValueError(f"专利 {patent_id} 不属于当前视图所在的库")

        field_key = config["group_by_field"]
        if field_key.startswith("custom_fields."):
            update_key = field_key
        elif field_key in SYSTEM_FIELDS:
            update_key = field_key
        else:
            update_key = f"custom_fields.{field_key}"
        return ViewService.update_shared_field_in_view(
            db, view, patent_id, update_key, to_value, changed_by=changed_by,
        )

    @staticmethod
    def get_gantt_data(
        db: Session,
        view: PatentView,
        page_size: int = 200,
        extra_filters: Optional[dict] = None,
        search: Optional[str] = None,
    ) -> dict:
        """Return date-bounded patents grouped for a gantt timeline."""
        config = ViewService.validate_gantt_config(view.gantt_config)
        patents, total = ViewService.list_view_patents(
            db, view, page=1, page_size=min(max(page_size, 1), 1000),
            extra_filters=extra_filters, search=search,
        )
        groups_by_key: dict[str, dict] = {}
        ordered_keys: list[str] = []
        time_start: Optional[date] = None
        time_end: Optional[date] = None

        def add_group(value: Any) -> dict:
            key = _group_key(value)
            if key not in groups_by_key:
                groups_by_key[key] = {
                    "key": None if value in (None, "") else value,
                    "label": "未设置" if value in (None, "") else str(value),
                    "items": [],
                }
                ordered_keys.append(key)
            return groups_by_key[key]

        # 批量预加载本地字段值，避免 N+1
        items = ViewService.get_view_patents_with_local_fields_batch(db, view, patents)
        for patent, item in zip(patents, items):
            start = _parse_date(_get_item_field_value(item, config["start_field"]))
            end = _parse_date(_get_item_field_value(item, config["end_field"]))
            if not start or not end:
                continue
            if end < start:
                start, end = end, start
            title = _get_item_field_value(item, config["title_field"])
            group_value = _get_item_field_value(item, config["group_by_field"]) if config["group_by_field"] else None
            color_value = _get_item_field_value(item, config["bar_color_field"]) if config["bar_color_field"] else None
            color = config["bar_color_map"].get(str(color_value), "#2563eb")
            group = add_group(group_value)
            group["items"].append({
                "id": patent.id,
                "title": str(title or patent.title or "未命名专利"),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "color": color,
            })
            time_start = start if time_start is None or start < time_start else time_start
            time_end = end if time_end is None or end > time_end else time_end

        return {
            "view_id": view.id,
            "total": total,
            "returned": sum(len(group["items"]) for group in groups_by_key.values()),
            "truncated": total > len(patents),
            "config": config,
            "groups": [groups_by_key[key] for key in ordered_keys],
            "time_range": {
                "start": time_start.isoformat() if time_start else None,
                "end": time_end.isoformat() if time_end else None,
            },
        }

    @staticmethod
    def update_gantt_dates(
        db: Session,
        view: PatentView,
        patent_id: int,
        new_start: date,
        new_end: date,
        changed_by: Optional[str] = None,
    ) -> Patent:
        config = ViewService.validate_gantt_config(view.gantt_config)
        if new_end < new_start:
            raise ValueError("甘特任务结束日期不能早于开始日期")
        patent = db.query(Patent).filter(
            Patent.id == patent_id,
            Patent.database_id == view.database_id,
        ).first()
        if not patent:
            raise ValueError(f"专利 {patent_id} 不属于当前视图所在的库")

        def update_field(field_key: str, value: Any) -> None:
            update_key = field_key
            if not field_key.startswith("custom_fields.") and field_key not in SYSTEM_FIELDS:
                update_key = f"custom_fields.{field_key}"
            if update_key.startswith("custom_fields."):
                value = value.isoformat() if isinstance(value, (date, datetime)) else value
            ViewService.update_shared_field_in_view(
                db, view, patent_id, update_key, value, changed_by=changed_by,
            )

        update_field(config["start_field"], new_start)
        update_field(config["end_field"], new_end)
        db.refresh(patent)
        return patent

    # ========== Grouping and conditional formatting ==========

    @staticmethod
    def validate_group_by_config(config: Any) -> dict:
        """Normalize and validate the persisted grouping configuration."""
        if config in (None, {}, []):
            return {"fields": []}
        if isinstance(config, dict):
            raw_fields = config.get("fields", [])
            if not raw_fields and config.get("field"):
                raw_fields = [config]
        elif isinstance(config, list):
            raw_fields = config
        else:
            raise ValueError("group_by_config must be an object or array")

        if not isinstance(raw_fields, list) or len(raw_fields) > 3:
            raise ValueError("group_by_config supports at most 3 fields")

        normalized = []
        seen = set()
        for item in raw_fields:
            if not isinstance(item, dict) or not str(item.get("field", "")).strip():
                raise ValueError("Every group field must include a field key")
            field = str(item["field"]).strip()
            if field in seen:
                raise ValueError(f"Duplicate group field: {field}")
            direction = item.get("direction", "asc")
            if direction not in {"asc", "desc"}:
                raise ValueError("Group direction must be asc or desc")
            seen.add(field)
            normalized.append({
                "field": field,
                "direction": direction,
                "collapsed": bool(item.get("collapsed", False)),
            })
        return {"fields": normalized}

    @staticmethod
    def validate_conditional_formatting(config: Any) -> list[dict]:
        """Validate conditional formatting without executing arbitrary expressions."""
        if config in (None, []):
            return []
        if not isinstance(config, list):
            raise ValueError("conditional_formatting must be an array")

        normalized = []
        for index, rule in enumerate(config):
            if not isinstance(rule, dict) or not str(rule.get("field", "")).strip():
                raise ValueError("Every conditional format rule must include a field key")
            conditions = rule.get("conditions", [])
            if not isinstance(conditions, list) or not conditions:
                raise ValueError("Every conditional format rule needs at least one condition")
            normalized_conditions = []
            for condition in conditions:
                if not isinstance(condition, dict):
                    raise ValueError("Conditional format conditions must be objects")
                operator = condition.get("op")
                if operator not in ViewService.CONDITION_OPERATORS:
                    raise ValueError(f"Unsupported conditional format operator: {operator}")
                style = condition.get("style") or {}
                if not isinstance(style, dict):
                    raise ValueError("Conditional format style must be an object")
                normalized_conditions.append({
                    "op": operator,
                    "value": condition.get("value"),
                    **({"unit": condition.get("unit")} if condition.get("unit") else {}),
                    "style": {
                        key: value
                        for key, value in style.items()
                        if key in ViewService.CONDITION_STYLE_KEYS and value is not None
                    },
                })
            normalized.append({
                "id": str(rule.get("id") or f"cf_{index + 1}"),
                "field": str(rule["field"]).strip(),
                "conditions": normalized_conditions,
            })
        return normalized

    @staticmethod
    def get_grouped_data(
        db: Session,
        view: PatentView,
        page: int = 1,
        page_size: int = 500,
        extra_filters: Optional[dict] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        group_by_family: bool = False,
    ) -> dict:
        """Return the current view page as nested groups."""
        group_fields = ViewService.validate_group_by_config(view.group_by_config).get("fields", [])
        normalized_page_size = min(max(page_size, 1), 500)
        patents, total = ViewService.list_view_patents(
            db, view, page=page, page_size=normalized_page_size,
            extra_filters=extra_filters, search=search,
            sort_by=sort_by, sort_order=sort_order,
            group_by_family=group_by_family,
        )
        local_values = {}
        if patents:
            rows = db.query(PatentViewFieldValue).filter(
                PatentViewFieldValue.view_id == view.id,
                PatentViewFieldValue.patent_id.in_([patent.id for patent in patents]),
            ).all()
            for row in rows:
                local_values.setdefault(row.patent_id, {})[row.field_key] = row.value

        items = []
        for patent in patents:
            item = _patent_to_dict(patent)
            item["view_local_fields"] = {
                field.key: local_values.get(patent.id, {}).get(field.key)
                for field in view.local_fields
            }
            items.append(item)

        def build_groups(current_items: list[dict], depth: int) -> list[dict]:
            config = group_fields[depth]
            buckets: dict[str, dict] = {}
            for item in current_items:
                value = _get_item_field_value(item, config["field"])
                bucket_key = _group_key(value)
                bucket = buckets.setdefault(bucket_key, {
                    "key": None if value in (None, "") else value,
                    "label": "未设置" if value in (None, "") else str(value),
                    "items": [],
                })
                bucket["items"].append(item)

            groups = list(buckets.values())
            groups.sort(
                key=lambda group: (group["key"] is None, str(group["key"]).casefold()),
                reverse=config["direction"] == "desc",
            )
            result = []
            for group in groups:
                children = group.pop("items")
                entry = {
                    "key": group["key"],
                    "label": group["label"],
                    "field": config["field"],
                    "count": len(children),
                    "collapsed": config["collapsed"],
                }
                if depth + 1 < len(group_fields):
                    entry["subgroups"] = build_groups(children, depth + 1)
                else:
                    entry["patents"] = children
                result.append(entry)
            return result

        return {
            "view_id": view.id,
            "total": total,
            "page": page,
            "page_size": normalized_page_size,
            "groups": build_groups(items, 0) if group_fields else [],
            "group_by_config": {"fields": group_fields},
            "conditional_formatting": view.conditional_formatting or [],
        }

    @staticmethod
    def get_conditional_styles(view: PatentView, field_key: str, value: Any) -> dict:
        """Return the first matching style for one cell."""
        for rule in view.conditional_formatting or []:
            if rule.get("field") != field_key:
                continue
            for condition in rule.get("conditions", []):
                if _matches_condition(value, condition):
                    return condition.get("style") or {}
        return {}

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

    @staticmethod
    def get_view_patents_with_local_fields_batch(
        db: Session, view: PatentView, patents: list[Patent]
    ) -> list[dict]:
        """批量返回多个专利在视图中可见的所有字段值（共享字段 + 视图本地字段）。

        替代逐条调用 get_view_patent_with_local_fields 的 N+1 模式：
        一次性用 IN 子句拉回当前页所有专利的本地字段值，再在内存里按
        patent_id 分组拼装，将 N 次查询降为 1 次。
        """
        if not patents:
            return []

        # 一次查询拉回所有专利的本地字段值
        patent_ids = [p.id for p in patents]
        rows = db.query(PatentViewFieldValue).filter(
            PatentViewFieldValue.view_id == view.id,
            PatentViewFieldValue.patent_id.in_(patent_ids),
        ).all()

        # 按 patent_id 分组
        local_values_by_patent: dict[int, dict[str, Any]] = {}
        for row in rows:
            local_values_by_patent.setdefault(row.patent_id, {})[row.field_key] = row.value

        items = []
        for patent in patents:
            patent_dict = _patent_to_dict(patent)
            lv_map = local_values_by_patent.get(patent.id, {})
            patent_dict["view_local_fields"] = {
                f.key: lv_map.get(f.key) for f in view.local_fields
            }
            items.append(patent_dict)
        return items

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
                "import_batch_id": h.import_batch_id,
                "source_table_title": h.source_table_title,
                "source_row": h.source_row,
                "source_field_name": h.source_field_name,
            })
        return result


# ========== 内部工具 ==========

def _get_item_field_value(item: dict, field_key: str) -> Any:
    if field_key.startswith("custom_fields."):
        return (item.get("custom_fields") or {}).get(field_key[len("custom_fields."):])
    if field_key.startswith("ai_fields."):
        return (item.get("ai_fields") or {}).get(field_key[len("ai_fields."):])
    if field_key.startswith("view_local."):
        return (item.get("view_local_fields") or {}).get(field_key[len("view_local."):])
    if field_key in item:
        return item.get(field_key)
    return (item.get("custom_fields") or {}).get(field_key)


def _group_key(value: Any) -> str:
    if value is None or value == "":
        return "__empty__"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _parse_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _matches_condition(value: Any, condition: dict) -> bool:
    operator = condition.get("op")
    expected = condition.get("value")
    empty = value is None or value == ""
    if operator == "is_empty":
        return empty
    if operator == "is_not_empty":
        return not empty
    if empty:
        return False
    if operator == "contains":
        return str(expected).casefold() in str(value).casefold()
    if operator == "starts_with":
        return str(value).casefold().startswith(str(expected).casefold())
    if operator == "ends_with":
        return str(value).casefold().endswith(str(expected).casefold())
    if operator in {"date_within", "date_before", "date_after"}:
        actual_date = _parse_date(value)
        if not actual_date:
            return False
        if operator == "date_within":
            try:
                amount = int(expected)
            except (TypeError, ValueError):
                return False
            unit = condition.get("unit", "day")
            multiplier = {"day": 1, "week": 7, "month": 30}.get(unit, 1)
            today = date.today()
            return today <= actual_date <= today + timedelta(days=amount * multiplier)
        compare_date = _parse_date(expected)
        if not compare_date:
            return False
        return actual_date < compare_date if operator == "date_before" else actual_date > compare_date
    if operator in {">", "<", ">=", "<="}:
        try:
            left, right = float(value), float(expected)
        except (TypeError, ValueError):
            left, right = str(value), str(expected)
        return {
            ">": left > right,
            "<": left < right,
            ">=": left >= right,
            "<=": left <= right,
        }[operator]
    if operator == "==":
        return str(value).casefold() == str(expected).casefold()
    if operator == "!=":
        return str(value).casefold() != str(expected).casefold()
    return False


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
        "ai_fields": dict(patent.ai_fields or {}),
        "database_id": patent.database_id,
    }
