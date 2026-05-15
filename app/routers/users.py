from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import hash_password
from app.models.user import User
from app.utils.exceptions import NotFoundError, ValidationError
from app.utils.oplog import log_operation
from app.routers import get_current_user_from_header, require_admin_user

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "user"


class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool
    created_at: str


@router.get("")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    users = result.scalars().all()
    count_stmt = select(func.count(User.id))
    total = (await db.execute(count_stmt)).scalar()
    return {
        "items": [
            {"id": u.id, "username": u.username, "email": u.email, "role": u.role, "is_active": u.is_active,
             "created_at": u.created_at.isoformat() if u.created_at else ""}
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("")
async def create_user(
    data: UserCreate,
    admin: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.username == data.username))
    if existing.scalar_one_or_none():
        raise ValidationError("Username already exists")
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        email=data.email,
        role=data.role if data.role in ("admin", "user") else "user",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await log_operation(db, admin.id, "create", "user", user.id, f"Created user {user.username}")
    return {"id": user.id, "username": user.username, "role": user.role, "email": user.email}


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    data: UserUpdate,
    admin: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User", user_id)
    if data.username is not None:
        user.username = data.username
    if data.password:
        user.password_hash = hash_password(data.password)
    if data.email is not None:
        user.email = data.email
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    await db.commit()
    await log_operation(db, admin.id, "update", "user", user_id, f"Updated user {user.username}")
    return {"id": user.id, "username": user.username, "role": user.role, "email": user.email, "is_active": user.is_active}


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User", user_id)
    await db.delete(user)
    await db.commit()
    await log_operation(db, admin.id, "delete", "user", user_id, f"Deleted user {user.username}")
    return {"message": "User deleted"}
