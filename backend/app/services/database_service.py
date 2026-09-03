"""专利库（Database）服务——P0-11 新增。

库是专利数据的顶层品类容器，导入时强制选择，去重范围限定在库内。
"""
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from app.database import Base

from app.models import PatentDatabase, Patent, User, DatabaseMembership


class DatabaseService:
    @staticmethod
    def list_databases(
        db: Session,
        include_archived: bool = False,
    ) -> list[PatentDatabase]:
        query = db.query(PatentDatabase)
        if not include_archived:
            query = query.filter(PatentDatabase.is_archived == False)
        query = query.order_by(PatentDatabase.sort_order, PatentDatabase.id)
        return query.all()

    @staticmethod
    def get_database(db: Session, database_id: int) -> Optional[PatentDatabase]:
        return db.query(PatentDatabase).filter(PatentDatabase.id == database_id).first()

    @staticmethod
    def get_default_database(db: Session) -> Optional[PatentDatabase]:
        """优先返回 is_default=True 的库，否则返回第一个库，再否则 None。"""
        default = db.query(PatentDatabase).filter(PatentDatabase.is_default == True).first()
        if default:
            return default
        return db.query(PatentDatabase).order_by(PatentDatabase.sort_order, PatentDatabase.id).first()

    @staticmethod
    def create_database(
        db: Session,
        name: str,
        code: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None,
        icon: Optional[str] = None,
        owner_id: Optional[int] = None,
    ) -> PatentDatabase:
        # 自动生成 code（如未提供）
        if not code:
            base = "".join(c for c in name if c.isalnum() or c in "_-").upper() or "DB"
            existing_count = db.query(PatentDatabase).count()
            code = f"{base}_{existing_count + 1:03d}"

        # code 唯一性：若冲突则加后缀
        if db.query(PatentDatabase).filter(PatentDatabase.code == code).first():
            suffix = 1
            while db.query(PatentDatabase).filter(PatentDatabase.code == f"{code}_{suffix}").first():
                suffix += 1
            code = f"{code}_{suffix}"

        database = PatentDatabase(
            name=name,
            code=code,
            description=description,
            color=color or "#1890ff",
            icon=icon,
            sort_order=db.query(PatentDatabase).count(),
            owner_id=owner_id,
        )
        db.add(database)
        db.commit()
        db.refresh(database)

        # 自动建立 owner 成员关系（role=owner）
        if owner_id is not None:
            existing = db.query(DatabaseMembership).filter(
                DatabaseMembership.user_id == owner_id,
                DatabaseMembership.database_id == database.id,
            ).first()
            if not existing:
                membership = DatabaseMembership(
                    user_id=owner_id,
                    database_id=database.id,
                    role="owner",
                )
                db.add(membership)
                db.commit()

        # P0-14：建库时自动创建主视图（master view），所有专利默认可见
        try:
            from app.services.view_service import ViewService
            existing_master = ViewService.get_department_master_view(db, database.id)
            if not existing_master:
                ViewService.create_view(
                    db,
                    name=f"{name} · 主表",
                    database_id=database.id,
                    view_type="department_master",
                    is_department_master=True,
                    filter_config={},
                    column_config=[],
                    sort_config={"sort_by": "filing_date", "sort_order": "desc"},
                )
            from app.services.view_service import ViewService as BusinessViewService
            BusinessViewService.ensure_default_business_views(db, database.id)
            from app.services.export_service import ExportService
            ExportService.ensure_default_templates(db, database.id)
        except Exception:
            # 主视图/业务模板创建失败不应阻断建库流程；下次启动会幂等补齐。
            pass
        return database

    @staticmethod
    def set_owner(db: Session, database: PatentDatabase, user_id: int) -> PatentDatabase:
        """设置库的所有者（同时建立 owner 成员关系）"""
        database.owner_id = user_id
        db.add(database)
        # 建立/更新成员关系
        existing = db.query(DatabaseMembership).filter(
            DatabaseMembership.user_id == user_id,
            DatabaseMembership.database_id == database.id,
        ).first()
        if existing:
            existing.role = "owner"
        else:
            db.add(DatabaseMembership(user_id=user_id, database_id=database.id, role="owner"))
        db.commit()
        db.refresh(database)
        return database

    @staticmethod
    def update_database(
        db: Session,
        database: PatentDatabase,
        name: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None,
        icon: Optional[str] = None,
        sort_order: Optional[int] = None,
    ) -> PatentDatabase:
        if name is not None:
            database.name = name
        if description is not None:
            database.description = description
        if color is not None:
            database.color = color
        if icon is not None:
            database.icon = icon
        if sort_order is not None:
            database.sort_order = sort_order
        db.add(database)
        db.commit()
        db.refresh(database)
        return database

    @staticmethod
    def archive_database(db: Session, database: PatentDatabase) -> PatentDatabase:
        database.is_archived = True
        db.add(database)
        db.commit()
        db.refresh(database)
        return database

    @staticmethod
    def delete_database(db: Session, database: PatentDatabase, force: bool = False) -> bool:
        """删除库。

        - force=False（默认）：库中有专利时拒绝删除，需先迁移或清空。
        - force=True：级联删除库内所有数据（专利/视图/仪表盘/自动化规则/附件），
          然后删库。默认库仍不可删。
        """
        # 不允许删除默认库
        if database.is_default:
            return False
        patent_count = db.query(func.count(Patent.id)).filter(Patent.database_id == database.id).scalar()
        if patent_count and patent_count > 0:
            if not force:
                return False
        if not force and patent_count:
            return False

        # SQLite enforces foreign keys for every application connection. Do
        # not rely on ORM relationship cascades here: bulk deletes are used so
        # a database can be removed even when it contains old rows created
        # before the V2 relationships were added.
        tables = Base.metadata.tables
        def delete_where(table_name: str, condition) -> None:
            table = tables.get(table_name)
            if table is not None:
                db.execute(table.delete().where(condition(table)))

        def delete_ids(table_name: str, column_name: str, ids: set[int]) -> None:
            if not ids:
                return
            table = tables.get(table_name)
            column = table.c.get(column_name) if table is not None else None
            if column is not None:
                db.execute(table.delete().where(column.in_(ids)))

        patent_ids = {
            int(row[0]) for row in db.query(Patent.id).filter(
                Patent.database_id == database.id,
            ).all()
        }
        view_ids = {
            int(row[0]) for row in db.execute(
                tables["patent_views"].select().with_only_columns(tables["patent_views"].c.id).where(
                    tables["patent_views"].c.database_id == database.id,
                )
            ).all()
        } if "patent_views" in tables else set()
        rule_ids = {
            int(row[0]) for row in db.execute(
                tables["automation_rules"].select().with_only_columns(tables["automation_rules"].c.id).where(
                    tables["automation_rules"].c.database_id == database.id,
                )
            ).all()
        } if "automation_rules" in tables else set()
        risk_case_ids = {
            int(row[0]) for row in db.execute(
                tables["risk_cases"].select().with_only_columns(tables["risk_cases"].c.id).where(
                    tables["risk_cases"].c.database_id == database.id,
                )
            ).all()
        } if "risk_cases" in tables else set()
        solution_ids = {
            int(row[0]) for row in db.execute(
                tables["project_solution_versions"].select().with_only_columns(tables["project_solution_versions"].c.id).where(
                    tables["project_solution_versions"].c.database_id == database.id,
                )
            ).all()
        } if "project_solution_versions" in tables else set()

        # Import evidence must go before batches and patents. Batch database
        # scope is stored in review_config for compatibility with old schema.
        import_batch_ids: set[int] = set()
        if "import_batches" in tables:
            from app.models import ImportBatch
            for batch in db.query(ImportBatch).all():
                if (batch.review_config or {}).get("database_id") == database.id or (
                    batch.created_patent_ids and patent_ids.intersection(set(batch.created_patent_ids))
                ) or db.query(Patent.id).filter(
                    Patent.id.in_(patent_ids), Patent.source_batch_id == batch.id,
                ).first() is not None:
                    import_batch_ids.add(batch.id)
        if import_batch_ids:
            # Patent.source_batch_id has no ON DELETE action in legacy schema.
            # Detach it before removing the provenance batch.
            db.query(Patent).filter(Patent.source_batch_id.in_(import_batch_ids)).update(
                {Patent.source_batch_id: None}, synchronize_session=False,
            )
        if import_batch_ids:
            source_rows = db.execute(
                tables["import_source_rows"].select().with_only_columns(tables["import_source_rows"].c.id).where(
                    tables["import_source_rows"].c.import_batch_id.in_(import_batch_ids),
                )
            ).all() if "import_source_rows" in tables else []
            source_row_ids = {int(row[0]) for row in source_rows}
            observation_rows = db.execute(
                tables["field_observations"].select().with_only_columns(tables["field_observations"].c.id).where(
                    tables["field_observations"].c.source_row_id.in_(source_row_ids),
                )
            ).all() if source_row_ids and "field_observations" in tables else []
            observation_ids = {int(row[0]) for row in observation_rows}
            # Bulk deletes bypass ORM cascades, so remove governance decisions
            # explicitly before deleting their referenced observations.
            delete_ids("governance_decisions", "observation_id", observation_ids)
            delete_ids("field_observations", "source_row_id", source_row_ids)
            delete_ids("import_source_rows", "id", source_row_ids)
            delete_ids("patent_histories", "import_batch_id", import_batch_ids)
            delete_ids("import_batches", "id", import_batch_ids)

        # Risk/project version children. Risk assessments can reference a
        # solution with RESTRICT, so remove every dependent row explicitly.
        delete_ids("risk_patent_links", "risk_case_id", risk_case_ids)
        delete_ids("risk_solution_links", "risk_case_id", risk_case_ids)
        delete_ids("risk_case_regions", "risk_case_id", risk_case_ids)
        delete_ids("risk_assessment_versions", "risk_case_id", risk_case_ids)
        delete_ids("risk_review_events", "risk_case_id", risk_case_ids)
        delete_ids("risk_cases", "id", risk_case_ids)
        delete_ids("risk_solution_links", "solution_version_id", solution_ids)
        delete_ids("risk_assessment_versions", "solution_version_id", solution_ids)
        delete_ids("project_solution_changes", "solution_version_id", solution_ids)
        delete_ids("project_solution_regions", "solution_version_id", solution_ids)
        delete_ids("project_solution_versions", "id", solution_ids)

        # View and rule children.
        delete_ids("form_share_links", "view_id", view_ids)
        delete_ids("patent_view_field_values", "view_id", view_ids)
        delete_ids("view_local_fields", "view_id", view_ids)
        delete_ids("patent_views", "id", view_ids)
        delete_ids("automation_logs", "rule_id", rule_ids)
        delete_ids("automation_logs", "patent_id", patent_ids)
        delete_ids("automation_rules", "id", rule_ids)
        delete_where("patent_export_templates", lambda table: table.c.database_id == database.id)
        delete_where("dashboards", lambda table: table.c.database_id == database.id)
        delete_where("database_memberships", lambda table: table.c.database_id == database.id)

        # Files are external to SQLite. Remove metadata after collecting the
        # paths; a missing file is harmless, but an actual deletion error is
        # surfaced so the transaction does not claim a complete cleanup.
        if "attachments" in tables:
            from app.config import settings
            attachments = db.execute(tables["attachments"].select().where(
                tables["attachments"].c.database_id == database.id,
            )).mappings().all()
            for attachment in attachments:
                file_path = settings.FILES_DIR / attachment["file_path"]
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except OSError as exc:
                        raise RuntimeError(f"无法删除附件文件 {file_path}: {exc}") from exc
            delete_where("attachments", lambda table: table.c.database_id == database.id)

        # Patent-owned records without complete ON DELETE clauses.
        delete_ids("patent_tags", "patent_id", patent_ids)
        delete_ids("patent_projects", "patent_id", patent_ids)
        delete_ids("citations", "citing_patent_id", patent_ids)
        delete_ids("citations", "cited_patent_id", patent_ids)
        delete_ids("ai_field_values", "patent_id", patent_ids)
        delete_ids("patent_identifiers", "patent_id", patent_ids)
        delete_ids("patent_histories", "patent_id", patent_ids)
        delete_ids("patent_shares", "patent_id", patent_ids)
        delete_ids("comments", "patent_id", patent_ids)
        delete_ids("patent_view_field_values", "patent_id", patent_ids)
        delete_ids("risk_patent_links", "patent_id", patent_ids)
        # duplicate_of is a self-reference without ON DELETE SET NULL. A
        # patent in another database may still point at a deleted patent;
        # preserve that external record while removing the dangling link.
        if patent_ids:
            db.query(Patent).filter(Patent.duplicate_of.in_(patent_ids)).update(
                {Patent.duplicate_of: None}, synchronize_session=False,
            )
        if patent_ids and "cross_table_links" in tables:
            link = tables["cross_table_links"]
            db.execute(link.delete().where(or_(
                and_(link.c.source_table == "patents", link.c.source_record_id.in_(patent_ids)),
                and_(link.c.target_table == "patents", link.c.target_record_id.in_(patent_ids)),
            )))
        delete_ids("patents", "id", patent_ids)

        # Remove any remaining rows that explicitly belong to this database.
        for table_name in ("patent_export_templates", "dashboards", "automation_rules", "attachments", "patent_views", "database_memberships"):
            table = tables.get(table_name)
            if table is not None and table.c.get("database_id") is not None:
                db.execute(table.delete().where(table.c.database_id == database.id))

        db.execute(tables["patent_databases"].delete().where(
            tables["patent_databases"].c.id == database.id,
        ))
        db.commit()
        return True

    @staticmethod
    def refresh_patent_count(db: Session, database_id: int) -> int:
        count = db.query(func.count(Patent.id)).filter(Patent.database_id == database_id).scalar()
        database = db.query(PatentDatabase).filter(PatentDatabase.id == database_id).first()
        if database:
            database.patent_count = count or 0
            db.add(database)
            db.commit()
        return count or 0

    @staticmethod
    def to_dict(database: PatentDatabase) -> dict:
        return {
            "id": database.id,
            "name": database.name,
            "code": database.code,
            "description": database.description,
            "color": database.color,
            "icon": database.icon,
            "is_default": database.is_default,
            "is_archived": database.is_archived,
            "patent_count": database.patent_count,
            "sort_order": database.sort_order,
            "owner_id": database.owner_id,
            "created_at": database.created_at.isoformat() if database.created_at else None,
            "updated_at": database.updated_at.isoformat() if database.updated_at else None,
        }
