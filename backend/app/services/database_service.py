"""专利库（Database）服务——P0-11 新增。

库是专利数据的顶层品类容器，导入时强制选择，去重范围限定在库内。
"""
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

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
        - force=True：级联删除库内所有专利，然后删库。默认库仍不可删。
        """
        # 不允许删除默认库
        if database.is_default:
            return False
        patent_count = db.query(func.count(Patent.id)).filter(Patent.database_id == database.id).scalar()
        if patent_count and patent_count > 0:
            if not force:
                return False
            # force=True：级联删除库内所有专利
            db.query(Patent).filter(Patent.database_id == database.id).delete(
                synchronize_session=False
            )
        db.delete(database)
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
