from __future__ import annotations
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import relationship
from app.models.base import Base
from app.utils import timezone

class SystemPrompt(Base):
    __tablename__ = "system_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    version = Column(String(20), default="1.0")
    tags = Column(String(200))
    is_active = Column(Boolean, default=True)
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)
    updated_at = Column(DateTime, default=timezone.now, onupdate=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)

    creator = relationship("User", back_populates="user_prompts")
