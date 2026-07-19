"""组织/人员/产品线/产品 模型。"""
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    members = relationship("Person", back_populates="department")


class Person(Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255))
    department_id = Column(Integer, ForeignKey("departments.id"))
    role = Column(String(100))
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    department = relationship("Department", back_populates="members")
    owned_products = relationship("Product", back_populates="owner")


class ProductLine(Base):
    __tablename__ = "product_lines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True, nullable=False)
    description = Column(Text)
    code = Column(String(50), unique=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    products = relationship("Product", back_populates="product_line")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50))
    product_line_id = Column(Integer, ForeignKey("product_lines.id"))
    owner_id = Column(Integer, ForeignKey("people.id"))
    description = Column(Text)
    category = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    product_line = relationship("ProductLine", back_populates="products")
    owner = relationship("Person", back_populates="owned_products")
    projects = relationship("Project", back_populates="product")
    patents = relationship("Patent", back_populates="product")
