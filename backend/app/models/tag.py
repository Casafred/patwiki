"""标签与标签组模型。"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class TagGroup(Base):
    __tablename__ = "tag_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    color = Column(String(20))
    created_at = Column(DateTime, server_default=func.now())

    tags = relationship("Tag", back_populates="group")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    group_id = Column(Integer, ForeignKey("tag_groups.id"))
    color = Column(String(20))
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    group = relationship("TagGroup", back_populates="tags")
    patents = relationship("Patent", secondary="patent_tags", back_populates="tags")

    __table_args__ = (UniqueConstraint("name", "group_id", name="_tag_name_group_uc"),)
