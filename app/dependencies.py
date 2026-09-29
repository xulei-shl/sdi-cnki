from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.utils.exceptions import AuthenticationError, PermissionDeniedError

settings = get_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise AuthenticationError("Invalid or expired token")


def create_artifact_token(job_id: int, ttl_minutes: int) -> str:
    """签发短期文件下载令牌，使下载 URL 可脱离 API Key 使用。"""
    expire = datetime.utcnow() + timedelta(minutes=ttl_minutes)
    return jwt.encode(
        {"sub": str(job_id), "type": "artifact", "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_artifact_token(token: str, job_id: int) -> None:
    """校验文件下载令牌；不匹配则抛 AuthenticationError。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise AuthenticationError("Invalid or expired artifact token")
    if payload.get("type") != "artifact" or payload.get("sub") != str(job_id):
        raise AuthenticationError("Artifact token does not match the requested job")


async def get_current_user(db: AsyncSession, token: str) -> User:
    payload = decode_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationError("Invalid token payload")
    result = await db.execute(select(User).where(User.id == int(user_id), User.is_active == True))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationError("User not found or inactive")
    return user


def require_admin(user: User) -> None:
    if user.role != "admin":
        raise PermissionDeniedError("Admin access required")
