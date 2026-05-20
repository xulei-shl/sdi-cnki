from __future__ import annotations

from typing import Optional

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_notification_config import UserNotificationConfig
from app.utils.logging import get_logger

logger = get_logger("wecom_notifier")


async def load_webhook_url(db: AsyncSession, user_id: int) -> Optional[str]:
    """从 user_notification_configs 表读取指定用户的 Webhook URL。"""
    result = await db.execute(
        select(UserNotificationConfig).where(
            UserNotificationConfig.user_id == user_id,
            UserNotificationConfig.enabled == True,
        )
    )
    config = result.scalar_one_or_none()
    if config and config.webhook_url:
        return config.webhook_url.strip()
    return None


async def _compute_detailed_stats(db: AsyncSession, instance_id: int) -> dict:
    """查询任务实例的详细统计数据。"""
    import json
    from app.models.llm_analysis_result import LlmAnalysisResult
    from app.models.download_result import DownloadResult
    from app.models.task_result import TaskResult

    llm_completed = 0
    llm_passed = 0
    llm_rejected = 0
    llm_failed = 0
    for row in (
        await db.execute(
            select(LlmAnalysisResult.status, LlmAnalysisResult.parsed_result)
            .where(LlmAnalysisResult.task_instance_id == instance_id)
        )
    ).all():
        if row.status == "completed":
            llm_completed += 1
            if row.parsed_result:
                try:
                    p = json.loads(row.parsed_result)
                    is_rel = p.get("is_relevant")
                    if is_rel is None:
                        is_rel = p.get("is_target_topic")
                    if is_rel is True:
                        llm_passed += 1
                    elif is_rel is False:
                        llm_rejected += 1
                except (json.JSONDecodeError, TypeError):
                    pass
        elif row.status == "failed":
            llm_failed += 1

    manual_passed = (
        await db.execute(
            select(func.count(TaskResult.id)).where(
                TaskResult.task_instance_id == instance_id,
                TaskResult.is_duplicate == False,
                TaskResult.is_passed == True,
            )
        )
    ).scalar() or 0
    manual_rejected = (
        await db.execute(
            select(func.count(TaskResult.id)).where(
                TaskResult.task_instance_id == instance_id,
                TaskResult.is_duplicate == False,
                TaskResult.is_passed == False,
            )
        )
    ).scalar() or 0

    download_success = 0
    download_failed = 0
    for row in (
        await db.execute(
            select(
                DownloadResult.download_status,
                func.count(DownloadResult.id),
            )
            .where(DownloadResult.task_instance_id == instance_id)
            .group_by(DownloadResult.download_status)
        )
    ).all():
        if row[0] == "completed":
            download_success = row[1]
        elif row[0] == "failed":
            download_failed = row[1]

    return {
        "llm_completed": llm_completed,
        "llm_passed": llm_passed,
        "llm_rejected": llm_rejected,
        "llm_failed": llm_failed,
        "manual_passed": manual_passed,
        "manual_rejected": manual_rejected,
        "download_success": download_success,
        "download_failed": download_failed,
    }


def _build_markdown(instance_data: dict) -> str:
    """构建企业微信 Markdown 消息。"""
    status = instance_data.get("status", "")
    is_failure = status == "failed"
    stage = instance_data.get("stage", "任务执行")
    status_icon = "❌" if is_failure else "✅"
    status_text = "失败" if is_failure else "完成"
    stats = instance_data.get("stats", {})
    detail = instance_data.get("detail_stats", {})

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
        parts.append(f"- 检索总数：{stats.get('total', 0)} 条")
        parts.append(f"- 有效数据：{stats.get('valid', 0)} 条  （去重 {stats.get('duplicate', 0)} 条）")
        if detail:
            parts.append(
                f"- **LLM分析**：已完成 {detail.get('llm_completed', 0)}"
                f"（通过 {detail.get('llm_passed', 0)}/拒绝 {detail.get('llm_rejected', 0)}）"
                f" 失败 {detail.get('llm_failed', 0)}"
            )
            parts.append(
                f"- **人工审核**：通过 {detail.get('manual_passed', 0)} / 拒绝 {detail.get('manual_rejected', 0)}"
            )
            parts.append(
                f"- **下载**：成功 {detail.get('download_success', 0)} / 失败 {detail.get('download_failed', 0)}"
            )
        else:
            parts.append(f"- 分析完成：{stats.get('analyzed', 0)} 条")
            parts.append(f"- 下载成功：{stats.get('downloaded', 0)} 条")
    return "\n".join(parts)


async def send_notification(db: AsyncSession, instance_data: dict, user_id: int | None = None) -> None:
    """向企业微信群发送任务通知。失败时不抛出异常，仅记录日志。

    Args:
        db: 数据库会话
        instance_data: 任务实例数据
        user_id: 用户ID，用于查找该用户的 webhook 配置。为 None 时从 instance_data 中取。
    """
    try:
        if user_id is None:
            user_id = instance_data.get("user_id")
        if not user_id:
            logger.info("未指定用户，跳过通知")
            return

        webhook_url = await load_webhook_url(db, user_id)
        if not webhook_url:
            logger.info(f"用户 {user_id} 未配置 Webhook，跳过通知")
            return

        instance_id = instance_data.get("instance_id")
        if instance_id:
            instance_data["detail_stats"] = await _compute_detailed_stats(db, instance_id)

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
