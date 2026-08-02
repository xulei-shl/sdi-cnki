from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_notification_config import UserNotificationConfig
from app.services.wecom_notifier import load_user_config, send_wecom_notification
from app.services.wecom_notifier import _parse_flags, _check_module_flag
from app.services.email_notifier import send_email_notification
from app.utils.logging import get_logger

logger = get_logger("notification")


async def send_notification(
    db: AsyncSession,
    instance_data: dict,
    user_id: int | None = None,
    module_key: str | None = None,
) -> None:
    """统一通知入口，按用户配置发送企业微信和/或邮件通知。

    Args:
        db: 数据库会话
        instance_data: 任务实例数据
        user_id: 用户ID，为 None 时从 instance_data 中取
        module_key: 模块标识（如 "检索"/"分析"/"下载"），用于检查 module_flags
    """
    try:
        if user_id is None:
            user_id = instance_data.get("user_id")
        if not user_id:
            logger.info("未指定用户，跳过通知")
            return

        config = await load_user_config(db, user_id)
        if not config:
            logger.info(f"用户 {user_id} 未配置通知，跳过")
            return

        is_failure = instance_data.get("status", "") == "failed"

        # 企业微信通道
        if config.enabled and config.webhook_url:
            wecom_flags = _parse_flags(config.module_flags)
            if _check_module_flag(wecom_flags, module_key, is_failure):
                await send_wecom_notification(db, config, instance_data, module_key)
            else:
                logger.info(f"企微通知被 module_flags 过滤（module_key={module_key}）")
        else:
            logger.info(f"用户 {user_id} 企微通知未启用，跳过")

        # 邮件通道
        if config.email_enabled:
            email_flags = _parse_flags(config.email_module_flags)
            if _check_module_flag(email_flags, module_key, is_failure):
                await send_email_notification(db, config, instance_data)
            else:
                logger.info(f"邮件通知被 email_module_flags 过滤（module_key={module_key}）")
        else:
            logger.info(f"用户 {user_id} 邮件通知未启用，跳过")

    except Exception as e:
        logger.error(f"通知发送异常（已忽略）: {e}")