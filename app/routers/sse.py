"""SSE (Server-Sent Events) endpoint with in-memory event broadcasting."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.task_instance import TaskInstance
from app.routers import get_current_user_from_header
from app.utils.exceptions import NotFoundError
from app.utils.logging import get_logger

logger = get_logger("sse")

router = APIRouter()

# In-memory event store: {instance_id: [event_dict, ...]}
_event_store: dict[int, list[dict[str, Any]]] = {}
_event_conditions: dict[int, asyncio.Condition] = {}


async def broadcast_event(instance_id: int, event_type: str, data: dict) -> None:
    """Push event to store and notify SSE listeners."""
    event = {"event": event_type, "data": json.dumps(data, ensure_ascii=False)}
    if instance_id not in _event_store:
        _event_store[instance_id] = []
    _event_store[instance_id].append(event)
    if instance_id in _event_conditions:
        async with _event_conditions[instance_id]:
            _event_conditions[instance_id].notify_all()


async def _get_instance_status(db: AsyncSession, instance_id: int) -> dict | None:
    stmt = select(TaskInstance).where(TaskInstance.id == instance_id)
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()
    if not inst:
        return None
    return {
        "status": inst.status,
        "search_result_count": inst.search_result_count,
        "valid_data_count": inst.valid_data_count,
        "duplicate_count": inst.duplicate_count,
        "error_message": inst.error_message,
        "started_at": inst.started_at.isoformat() if inst.started_at else None,
        "search_completed_at": inst.search_completed_at.isoformat() if inst.search_completed_at else None,
        "analysis_completed_at": inst.analysis_completed_at.isoformat() if inst.analysis_completed_at else None,
        "completed_at": inst.completed_at.isoformat() if inst.completed_at else None,
    }


@router.get("/{instance_id}/events")
async def sse_events(
    instance_id: int,
    request: Request,
    current_user=Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TaskInstance).where(TaskInstance.id == instance_id))
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and instance.creator_id != current_user.id:
        from app.utils.exceptions import PermissionDeniedError
        raise PermissionDeniedError()

    if instance_id not in _event_store:
        _event_store[instance_id] = []
    if instance_id not in _event_conditions:
        _event_conditions[instance_id] = asyncio.Condition()

    async def event_generator():
        last_index = len(_event_store[instance_id])
        terminal_events = {"task.completed", "task.failed", "task.cancelled"}

        initial = await _get_instance_status(db, instance_id)
        if initial:
            yield f"event: task.progress\ndata: {json.dumps({'status': initial['status'], **initial}, ensure_ascii=False)}\n\n"

        send_heartbeat = False
        try:
            while True:
                if await request.is_disconnected():
                    break

                if send_heartbeat:
                    yield "event: ping\ndata: {}\n\n"
                    send_heartbeat = False

                async with _event_conditions[instance_id]:
                    try:
                        await asyncio.wait_for(
                            _event_conditions[instance_id].wait(),
                            timeout=15,
                        )
                    except asyncio.TimeoutError:
                        send_heartbeat = True
                        continue

                while last_index < len(_event_store[instance_id]):
                    event = _event_store[instance_id][last_index]
                    yield f"event: {event['event']}\ndata: {event['data']}\n\n"
                    last_index += 1

                    if event["event"] in terminal_events:
                        async with _event_conditions.get(instance_id, asyncio.Condition()):
                            _event_store.pop(instance_id, None)
                            _event_conditions.pop(instance_id, None)
                        return

                sync_status = await _get_instance_status(db, instance_id)
                if sync_status and sync_status["status"] in ("completed", "failed", "cancelled"):
                    yield f"event: task.{sync_status['status']}\ndata: {json.dumps({'status': sync_status['status'], 'completed_at': datetime.now(timezone.utc).isoformat()}, ensure_ascii=False)}\n\n"
                    async with _event_conditions.get(instance_id, asyncio.Condition()):
                        _event_store.pop(instance_id, None)
                        _event_conditions.pop(instance_id, None)
                    return
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
