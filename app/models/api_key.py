from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String, text

from app.models.base import Base
from app.utils import timezone


class ApiKey(Base):
    """外部调用方 API Key（供 agent / 第三方系统访问开放检索接口）。

    只保存 bcrypt 哈希与可检索前缀，明文仅在创建时返回一次。
    """

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(16), nullable=False, index=True)
    key_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=timezone.now, server_default=text("(datetime('now', 'localtime'))"), nullable=False)
