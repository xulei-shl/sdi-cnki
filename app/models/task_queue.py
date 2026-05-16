from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, Text, text

from app.models.base import Base
from app.utils import timezone


class TaskQueueItem(Base):
    __tablename__ = "task_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    queue_type = Column(String(20), nullable=False)
    task_type = Column(String(50), nullable=False)
    task_key = Column(String(100), unique=True)
    params_json = Column(Text, nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    priority = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    timeout_sec = Column(Integer, default=1800)
    error_message = Column(Text)
    result_json = Column(Text)
    worker_task_id = Column(String(100))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)
