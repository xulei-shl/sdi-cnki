from __future__ import annotations

from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_config import SystemConfig
from app.models.user import User
from app.models.user_notification_config import UserNotificationConfig
from app.utils.logging import get_logger

logger = get_logger("email_notifier")


async def _load_system_config(db: AsyncSession, key: str) -> str | None:
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    cfg = result.scalar_one_or_none()
    return cfg.value.strip() if cfg and cfg.value else None


async def _load_email_recipient(
    db: AsyncSession,
    config: UserNotificationConfig,
    user_id: int,
) -> str | None:
    if config.email_to:
        return config.email_to.strip()
    result = await db.execute(select(User.email).where(User.id == user_id))
    user_email = result.scalar_one_or_none()
    if user_email:
        return user_email.strip()
    return None


def _build_html(instance_data: dict) -> str:
    status = instance_data.get("status", "")
    is_failure = status == "failed"
    stage = instance_data.get("stage", "任务执行")
    status_text = "失败" if is_failure else "完成"
    stats = instance_data.get("stats", {})
    detail = instance_data.get("detail_stats", {})

    rows = [
        f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>任务名称</td><td style='padding:6px 12px;'>{instance_data.get('meta_task_name', '-')}</td></tr>",
        f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>执行用户</td><td style='padding:6px 12px;'>{instance_data.get('username', '-')}</td></tr>",
        f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>任务编号</td><td style='padding:6px 12px;'>{instance_data.get('instance_no', '-')}</td></tr>",
        f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>执行状态</td><td style='padding:6px 12px;'><strong style='color:{'#e74c3c' if is_failure else '#27ae67'};'>{status_text}</strong></td></tr>",
    ]

    if is_failure:
        rows.append(f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>失败原因</td><td style='padding:6px 12px;color:#e74c3c;'>{instance_data.get('error_message', '未知错误')}</td></tr>")
    else:
        rows.append(f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>检索总数</td><td style='padding:6px 12px;'>{stats.get('total', 0)} 条</td></tr>")
        rows.append(f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>有效数据</td><td style='padding:6px 12px;'>{stats.get('valid', 0)} 条（去重 {stats.get('duplicate', 0)} 条）</td></tr>")
        if detail:
            rows.append(f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>LLM分析</td><td style='padding:6px 12px;'>已完成 {detail.get('llm_completed', 0)}（通过 {detail.get('llm_passed', 0)} / 拒绝 {detail.get('llm_rejected', 0)}）失败 {detail.get('llm_failed', 0)}</td></tr>")
            rows.append(f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>人工审核</td><td style='padding:6px 12px;'>通过 {detail.get('manual_passed', 0)} / 拒绝 {detail.get('manual_rejected', 0)}</td></tr>")
            rows.append(f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>下载</td><td style='padding:6px 12px;'>成功 {detail.get('download_success', 0)} / 失败 {detail.get('download_failed', 0)}</td></tr>")
        else:
            rows.append(f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>分析完成</td><td style='padding:6px 12px;'>{stats.get('analyzed', 0)} 条</td></tr>")
            rows.append(f"<tr><td style='padding:6px 12px;font-weight:600;white-space:nowrap;color:#555;'>下载成功</td><td style='padding:6px 12px;'>{stats.get('downloaded', 0)} 条</td></tr>")

    font_family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:{font_family};">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.1);">
<tr><td style="padding:20px 24px;background:{'#e74c3c' if is_failure else '#27ae67'};color:#fff;font-size:18px;font-weight:600;">
{'❌' if is_failure else '✅'} {stage}{status_text}通知
</td></tr>
<tr><td style="padding:16px 24px;font-size:14px;line-height:1.6;color:#333;">
<p style="margin:0 0 12px 0;">您好，以下是任务执行结果：</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">{"".join(rows)}</table>
<p style="margin:16px 0 0 0;font-size:12px;color:#999;">本邮件由系统自动发送，请勿回复。</p>
</td></tr>
</table>
</td></tr></table>
</body>
</html>"""


async def send_email_notification(
    db: AsyncSession,
    config: UserNotificationConfig,
    instance_data: dict,
) -> None:
    try:
        api_url = await _load_system_config(db, "email_api_url")
        api_key = await _load_system_config(db, "email_api_key")
        if not api_url or not api_key:
            logger.info("邮件服务未配置（email_api_url 或 email_api_key 为空），跳过邮件通知")
            return

        user_id = instance_data.get("user_id")
        if not user_id:
            logger.info("未指定用户，跳过邮件通知")
            return

        recipient = await _load_email_recipient(db, config, user_id)
        if not recipient:
            logger.info(f"用户 {user_id} 未配置邮箱，跳过邮件通知")
            return

        stage = instance_data.get("stage", "任务执行")
        status = instance_data.get("status", "")
        is_failure = status == "failed"
        status_text = "失败" if is_failure else "完成"
        subject = f"{'❌' if is_failure else '✅'} {stage}{status_text} - {instance_data.get('meta_task_name', '')}"

        instance_id = instance_data.get("instance_id")
        if instance_id:
            from app.services.wecom_notifier import _compute_detailed_stats
            instance_data["detail_stats"] = await _compute_detailed_stats(db, instance_id)

        html_content = _build_html(instance_data)
        payload = {
            "to": recipient,
            "subject": subject,
            "content": html_content,
            "content_type": "html",
        }

        base_url = api_url.rstrip("/")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{base_url}/api/v1/mail/send",
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": api_key,
                },
                json=payload,
            )
            if resp.status_code != 200:
                logger.error(f"邮件发送失败: HTTP {resp.status_code} {resp.text}")
            else:
                body = resp.json()
                if body.get("code") == 0:
                    logger.info(f"邮件通知提交成功 -> {recipient}")
                else:
                    logger.error(f"邮件通知提交失败: {body.get('message', '')}")
    except Exception as e:
        logger.error(f"邮件通知异常（已忽略）: {e}")


async def send_test_email(db: AsyncSession, email_to: str) -> None:
    api_url = await _load_system_config(db, "email_api_url")
    api_key = await _load_system_config(db, "email_api_key")
    if not api_url or not api_key:
        raise RuntimeError("邮件服务未配置，请联系管理员设置 email_api_url 和 email_api_key")

    payload = {
        "to": email_to,
        "subject": "测试邮件",
        "content": "<h2>测试消息</h2><p>这是一条来自 SDI-CNKI 系统的测试邮件。</p><p>如果您收到此邮件，说明邮件通知配置正确。</p>",
        "content_type": "html",
    }

    base_url = api_url.rstrip("/")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{base_url}/api/v1/mail/send",
            headers={
                "Content-Type": "application/json",
                "X-API-Key": api_key,
            },
            json=payload,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"发送失败: HTTP {resp.status_code}")
        body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(body.get("message", "发送失败"))