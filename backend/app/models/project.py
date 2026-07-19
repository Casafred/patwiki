"""项目模型。"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50))
    product_id = Column(Integer, ForeignKey("products.id"))
    description = Column(Text)
    module = Column(String(200))
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    product = relationship("Product", back_populates="projects")
    patents = relationship("Patent", secondary="patent_projects", back_populates="projects")
