"""公式字段依赖关系模型。"""
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class FormulaDependency(Base):
    """记录公式字段引用的字段，供循环检测和增量重算使用。"""

    __tablename__ = "formula_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "formula_field_key",
            "depends_on_field_key",
            name="uq_formula_dependency",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    formula_field_key = Column(String(100), nullable=False, index=True)
    depends_on_field_key = Column(String(100), nullable=False, index=True)
    depends_on_type = Column(String(20), nullable=False, default="system")
    created_at = Column(DateTime, server_default=func.now())
