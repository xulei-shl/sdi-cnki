from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.llm_config import LlmConfig
from app.utils.exceptions import NotFoundError, ValidationError
from app.utils.crypto import encrypt_api_key, decrypt_api_key, mask_api_key
from app.config import get_settings
from app.routers import get_current_user_from_header, require_admin_user
from app.services.llm_provider import call_llm_once

router = APIRouter()
settings = get_settings()


class LlmConfigCreate(BaseModel):
    name: str
    model_name: str
    api_key: str
    api_endpoint: str
    is_active: bool = True


class LlmConfigUpdate(BaseModel):
    name: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    api_endpoint: Optional[str] = None
    is_active: Optional[bool] = None


class LlmConfigTest(BaseModel):
    model_name: str
    api_endpoint: str
    api_key: str


@router.get("")
async def list_llm_configs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    where = [LlmConfig.is_active == True] if current_user.role != "admin" else []
    stmt = select(LlmConfig).where(*where).order_by(LlmConfig.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    configs = result.scalars().all()
    count_stmt = select(func.count(LlmConfig.id)).where(*where)
    total = (await db.execute(count_stmt)).scalar()
    items = []
    for c in configs:
        items.append({
            "id": c.id,
            "name": c.name,
            "model_name": c.model_name,
            "api_key_masked": mask_api_key(c.api_key_encrypted, settings.aes_encryption_key),
            "api_endpoint": c.api_endpoint,
            "is_active": c.is_active,
            "created_by": c.created_by,
            "created_at": c.created_at.isoformat() if c.created_at else "",
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("")
async def create_llm_config(
    data: LlmConfigCreate,
    admin = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    encrypted = encrypt_api_key(data.api_key, settings.aes_encryption_key)
    config = LlmConfig(
        name=data.name,
        model_name=data.model_name,
        api_key_encrypted=encrypted,
        api_endpoint=data.api_endpoint,
        is_active=data.is_active,
        created_by=admin.id,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return {"id": config.id, "name": config.name, "model_name": config.model_name}


@router.put("/{config_id}")
async def update_llm_config(
    config_id: int,
    data: LlmConfigUpdate,
    admin = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LlmConfig).where(LlmConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise NotFoundError("LLM Config", config_id)
    if data.name is not None:
        config.name = data.name
    if data.model_name is not None:
        config.model_name = data.model_name
    if data.api_key:
        config.api_key_encrypted = encrypt_api_key(data.api_key, settings.aes_encryption_key)
    if data.api_endpoint is not None:
        config.api_endpoint = data.api_endpoint
    if data.is_active is not None:
        config.is_active = data.is_active
    await db.commit()
    return {"id": config.id, "name": config.name}


@router.delete("/{config_id}")
async def delete_llm_config(
    config_id: int,
    admin = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LlmConfig).where(LlmConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise NotFoundError("LLM Config", config_id)
    from sqlalchemy import select as sel
    from app.models.meta_task_llm_config import MetaTaskLlmConfig
    ref = await db.execute(sel(MetaTaskLlmConfig).where(MetaTaskLlmConfig.llm_config_id == config_id))
    if ref.scalar_one_or_none():
        raise ValidationError("LLM config is referenced by task templates and cannot be deleted")
    await db.delete(config)
    await db.commit()
    return {"message": "LLM config deleted"}


@router.post("/test")
async def test_llm_config(
    data: LlmConfigTest,
    admin = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        content = await call_llm_once(
            api_key=data.api_key,
            api_endpoint=data.api_endpoint,
            model_name=data.model_name,
            messages=[{"role": "user", "content": "Say 'Hello' in one word."}],
            timeout=30,
        )
        return {"message": "连接成功", "response": content[:200]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连接失败: {str(e)[:200]}")


@router.post("/{config_id}/test")
async def test_llm_config_by_id(
    config_id: int,
    admin = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LlmConfig).where(LlmConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise NotFoundError("LLM Config", config_id)
    api_key = decrypt_api_key(config.api_key_encrypted, settings.aes_encryption_key)
    try:
        content = await call_llm_once(
            api_key=api_key,
            api_endpoint=config.api_endpoint,
            model_name=config.model_name,
            messages=[{"role": "user", "content": "Say 'Hello' in one word."}],
            timeout=30,
        )
        return {"message": "连接成功", "response": content[:200]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连接失败: {str(e)[:200]}")
