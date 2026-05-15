from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import Base


class ExportTask(Base):
    __tablename__ = "export_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_instance_id = Column(Integer, ForeignKey("task_instances.id", ondelete="CASCADE"), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="pending")
    file_path = Column(String(500))
    file_size = Column(Integer)
    error_message = Column(Text)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)

    task_instance = relationship("TaskInstance", backref="export_tasks")
    creator = relationship("User", backref="export_tasks")
