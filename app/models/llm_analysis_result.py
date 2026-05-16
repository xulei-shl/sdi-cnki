from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.utils import timezone


class LlmAnalysisResult(Base):
    __tablename__ = "llm_analysis_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_result_id = Column(Integer, ForeignKey("task_results.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    task_instance_id = Column(Integer, ForeignKey("task_instances.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(20), default="pending", nullable=False)
    raw_response = Column(Text)
    parsed_result = Column(Text)
    error_message = Column(Text)
    llm_config_id = Column(Integer)
    attempt_count = Column(Integer, default=0)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, default=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)

    task_result = relationship("TaskResult", back_populates="llm_analysis")
    task_instance = relationship("TaskInstance")
