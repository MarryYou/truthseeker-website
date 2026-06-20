from __future__ import annotations
import json
import uuid as uuid_mod
from typing import Any, cast
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.engine import get_db
from backend.db import crud
from backend.api.auth import get_current_user
from backend.core.logging import logger
from backend.utils.redis import get_redis
from pydantic import BaseModel, ConfigDict
from datetime import datetime

router = APIRouter(prefix="/api/v1/researches", tags=["research"])

# ── Pydantic 响应模型 ────────────────────────────────────────────────
class TaskItemResponse(BaseModel):
    id: str
    ordinal: int
    query: str
    status: str
    pending_approval: bool = False
    breakpoint_type: str | None = None
    summary: str | None = None
    research_conclusion: str | None = None
    dimensions: list[Any] | None = None
    sources: list[dict] | None = None
    claims: list[dict] | None = None
    thought_steps: list[dict] | None = None
    run_config_snapshot: dict | None = None
    duration_seconds: int | None = None
    overall_confidence: float | None = None
    created_at: datetime
    completed_at: datetime | None = None
    
    model_config = ConfigDict(from_attributes=True)

class SessionItemResponse(BaseModel):
    id: str
    title: str | None
    status: str
    total_duration_seconds: int = 0
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class SessionListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[SessionItemResponse]

class SessionDetailResponse(BaseModel):
    id: str
    title: str | None
    status: str
    preset_id: str | None
    created_at: datetime
    updated_at: datetime
    tasks: list[TaskItemResponse]
    
    model_config = ConfigDict(from_attributes=True)


# ── 查询列表 (GET /api/researches) ───────────────────────────────────
@router.get("", response_model=SessionListResponse)
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, str] = Depends(get_current_user),
):
    """分页获取会话列表记录。"""
    user_id = current_user["user_id"]
    
    total, items = await crud.list_research_sessions(
        db=db,
        user_id=user_id,
        page=page,
        page_size=page_size,
        keyword=keyword
    )
    
    return SessionListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=cast(Any, items)
    )


# ── 获取详情 (GET /api/researches/{id}) ───────────────────────────────
@router.get("/{research_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    research_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, str] = Depends(get_current_user),
):
    """获取会话详情，包含该会话下的所有交互任务任务。"""
    user_id = current_user["user_id"]
    tenant_id = current_user["tenant_id"]
    
    session = await crud.get_research_session(
        db=db,
        session_id=research_id,
        tenant_id=tenant_id,
        user_id=user_id
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在，或您无权访问"
        )
        
    return session


# ── 删除任务 (DELETE /api/researches/{id}) ────────────────────────────
@router.delete("/{research_id}")
async def delete_session(
    research_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, str] = Depends(get_current_user),
):
    """删除会话及其下属所有任务。"""
    user_id = current_user["user_id"]
    
    success = await crud.delete_research_session(
        db=db,
        session_id=research_id,
        user_id=user_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在，删除失败"
        )
        
    await db.commit()

    # 通过 Redis PubSub 广播取消信号通知所有 Worker
    try:
        redis = await get_redis()
        cancel_payload = json.dumps({"research_id": research_id, "exclude_run_uuid": str(uuid_mod.uuid4())})
        await redis.publish("truthseeker:cancellations", cancel_payload)
        logger.info("已广播取消信号 | research_id={}", research_id)
    except Exception as e:
        logger.warning("广播取消信号失败 | research_id={} error={}", research_id, e)

    return {"message": "删除成功"}
