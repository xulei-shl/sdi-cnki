from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.user_notification_config import UserNotificationConfig
from app.routers import require_admin_user

from fastapi import APIRouter, Depends

router = APIRouter()


@router.get("/user-notification-configs")
async def list_all_notification_configs(
    admin=Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(User, UserNotificationConfig)
        .outerjoin(UserNotificationConfig, User.id == UserNotificationConfig.user_id)
        .order_by(User.username)
    )
    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for user, config in rows:
        items.append({
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "webhook_url": config.webhook_url if config else None,
            "enabled": config.enabled if config else False,
            "email_enabled": config.email_enabled if config else False,
            "email_to": config.email_to if config else None,
            "module_flags": config.module_flags if config else None,
            "email_module_flags": config.email_module_flags if config else None,
            "updated_at": config.updated_at.isoformat() if config and config.updated_at else None,
        })

    return {"items": items, "total": len(items)}