from __future__ import annotations

from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.operation_log import OperationLog


async def log_operation(
    db: AsyncSession,
    user_id: int,
    action: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    details: str | None = None,
    ip_address: str | None = None,
) -> OperationLog:
    entry = OperationLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.commit()
    return entry
