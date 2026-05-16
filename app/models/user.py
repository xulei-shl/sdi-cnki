from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func
from sqlalchemy.orm import relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(100))
    role = Column(String(20), default="user", nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now(), nullable=False)

    meta_tasks = relationship("MetaTask", back_populates="creator")
    task_instances = relationship("TaskInstance", back_populates="creator")
    llm_configs = relationship("LlmConfig", back_populates="creator")
    operation_logs = relationship("OperationLog", back_populates="user")
    user_prompts = relationship("SystemPrompt", back_populates="creator")
    prompt_templates = relationship("PromptTemplate", back_populates="creator")
