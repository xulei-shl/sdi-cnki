from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import Base


class MetaTaskLlmConfig(Base):
    __tablename__ = "meta_task_llm_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meta_task_id = Column(Integer, ForeignKey("meta_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    llm_config_id = Column(Integer, ForeignKey("llm_configs.id"), nullable=False, index=True)
    priority = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("meta_task_id", "llm_config_id", name="idx_mtlc_unique"),
    )

    meta_task = relationship("MetaTask", back_populates="llm_config_links")
    llm_config = relationship("LlmConfig", back_populates="task_links")
