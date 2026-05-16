from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.meta_task import MetaTask
from app.models.system_prompt import SystemPrompt
from app.utils.exceptions import NotFoundError
from app.routers import get_current_user_from_header, require_admin_user

router = APIRouter()


class PromptCreate(BaseModel):
    name: str
    content: str
    version: str = "1.0"
    tags: Optional[str] = None
    is_active: bool = True


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    version: Optional[str] = None
    tags: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
async def list_prompts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SystemPrompt).options(joinedload(SystemPrompt.creator))
    if current_user.role != "admin":
        stmt = stmt.where(SystemPrompt.creator_id == current_user.id)
    stmt = stmt.order_by(SystemPrompt.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    prompts = result.unique().scalars().all()

    count_stmt = select(func.count(SystemPrompt.id))
    if current_user.role != "admin":
        count_stmt = count_stmt.where(SystemPrompt.creator_id == current_user.id)
    total = (await db.execute(count_stmt)).scalar()

    prompt_ids = [p.id for p in prompts]
    ref_counts: dict[int, int] = {}
    if prompt_ids:
        rc_stmt = (
            select(MetaTask.prompt_template_id, func.count(MetaTask.id))
            .where(MetaTask.prompt_template_id.in_(prompt_ids))
            .group_by(MetaTask.prompt_template_id)
        )
        for row in (await db.execute(rc_stmt)).all():
            ref_counts[row[0]] = row[1]

    return {
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "content": p.content,
                "version": p.version,
                "tags": p.tags,
                "is_active": p.is_active,
                "creator_id": p.creator_id,
        "creator_name": p.creator.username if p.creator else str(p.creator_id),
                "ref_count": ref_counts.get(p.id, 0),
                "updated_at": p.updated_at.isoformat() if p.updated_at else "",
            }
            for p in prompts
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("")
async def create_prompt(
    data: PromptCreate,
    current_user=Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    prompt = SystemPrompt(
        name=data.name,
        content=data.content,
        version=data.version,
        tags=data.tags,
        is_active=data.is_active,
        creator_id=current_user.id,
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return {"id": prompt.id, "name": prompt.name, "version": prompt.version}


@router.get("/{prompt_id}")
async def get_prompt(
    prompt_id: int,
    current_user=Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SystemPrompt)
        .options(joinedload(SystemPrompt.creator))
        .where(SystemPrompt.id == prompt_id)
    )
    prompt = result.unique().scalar_one_or_none()
    if not prompt:
        raise NotFoundError("Prompt", prompt_id)
    ref_count = (
        await db.execute(
            select(func.count(MetaTask.id)).where(MetaTask.prompt_template_id == prompt_id)
        )
    ).scalar()
    return {
        "id": prompt.id,
        "name": prompt.name,
        "content": prompt.content,
        "version": prompt.version,
        "tags": prompt.tags,
        "is_active": prompt.is_active,
        "creator_id": prompt.creator_id,
        "creator_name": prompt.creator.username if prompt.creator else str(prompt.creator_id),
        "ref_count": ref_count or 0,
    }


@router.put("/{prompt_id}")
async def update_prompt(
    prompt_id: int,
    data: PromptUpdate,
    current_user=Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise NotFoundError("Prompt", prompt_id)
    if current_user.role != "admin" and prompt.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能编辑自己的提示词")
    if data.name is not None:
        prompt.name = data.name
    if data.content is not None:
        prompt.content = data.content
    if data.version is not None:
        prompt.version = data.version
    if data.tags is not None:
        prompt.tags = data.tags
    if data.is_active is not None:
        prompt.is_active = data.is_active
    await db.commit()
    return {"id": prompt.id, "name": prompt.name}


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: int,
    current_user=Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise NotFoundError("Prompt", prompt_id)
    if current_user.role != "admin" and prompt.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能删除自己的提示词")

    ref_count = (
        await db.execute(
            select(func.count(MetaTask.id)).where(MetaTask.prompt_template_id == prompt_id)
        )
    ).scalar()
    if ref_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该提示词正被 {ref_count} 个任务模板引用，无法删除",
        )

    await db.delete(prompt)
    await db.commit()
    return {"message": "Prompt deleted"}
