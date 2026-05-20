from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import Base


class MetaTaskDedupScope(Base):
    __tablename__ = "meta_task_dedup_scopes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meta_task_id = Column(Integer, ForeignKey("meta_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    dedup_meta_task_id = Column(Integer, ForeignKey("meta_tasks.id", ondelete="CASCADE"), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("meta_task_id", "dedup_meta_task_id", name="idx_mtds_unique"),
    )

    meta_task = relationship("MetaTask", back_populates="dedup_scope_links", foreign_keys=[meta_task_id])
    dedup_meta_task = relationship("MetaTask", foreign_keys=[dedup_meta_task_id])
