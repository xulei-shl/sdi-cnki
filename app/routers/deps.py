from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import decode_token
from app.models.user import User
from app.utils.exceptions import AuthenticationError


async def get_current_user_from_header(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization:
        raise AuthenticationError("Missing authorization header")
    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == int(user_id), User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise AuthenticationError("User not found or inactive")
    return user


async def require_admin_user(current_user: User = Depends(get_current_user_from_header)) -> User:
    if current_user.role != "admin":
        from app.utils.exceptions import PermissionDeniedError
        raise PermissionDeniedError("Admin access required")
    return current_user
