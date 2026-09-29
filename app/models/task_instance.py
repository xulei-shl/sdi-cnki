from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.utils import timezone


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
    # 来源：web=网页触发，api=开放接口触发。api 任务不在网页列表中展示。
    source = Column(String(20), default="web", nullable=False)
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
    # 检索过程进度上报（跨进程可见，供开放接口轮询；网页 SSE 不使用）
    progress_stage = Column(String(30))
    progress_message = Column(String(200))
    progress_current = Column(Integer)
    progress_total = Column(Integer)
    heartbeat_at = Column(DateTime)
    created_at = Column(DateTime, default=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)

    meta_task = relationship("MetaTask", back_populates="task_instances")
    creator = relationship("User", back_populates="task_instances")
    task_results = relationship("TaskResult", back_populates="task_instance", cascade="all, delete-orphan")
