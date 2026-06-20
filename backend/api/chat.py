"""API Router for chat and research session management.

修改为 Worker 架构：
  - POST /api/v1/chat  → 校验入参、入队到 Worker、返回 SSE 流
  - POST /{research_id}/resume → 更新 DB、入队恢复任务、返回 SSE 流
  - SSE 事件由 Redis PubSub + Stream 消费者产生（sse_from_redis）
"""
from __future__ import annotations
import uuid
import time
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.engine import get_db
from backend.db import crud
from backend.api.auth import get_current_user
from backend.api.deps import get_config_validator, ResearchConfigValidator
from backend.services.sse import safe_json_dumps, sse_from_redis
from backend.core.logging import logger, trace_id_var, task_id_var
from backend.db.models import ResearchTask
from backend.services.chat_service import handle_existing_session_logic, handle_new_research_logic
from backend.services.research_lifecycle import map_claims_to_frontend
from backend.worker import enqueue_research, enqueue_resume_research

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class BusinessControl(BaseModel):
    """业务控制层 - 对应决策模式与速度"""
    execution_mode: Literal["auto", "preset"] = "auto"
    speed: Literal["auto", "fast_react", "expert_search", "research_pipeline"] = "research_pipeline"
    enable_hitl: bool = False

class ChatRequest(BaseModel):
    """Input schema for starting or continuing a chat research session."""
    message: str
    research_id: str | None = None
    preset_name: str | None = None

    control: BusinessControl = Field(default_factory=BusinessControl)


class ResumeRequest(BaseModel):
    """Input schema for resuming a suspended research session (HITL)."""
    approved_dimensions: list[str] | None = None
    approved_sources: list[str] | None = None


@router.post("")
async def chat(
    request: Request,
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, str] = Depends(get_current_user),
    validator: ResearchConfigValidator = Depends(get_config_validator),
):
    """
    Main entry point for research sessions.
    Validates input, enqueues to Worker, and returns SSE stream.
    """
    user_id = current_user["user_id"]
    tenant_id = current_user["tenant_id"]
    start_time = time.time()

    # 1. Determine session context (Reconnect, Follow-up, or New)
    research_id = data.research_id
    existing_session = None
    if research_id:
        existing_session = await crud.get_research_session(db, research_id, tenant_id, user_id)
    if existing_session:
        logger.info("会话类型=追问 | research_id={} message='{}'", research_id, data.message[:50])
    else:
        logger.info("会话类型=新研究 | research_id={} message='{}'", research_id or "auto", data.message[:50])

    # 2. Logic Branching
    task_id = str(uuid.uuid4())

    trace_id_var.set(research_id or "new-session")
    task_id_var.set(task_id)

    if existing_session:
        if research_id is None:
            raise ValueError("research_id must not be None for existing session")
        initial_input, research_id, preset_id, task_id = await _handle_existing_session(
            db=db, message=data.message, research_id=research_id,
            preset_name=data.preset_name, control=data.control,
            existing_session=existing_session, tenant_id=tenant_id,
            user_id=user_id, task_id=task_id,
        )
    else:
        initial_input, research_id, preset_id = await _handle_new_research(
            db=db, message=data.message, research_id=research_id,
            preset_name=data.preset_name, control=data.control,
            tenant_id=tenant_id, user_id=user_id, task_id=task_id,
            validator=validator,
        )

    # 3. Dispatch to Worker or sync-only
    if initial_input is None:
        # 无 message 的断线重连：如果最后一个任务还在 running，订阅实时流
        last_task = (await db.execute(
            select(ResearchTask).where(ResearchTask.session_id == research_id)
            .order_by(ResearchTask.ordinal.desc()).limit(1)
        )).scalar_one_or_none()

        if last_task and last_task.status == "running":
            # 任务还在跑 → 订阅 Redis SSE 实时流接收 Worker 事件
            return StreamingResponse(
                sse_from_redis(task_id=last_task.id, research_id=research_id),
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        # 任务已完成 → 从 DB 同步最终状态
        return StreamingResponse(
            _sync_session_state(db, research_id, task_id, start_time),
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 入队到 Worker
    speed = data.control.speed or "research_pipeline"
    await enqueue_research({
        "research_id": research_id,
        "task_id": task_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "preset_id": preset_id,
        "initial_state": initial_input,
        "enable_hitl": data.control.enable_hitl,
        "start_time": start_time,
    }, speed=speed)

    # 返回 SSE 流（从 Redis 消费）
    return StreamingResponse(
        sse_from_redis(task_id=task_id, research_id=research_id),
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{research_id}/resume")
async def resume_research(
    research_id: str,
    data: ResumeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, str] = Depends(get_current_user),
):
    """
    Resume a suspended research task (v3.0 HITL).
    Updates DB approval state, enqueues to Worker, returns SSE stream.
    """
    user_id = current_user["user_id"]
    tenant_id = current_user["tenant_id"]

    # 1. 查询挂起的任务
    stmt = (
        select(ResearchTask)
        .options(selectinload(ResearchTask.session))
        .where(
            ResearchTask.session_id == research_id,
            ResearchTask.status == "suspended",
            ResearchTask.pending_approval,
        )
        .order_by(ResearchTask.ordinal.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="No pending research task found to resume.")

    task_id = task.id
    preset_id = task.session.preset_id if task.session else None
    start_time = time.time()

    # 2. 清除 DB 审批标记
    task.pending_approval = False
    await db.commit()

    # 3. 入队恢复任务到 Worker
    await enqueue_resume_research({
        "research_id": research_id,
        "task_id": task_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "preset_id": preset_id,
        "enable_hitl": True,
        "start_time": start_time,
        "existing_steps": task.thought_steps,
        "resume_metadata": {
            "approved_dimensions": data.approved_dimensions,
            "approved_sources": data.approved_sources,
        },
    })

    # 4. 返回 SSE 流
    return StreamingResponse(
        sse_from_redis(task_id=task_id, research_id=research_id),
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════════
#  内部辅助函数（原有 chat_service.py 逻辑内联）
# ═══════════════════════════════════════════════════════════════

async def _handle_existing_session(
    db: AsyncSession,
    message: str,
    research_id: str,
    preset_name: str | None,
    control: Any,
    existing_session: Any,
    tenant_id: str,
    user_id: str,
    task_id: str,
):
    """处理已存在会话的重连或追问。"""
    return await handle_existing_session_logic(
        db=db, message=message, research_id=research_id,
        preset_name=preset_name, control=control,
        existing_session=existing_session, tenant_id=tenant_id,
        user_id=user_id, task_id=task_id,
    )


async def _handle_new_research(
    db: AsyncSession,
    message: str,
    research_id: str | None,
    preset_name: str | None,
    control: Any,
    tenant_id: str,
    user_id: str,
    task_id: str,
    validator: Any,
):
    """处理新研究会话的创建。"""
    return await handle_new_research_logic(
        db=db, message=message, research_id=research_id,
        preset_name=preset_name, control=control,
        tenant_id=tenant_id, user_id=user_id, task_id=task_id,
        validator=validator,
    )


async def _sync_session_state(
    db: AsyncSession,
    research_id: str,
    task_id: str,
    start_time: float,
):
    """无 message 的断线重连：只同步状态，不启动图执行。"""
    yield ": connected\n\n"

    # 从 DB 读取任务状态
    try:
        refreshed = await db.get(ResearchTask, task_id)
    except Exception:
        refreshed = None

    if refreshed:
        thought_steps = refreshed.thought_steps or []
        is_breakpoint = refreshed.pending_approval or False
        bp_type = refreshed.breakpoint_type
        task_status = refreshed.status or "running"

        if task_status == "suspended" or is_breakpoint:
            bp_data = {
                "type": bp_type or "dimensions",
                "payload": [],
                "research_id": research_id,
                "task_id": task_id,
            }
            yield f"event: breakpoint\ndata: {safe_json_dumps(bp_data)}\n\n"
        elif task_status == "completed":
            final_mapped_claims = []
            if refreshed.claims:
                final_mapped_claims = map_claims_to_frontend(refreshed.claims)

            complete_data = {
                "research_id": research_id,
                "task_id": task_id,
                "claims": final_mapped_claims,
                "warnings": refreshed.warnings or [],
                "error_log": refreshed.error_log or [],
                "confidence": refreshed.overall_confidence or 0.0,
                "conflict_dimensions": [],
                "duration_seconds": refreshed.duration_seconds or 0,
                "report": refreshed.summary or "",
                "research_conclusion": refreshed.research_conclusion or "",
                "message": "Research synchronized.",
            }
            yield f"event: complete\ndata: {safe_json_dumps(complete_data)}\n\n"
        else:
            yield f"event: sync\ndata: {safe_json_dumps({'thought_steps': thought_steps, 'task_id': task_id})}\n\n"
    else:
        yield f"event: sync\ndata: {safe_json_dumps({'thought_steps': [], 'task_id': task_id})}\n\n"
