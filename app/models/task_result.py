from __future__ import annotations

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class TaskResult(Base):
    __tablename__ = "task_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_instance_id = Column(Integer, ForeignKey("task_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    duplicate_ref_id = Column(Integer, ForeignKey("task_results.id"))

    title = Column(String(500))
    authors = Column(String(500))
    organ = Column(String(500))
    source_journal = Column(String(300))
    first_duty = Column(String(200))
    keywords = Column(String(500))
    abstract = Column(Text)
    publish_time = Column(String(50))
    fund = Column(String(500))
    publish_year = Column(Integer)
    volume = Column(String(50))
    issue = Column(String(50))
    pages = Column(String(50))
    clc = Column(String(100))
    issn = Column(String(50))
    original_url = Column(String(500))
    doi = Column(String(200))
    reference_format = Column(Text)

    title_normalized = Column(String(500), index=True)
    source_journal_normalized = Column(String(300))
    is_duplicate = Column(Boolean, default=False, index=True)
    is_passed = Column(Boolean, default=False)

    local_pdf_path = Column(String(500))

    task_instance = relationship("TaskInstance", back_populates="task_results")
    llm_analysis = relationship("LlmAnalysisResult", back_populates="task_result", uselist=False, cascade="all, delete-orphan")
    download_result = relationship("DownloadResult", back_populates="task_result", uselist=False, cascade="all, delete-orphan")
