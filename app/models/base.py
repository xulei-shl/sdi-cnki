from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
