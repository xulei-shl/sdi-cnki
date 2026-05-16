from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.utils import timezone


class LlmConfig(Base):
    __tablename__ = "llm_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    model_name = Column(String(100), nullable=False)
    api_key_encrypted = Column(String(500), nullable=False)
    api_endpoint = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)
    updated_at = Column(DateTime, default=timezone.now, onupdate=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)

    creator = relationship("User", back_populates="llm_configs")
    task_links = relationship("MetaTaskLlmConfig", back_populates="llm_config")
