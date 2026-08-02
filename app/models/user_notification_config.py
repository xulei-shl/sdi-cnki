from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.utils import timezone


class UserNotificationConfig(Base):
    __tablename__ = "user_notification_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    webhook_url = Column(Text, nullable=True)
    enabled = Column(Boolean, default=False)
    email_enabled = Column(Boolean, default=False)
    email_to = Column(Text, nullable=True)
    module_flags = Column(Text, nullable=True)
    email_module_flags = Column(Text, nullable=True)
    created_at = Column(DateTime, default=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)
    updated_at = Column(DateTime, default=timezone.now, onupdate=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)

    user = relationship("User", backref="notification_config")
