from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.models.base import Base


class TaskInstance(Base):
    __tablename__ = "task_instances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meta_task_id = Column(Integer, ForeignKey("meta_tasks.id"), nullable=False, index=True)
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    instance_no = Column(String(50), unique=True, nullable=False, index=True)
    status = Column(
        String(20),
        default="pending",
        nullable=False,
    )
    auto_run = Column(Boolean, default=True)
    execution_params = Column(String, nullable=False)
    search_result_file_path = Column(String(500))
    search_result_count = Column(Integer, default=0)
    valid_data_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    search_completed_at = Column(DateTime)
    analysis_completed_at = Column(DateTime)
    download_started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)

    meta_task = relationship("MetaTask", back_populates="task_instances")
    creator = relationship("User", back_populates="task_instances")
    task_results = relationship("TaskResult", back_populates="task_instance", cascade="all, delete-orphan")
