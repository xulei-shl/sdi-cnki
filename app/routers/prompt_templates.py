from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.prompt_template import PromptTemplate
from app.utils.exceptions import NotFoundError
from app.routers import get_current_user_from_header, require_admin_user

router = APIRouter()


class TemplateCreate(BaseModel):
    name: str
    content: str
    version: str = "1.0"
    tags: Optional[str] = None
    is_active: bool = True


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    version: Optional[str] = None
    tags: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
async def list_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(PromptTemplate)
        .order_by(PromptTemplate.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    templates = result.scalars().all()
    total = (await db.execute(select(func.count(PromptTemplate.id)))).scalar()
    return {
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "content": t.content,
                "version": t.version,
                "tags": t.tags,
                "is_active": t.is_active,
                "updated_at": t.updated_at.isoformat() if t.updated_at else "",
            }
            for t in templates
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("")
async def create_template(
    data: TemplateCreate,
    admin=Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    template = PromptTemplate(
        name=data.name,
        content=data.content,
        version=data.version,
        tags=data.tags,
        is_active=data.is_active,
        created_by=admin.id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return {"id": template.id, "name": template.name, "version": template.version}


@router.get("/{template_id}")
async def get_template(
    template_id: int,
    current_user=Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PromptTemplate).where(PromptTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundError("PromptTemplate", template_id)
    return {
        "id": template.id,
        "name": template.name,
        "content": template.content,
        "version": template.version,
        "tags": template.tags,
        "is_active": template.is_active,
    }


@router.put("/{template_id}")
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    admin=Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PromptTemplate).where(PromptTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundError("PromptTemplate", template_id)
    if data.name is not None:
        template.name = data.name
    if data.content is not None:
        template.content = data.content
    if data.version is not None:
        template.version = data.version
    if data.tags is not None:
        template.tags = data.tags
    if data.is_active is not None:
        template.is_active = data.is_active
    template.updated_at = datetime.utcnow()
    await db.commit()
    return {"id": template.id, "name": template.name}


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    admin=Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PromptTemplate).where(PromptTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundError("PromptTemplate", template_id)
    await db.delete(template)
    await db.commit()
    return {"message": "Prompt template deleted"}
