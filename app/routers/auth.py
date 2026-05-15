from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.user import User
from app.utils.exceptions import AuthenticationError
from app.utils.oplog import log_operation
from app.routers.deps import get_current_user_from_header

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise AuthenticationError("Invalid username or password")
    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    refresh_token = create_refresh_token({"sub": str(user.id), "role": user.role})
    await log_operation(db, user.id, "login", "auth", details=f"User {user.username} logged in")
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={"id": user.id, "username": user.username, "role": user.role, "email": user.email},
    )


@router.post("/refresh")
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if payload.get("type") != "refresh":
        raise AuthenticationError("Invalid token type")
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == int(user_id), User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise AuthenticationError("User not found")
    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    refresh_token = create_refresh_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={"id": user.id, "username": user.username, "role": user.role, "email": user.email},
    )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user_from_header)):
    return {"message": "Logged out successfully"}


@router.get("/me")
async def me(current_user: User = Depends(get_current_user_from_header)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "email": current_user.email,
        "is_active": current_user.is_active,
    }
