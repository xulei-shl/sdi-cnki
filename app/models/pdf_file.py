from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import relationship

from app.models.base import Base


class PdfFile(Base):
    __tablename__ = "pdf_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    original_url = Column(String(500), index=True)
    pdf_path = Column(String(500), nullable=False)
    file_hash = Column(String(64))
    file_size = Column(Integer, default=0)
    ref_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)

    download_results = relationship("DownloadResult", back_populates="pdf_file_ref")
