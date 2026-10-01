from __future__ import annotations

from sqlalchemy import REAL, Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.utils import timezone


class JevScore(Base):
    """单篇文献的 JEV 相关性评分。

    与 `LlmAnalysisResult` 并存而非复用：后者的 `parsed_result` 被网页端按
    `json_extract($.is_target_topic)` 直接过滤，且 `task_result_id` 上有 unique
    约束——复用会让两种引擎的结果互相覆盖、污染网页筛选。独立表让主流程后续
    迁移时可以与 LLM 结果并行跑同一批文献做口径对比，再决定切换。

    失败语义：`status='failed'` 时 `relevance_score` 为 NULL（不是 0）。
    「没打上分」与「打了低分」必须可区分，否则下游无法正确过滤。
    """

    __tablename__ = "jev_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_result_id = Column(
        Integer, ForeignKey("task_results.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    task_instance_id = Column(
        Integer, ForeignKey("task_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status = Column(String(20), default="pending", nullable=False)
    relevance_score = Column(REAL)
    relevance_level = Column(Integer)
    noul_prob = Column(REAL)
    level_confidence = Column(REAL)
    latency_ms = Column(Integer)
    raw_response = Column(Text)
    error_message = Column(Text)
    finished_at = Column(DateTime)
    created_at = Column(
        DateTime,
        default=timezone.now,
        server_default=text("(datetime('now', 'localtime'))"),
        nullable=False,
    )

    task_result = relationship("TaskResult", back_populates="jev_score")
    task_instance = relationship("TaskInstance")