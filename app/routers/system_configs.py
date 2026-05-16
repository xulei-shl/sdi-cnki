from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

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


@router.post("/configs/{key}/test")
async def test_config(
    key: str,
    data: SystemConfigUpdate,
    admin = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    if key != "webhook_enterprise_wechat":
        raise HTTPException(status_code=400, detail="该配置项不支持测试")
    url = data.value.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Webhook URL 为空")
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": "## 测试消息\n这是一条来自 SDI-CNKI 系统的测试通知。\n> 如果您收到此消息，说明 Webhook 配置正确。"
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"发送失败: HTTP {resp.status_code}",
        )
    return {"message": "测试通知发送成功"}


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
