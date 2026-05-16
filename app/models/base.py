from __future__ import annotations

from sqlalchemy import Column, DateTime, text
from sqlalchemy.orm import DeclarativeBase

from app.utils import timezone


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at = Column(DateTime, default=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)
