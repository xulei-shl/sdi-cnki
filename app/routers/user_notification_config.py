from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.database import get_db
from app.models.user_notification_config import UserNotificationConfig
from app.routers import get_current_user_from_header
from app.services.email_notifier import send_test_email
from app.utils.exceptions import NotFoundError

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


class NotificationConfigUpdate(BaseModel):
    webhook_url: str | None = None
    enabled: bool | None = None
    email_enabled: bool | None = None
    email_to: str | None = None
    module_flags: str | None = None
    email_module_flags: str | None = None


@router.get("/notification-config")
async def get_notification_config(
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserNotificationConfig).where(UserNotificationConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        return {
            "webhook_url": None,
            "enabled": False,
            "email_enabled": False,
            "email_to": None,
            "module_flags": None,
            "email_module_flags": None,
        }
    return {
        "webhook_url": config.webhook_url,
        "enabled": config.enabled,
        "email_enabled": config.email_enabled,
        "email_to": config.email_to,
        "module_flags": config.module_flags,
        "email_module_flags": config.email_module_flags,
    }


@router.put("/notification-config")
async def update_notification_config(
    data: NotificationConfigUpdate,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserNotificationConfig).where(UserNotificationConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        config = UserNotificationConfig(user_id=current_user.id)
        db.add(config)
    if data.webhook_url is not None:
        config.webhook_url = data.webhook_url.strip() if data.webhook_url else None
    if data.enabled is not None:
        config.enabled = data.enabled
    if data.email_enabled is not None:
        config.email_enabled = data.email_enabled
    if data.email_to is not None:
        config.email_to = data.email_to.strip() if data.email_to else None
    if data.module_flags is not None:
        config.module_flags = data.module_flags if data.module_flags else None
    if data.email_module_flags is not None:
        config.email_module_flags = data.email_module_flags if data.email_module_flags else None
    await db.commit()
    return {
        "webhook_url": config.webhook_url,
        "enabled": config.enabled,
        "email_enabled": config.email_enabled,
        "email_to": config.email_to,
        "module_flags": config.module_flags,
        "email_module_flags": config.email_module_flags,
    }


class TestWebhookInput(BaseModel):
    webhook_url: str


@router.post("/notification-config/test")
async def test_notification_config(
    data: TestWebhookInput,
    current_user = Depends(get_current_user_from_header),
):
    url = data.webhook_url.strip()
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


class TestEmailInput(BaseModel):
    email_to: str


@router.post("/notification-config/test-email")
async def test_email_config(
    data: TestEmailInput,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    email = data.email_to.strip()
    if not email:
        raise HTTPException(status_code=400, detail="邮箱地址为空")
    try:
        await send_test_email(db, email)
        return {"message": "测试邮件发送成功"}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))