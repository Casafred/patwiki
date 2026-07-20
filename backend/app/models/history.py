"""专利修改历史模型。

记录每条专利的修改记录：哪个字段、旧值、新值、何时、由谁修改。
用于详情页展示修改时间线和审计追溯。
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PatentHistory(Base):
    __tablename__ = "patent_histories"

    id = Column(Integer, primary_key=True, index=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False, index=True)
    # 修改的字段名（系统字段名或 custom_fields.xxx / ai_fields.xxx）
    field_key = Column(String(200), nullable=False, index=True)
    field_display_name = Column(String(200))
    # 旧值/新值（字符串化存储，便于任意类型）
    old_value = Column(Text)
    new_value = Column(Text)
    # 修改来源：manual（手动编辑）/ import（导入）/ ai（AI生成）/ bulk（批量编辑）/ api
    source = Column(String(50), default="manual")
    # 修改人（用户名，可空）
    changed_by = Column(String(100))
    # 修改时间
    created_at = Column(DateTime, server_default=func.now(), index=True)

    patent = relationship("Patent", back_populates="histories")
