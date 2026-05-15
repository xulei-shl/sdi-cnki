from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.system_config import SystemConfig
from app.utils.exceptions import NotFoundError
from app.routers import get_current_user_from_header, require_admin_user

router = APIRouter()


class SystemConfigUpdate(BaseModel):
    value: str


@router.get("/configs")
async def list_configs(
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemConfig).order_by(SystemConfig.key))
    configs = result.scalars().all()
    return {
        "items": [
            {
                "key": c.key,
                "value": c.value,
                "description": c.description,
                "updated_by": c.updated_by,
                "updated_at": c.updated_at.isoformat() if c.updated_at else "",
            }
            for c in configs
        ]
    }


@router.put("/configs/{key}")
async def update_config(
    key: str,
    data: SystemConfigUpdate,
    admin = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    config = result.scalar_one_or_none()
    if not config:
        raise NotFoundError("System config", key)
    config.value = data.value
    config.updated_by = admin.id
    await db.commit()
    return {"key": config.key, "value": config.value}


@router.get("/stats")
async def get_stats(
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    from app.models.meta_task import MetaTask
    from app.models.task_instance import TaskInstance
    mt_count = (await db.execute(select(func.count(MetaTask.id)))).scalar()
    ti_count = (await db.execute(select(func.count(TaskInstance.id)))).scalar()
    running = (await db.execute(select(func.count(TaskInstance.id)).where(TaskInstance.status == "running"))).scalar()
    return {
        "meta_task_count": mt_count,
        "task_instance_count": ti_count,
        "running_instances": running,
    }
