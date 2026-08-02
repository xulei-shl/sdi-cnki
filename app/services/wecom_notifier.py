from __future__ import annotations

import json
from typing import Optional

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_notification_config import UserNotificationConfig
from app.utils.logging import get_logger

logger = get_logger("wecom_notifier")


def _parse_flags(raw: str | None) -> dict[str, bool]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _check_module_flag(flags: dict[str, bool], module_key: str | None) -> bool:
    if not module_key:
        return True
    if not flags:
        return True
    return flags.get(module_key, True)


async def load_user_config(db: AsyncSession, user_id: int) -> UserNotificationConfig | None:
    result = await db.execute(
        select(UserNotificationConfig).where(UserNotificationConfig.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _compute_detailed_stats(db: AsyncSession, instance_id: int) -> dict:
    """查询任务实例的详细统计数据。"""
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


async def send_wecom_notification(
    db: AsyncSession,
    config: UserNotificationConfig,
    instance_data: dict,
    module_key: str | None = None,
) -> None:
    """向企业微信群发送任务通知。失败时不抛出异常，仅记录日志。

    Args:
        db: 数据库会话
        config: 用户通知配置对象
        instance_data: 任务实例数据
        module_key: 模块标识，用于检查 module_flags 开关
    """
    try:
        if not config.webhook_url:
            logger.info("用户未配置 Webhook URL，跳过企微通知")
            return

        flags = _parse_flags(config.module_flags)
        if not _check_module_flag(flags, module_key):
            logger.info(f"企微通知被 module_flags 过滤（module_key={module_key}, status={instance_data.get('status')}）")
            return

        instance_id = instance_data.get("instance_id")
        if instance_id:
            instance_data["detail_stats"] = await _compute_detailed_stats(db, instance_id)

        markdown_content = _build_markdown(instance_data)
        payload = {"msgtype": "markdown", "markdown": {"content": markdown_content}}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(config.webhook_url.strip(), json=payload)
            if resp.status_code != 200:
                logger.error(f"企微通知发送失败: HTTP {resp.status_code} {resp.text}")
            else:
                logger.info("企微通知发送成功")
    except Exception as e:
        logger.error(f"企微通知异常（已忽略）: {e}")