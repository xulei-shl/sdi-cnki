from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class DownloadResult(Base):
    __tablename__ = "download_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_result_id = Column(Integer, ForeignKey("task_results.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    task_instance_id = Column(Integer, ForeignKey("task_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    pdf_file_id = Column(Integer, ForeignKey("pdf_files.id", ondelete="SET NULL"), index=True)

    download_status = Column(String(20), default="pending", nullable=False)
    pdf_path = Column(String(500))
    file_size = Column(Integer)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    task_result = relationship("TaskResult", back_populates="download_result")
    pdf_file_ref = relationship("PdfFile", back_populates="download_results")
