from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.utils import timezone


class MetaTask(Base):
    __tablename__ = "meta_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    prompt_template_id = Column(Integer, ForeignKey("system_prompts.id"))
    search_params = Column(String, nullable=False)
    schedule_cron = Column(String(100))
    is_periodic = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True, index=True)
    last_executed_at = Column(DateTime)
    execution_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)
    updated_at = Column(DateTime, default=timezone.now, onupdate=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)

    creator = relationship("User", back_populates="meta_tasks")
    llm_config_links = relationship("MetaTaskLlmConfig", back_populates="meta_task", cascade="all, delete-orphan")
    task_instances = relationship("TaskInstance", back_populates="meta_task")
