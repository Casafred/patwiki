"""专利库（Database）模型——P0-8 新增。

库是专利数据的顶层品类归属，例如"电钻专利数据库"、"传感器专利数据库"。
导入时强制选择库，去重范围限定在库内。
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PatentDatabase(Base):
    __tablename__ = "patent_databases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50), unique=True, index=True)
    description = Column(Text)
    color = Column(String(20))
    icon = Column(String(50))
    is_default = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    patent_count = Column(Integer, default=0)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    patents = relationship("Patent", back_populates="database")
