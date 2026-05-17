from __future__ import annotations

from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_config import SystemConfig
from app.utils.logging import get_logger

logger = get_logger("wecom_notifier")

CONFIG_KEY = "webhook_enterprise_wechat"


async def load_webhook_url(db: AsyncSession) -> Optional[str]:
    """从 system_configs 表读取企微 Webhook URL。"""
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.key == CONFIG_KEY)
    )
    config = result.scalar_one_or_none()
    if config and config.value:
        return config.value.strip()
    return None


def _build_markdown(instance_data: dict) -> str:
    """构建企业微信 Markdown 消息。"""
    status = instance_data.get("status", "")
    is_failure = status == "failed"
    stage = instance_data.get("stage", "任务执行")
    status_icon = "❌" if is_failure else "✅"
    status_text = "失败" if is_failure else "完成"
    stats = instance_data.get("stats", {})

    parts = [
        f"## {'📋'} {stage}{'失败' if is_failure else '完成'}通知\n",
        f"**任务名称**: {instance_data.get('meta_task_name', '-')}",
        f"**执行用户**: {instance_data.get('username', '-')}",
        f"**任务编号**: {instance_data.get('instance_no', '-')}",
        f"**执行状态**: {status_icon} {status_text}",
        f"**执行时间**: {instance_data.get('started_at', '-')} ~ {instance_data.get('completed_at', '-')}\n",
        "**数据统计**：",
    ]
    if is_failure:
        parts.append(f"> 失败原因：{instance_data.get('error_message', '未知错误')}")
    else:
        parts.extend([
            f"- 检索总数：{stats.get('total', 0)} 条",
            f"- 有效数据：{stats.get('valid', 0)} 条  （去重 {stats.get('duplicate', 0)} 条）",
            f"- 分析完成：{stats.get('analyzed', 0)} 条",
            f"- 下载成功：{stats.get('downloaded', 0)} 条",
        ])
    return "\n".join(parts)


async def send_notification(db: AsyncSession, instance_data: dict) -> None:
    """向企业微信群发送任务通知。失败时不抛出异常，仅记录日志。"""
    try:
        webhook_url = await load_webhook_url(db)
        if not webhook_url:
            logger.info("Webhook URL 未配置，跳过通知")
            return

        markdown_content = _build_markdown(instance_data)
        payload = {"msgtype": "markdown", "markdown": {"content": markdown_content}}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code != 200:
                logger.error(f"企微通知发送失败: HTTP {resp.status_code} {resp.text}")
            else:
                logger.info("企微通知发送成功")
    except Exception as e:
        logger.error(f"企微通知异常（已忽略）: {e}")
