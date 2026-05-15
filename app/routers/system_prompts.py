from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
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
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SystemPrompt).order_by(SystemPrompt.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    prompts = result.scalars().all()
    total = (await db.execute(select(func.count(SystemPrompt.id)))).scalar()
    return {
        "items": [
            {
                "id": p.id, "name": p.name, "content": p.content, "version": p.version, "tags": p.tags,
                "is_active": p.is_active,
                "updated_at": p.updated_at.isoformat() if p.updated_at else "",
            }
            for p in prompts
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("")
async def create_prompt(
    data: PromptCreate,
    admin = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    prompt = SystemPrompt(name=data.name, content=data.content, version=data.version, tags=data.tags, is_active=data.is_active)
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return {"id": prompt.id, "name": prompt.name, "version": prompt.version}


@router.get("/{prompt_id}")
async def get_prompt(
    prompt_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise NotFoundError("Prompt", prompt_id)
    return {"id": prompt.id, "name": prompt.name, "content": prompt.content, "version": prompt.version, "tags": prompt.tags, "is_active": prompt.is_active}


@router.put("/{prompt_id}")
async def update_prompt(
    prompt_id: int,
    data: PromptUpdate,
    admin = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise NotFoundError("Prompt", prompt_id)
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
    admin = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise NotFoundError("Prompt", prompt_id)
    await db.delete(prompt)
    await db.commit()
    return {"message": "Prompt deleted"}
