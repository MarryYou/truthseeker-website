"""Chat control and session state synchronization services."""
from __future__ import annotations

from backend.pipeline.types import ResearchState, merge_thought_steps
import uuid
import datetime
from typing import Any, cast, Literal, AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from backend.core.logging import logger, trace_id_var
from backend.services.research_engine import ResearchEngineService
from backend.services.selector import select_preset
from backend.services.context import resolve_context
from backend.services.sse import safe_json_dumps
from backend.db import crud
from backend.db.models import ResearchTask
from backend.db.store import ResearchStore
from backend.pipeline.state import create_initial_state
from backend.pipeline.constants import MAX_HISTORY_TURNS
from backend.services.research_lifecycle import map_claims_to_frontend, _extract_research_conclusion


def resolve_control_params(
    preset: Any, 
    control: Any | None
) -> tuple[Literal["auto", "preset"], Literal["fast_react", "expert_search", "research_pipeline"], bool]:
    """根据预设和前端控制参数解析执行模式、速度档位与 HITL 状态"""
    execution_mode: Literal["auto", "preset"] = "auto"
    speed: Literal["fast_react", "expert_search", "research_pipeline"] = "research_pipeline"
    enable_hitl = False

    if preset and preset.nodes_config:
        bus = preset.nodes_config.get("business", {})
        speed = bus.get("speed", "research_pipeline")
        if bus.get("allow_ai_override") is False:
            execution_mode = "preset"

    if control:
        if control.execution_mode:
            execution_mode = control.execution_mode
        if control.speed:
            speed = control.speed
        if control.enable_hitl is not None:
            enable_hitl = control.enable_hitl

    return execution_mode, speed, enable_hitl


async def _sync_session_state(
    db: AsyncSession,
    research_id: str,
    task_id: str,
    engine: ResearchEngineService,
    start_time: float,
) -> AsyncIterator[str]:
    """无 message 的断线重连：只同步状态，不启动图执行，避免空输入导致 LangGraph 异常。"""
    yield ": connected\n\n"
    
    # 1. 获取本地 DB 任务记录，加载已保存的步骤
    refreshed_steps = None
    task_status = "running"
    is_breakpoint = False
    bp_type = None
    final_report = ""
    overall_confidence = 0.0
    warnings = []
    error_log = []
    
    try:
        refreshed = await db.get(ResearchTask, task_id)
        if refreshed:
            refreshed_steps = refreshed.thought_steps or []
            task_status = refreshed.status or "running"
            is_breakpoint = refreshed.pending_approval or False
            bp_type = refreshed.breakpoint_type
            final_report = refreshed.summary or ""
            overall_confidence = refreshed.overall_confidence or 0.0
            warnings = refreshed.warnings or []
            error_log = refreshed.error_log or []
    except Exception as e:
        logger.warning("Failed to load task from db in _sync_session_state | error={}", e)

    thought_steps = list(refreshed_steps or [])
    
    # 2. 同步 LangGraph 状态
    active_graph = engine.get_graph()
    run_config = engine.get_run_config(research_id, "default", "default", None, task_id=task_id)
    
    snapshot = None
    try:
        snapshot = await active_graph.aget_state(run_config)
        if snapshot and snapshot.values:
            if "thought_steps" in snapshot.values:
                thought_steps = merge_thought_steps(thought_steps, snapshot.values["thought_steps"])
            
            # 同步最新步骤给前端
            yield f"event: sync\ndata: {safe_json_dumps({'thought_steps': thought_steps, 'task_id': task_id})}\n\n"
            
            # 如果内存中有最新的状态，以内存状态为准
            interrupt_nodes = snapshot.next or []
            if any(n in interrupt_nodes for n in ["agent_node", "search_react"]):
                is_breakpoint = True
                task_status = "suspended"
                bp_type = "dimensions"
            elif not snapshot.next:
                task_status = "completed"
    except Exception as e:
        logger.warning("Failed to get state in _sync_session_state | error={}", e)

    # 3. 根据最终状态同步信号，防止前端无限等待
    if task_status == "suspended" or is_breakpoint:
        bp_payload = []
        if snapshot and snapshot.values:
            bp_payload = snapshot.values.get("dimensions", [])
        
        bp_data = {
            "type": bp_type or "dimensions",
            "payload": bp_payload,
            "research_id": research_id,
            "task_id": task_id
        }
        yield f"event: breakpoint\ndata: {safe_json_dumps(bp_data)}\n\n"
        
    elif task_status == "completed":
        final_mapped_claims = []
        raw_claims = []
        try:
            rs = ResearchStore(cast(BaseStore, engine.store), tenant_id="default", research_id=research_id, task_id=task_id)
            raw_claims = await rs.load_claims("final")
            if raw_claims:
                final_mapped_claims = map_claims_to_frontend(raw_claims)
        except Exception as e:
            logger.warning("Load claims failed in _sync_session_state | error={}", e)
            
        research_conclusion = None
        if final_report and snapshot and snapshot.values:
            try:
                research_conclusion = _extract_research_conclusion(
                    report=final_report,
                    dimensions=snapshot.values.get("dimensions", []),
                    claims=raw_claims or [],
                    overall_confidence=overall_confidence,
                    history_summary=snapshot.values.get("history_summary"),
                )
            except Exception:
                pass
                
        complete_data = {
            "research_id": research_id,
            "task_id": task_id,
            "claims": final_mapped_claims,
            "warnings": warnings,
            "error_log": error_log,
            "confidence": overall_confidence,
            "conflict_dimensions": [],
            "duration_seconds": 0,
            "report": final_report,
            "research_conclusion": research_conclusion,
            "message": "Research synchronized."
        }
        yield f"event: complete\ndata: {safe_json_dumps(complete_data)}\n\n"
    else:
        # 如果仍然是 running，发送一个普通的 sync 信号给前端
        yield f"event: sync\ndata: {safe_json_dumps({'thought_steps': thought_steps, 'task_id': task_id})}\n\n"


async def _cleanup_stale_tasks(db: AsyncSession, research_id: str):
    """清理僵尸任务：标记超时未更新的 running 任务为 failed。"""
    stale_stmt = select(ResearchTask).where(
        ResearchTask.session_id == research_id,
        ResearchTask.status == "running",
    ).order_by(ResearchTask.ordinal.desc()).limit(1)
    stale_task = (await db.execute(stale_stmt)).scalar_one_or_none()
    
    if stale_task:
        stale_threshold_sec = 600
        now = datetime.datetime.now(datetime.timezone.utc)
        last_updated = stale_task.updated_at.replace(tzinfo=datetime.timezone.utc) if stale_task.updated_at.tzinfo is None else stale_task.updated_at

        if (now - last_updated).total_seconds() > stale_threshold_sec or (stale_task.duration_seconds == 0 and stale_task.ordinal > 0):
            logger.warning("发现僵尸/未启动任务 | task_id={} 超时或状态异常，标记为 failed", stale_task.id)
            await crud.update_research_task(db, stale_task.id, status="failed", error_log=[{"message": "Task marked as failed during cleanup."}])
            await crud.update_research_status(db, research_id, "failed")
            await db.commit()


async def handle_existing_session_logic(
    db: AsyncSession,
    message: str,
    research_id: str,
    preset_name: str | None,
    control: Any,
    existing_session: Any,
    tenant_id: str,
    user_id: str,
    task_id: str,
) -> tuple[ResearchState | None, str, str, str]:
    """处理已存在会话的重连或追问逻辑"""
    preset_id = cast(str, existing_session.preset_id)
    initial_input = None

    # ── 1. 重连逻辑与超时保护 ──────────────────────────────────────────
    # 只有当没有消息 (message 为空) 时，才执行重连逻辑
    if not message:
        await _cleanup_stale_tasks(db, research_id)
        
        if existing_session.status != "running":
            raise HTTPException(
                status_code=400,
                detail="未提供查询内容 (message)，且该会话没有正在运行的任务可重连。请提供 message 发起追问。"
            )

        stmt = select(ResearchTask).where(ResearchTask.session_id == research_id).order_by(ResearchTask.ordinal.desc()).limit(1)
        res = await db.execute(stmt)
        last_task = res.scalar_one_or_none()

        if last_task and last_task.status == "running":
            logger.info("Reconnecting to active research session | id={}", research_id)
            task_id = last_task.id
    else:
        # 如果有消息，且当前会话显示正在运行，我们依然发起新任务，由下游分布式锁处理冲突
        if existing_session.status == "running":
            logger.info("Session shows running but new message received, starting new task | research_id={}", research_id)

    # ── 2. 正常的追问逻辑 ──────────────────────────────────────────────
    if message:
        logger.info("Follow-up question for session | id={}", research_id)
        context = await resolve_context(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            research_id=research_id,
            query=message,
        )
        original_query = context.get("original_query", message)
        
        await crud.create_research_task(
            db=db,
            session_id=research_id,
            query=message,
            intent_type="follow_up",
            task_id=task_id,
        )
        await db.commit()

        followup_preset_name = preset_name or control.speed or existing_session.preset_id
        fu_preset = await select_preset(db, message, followup_preset_name, user_id, tenant_id)
        preset_id = cast(str, fu_preset.id)
        fu_mode, fu_speed, fu_enable_hitl = resolve_control_params(fu_preset, control)

        messages = []
        follow_up_history = context.get("follow_up_history", [])
        truncated_history = follow_up_history[-MAX_HISTORY_TURNS:]
        for turn in truncated_history:
            if turn.get("query"):
                messages.append(HumanMessage(content=turn["query"]))
            if turn.get("core_answer"):
                messages.append(AIMessage(content=turn["core_answer"]))
        
        messages.append(HumanMessage(content=message))

        initial_input = create_initial_state(
            query=message,
            original_query=original_query,
            research_id=research_id,
            tenant_id=tenant_id,
            user_id=user_id,
            task_id=task_id,
            preset_id=preset_id,
            context_mode="follow_up",
            speed=fu_speed,
            last_research_summary=context.get("last_research_summary", ""),
            last_research_dimensions=context.get("last_research_dimensions", []),
            last_unresolved=context.get("last_unresolved", []),
            follow_up_history=context.get("follow_up_history", []),
            history_summary=context.get("history_summary", ""),
            execution_mode=fu_mode,
            enable_hitl=fu_enable_hitl,
            messages=messages,
            proven_facts=context.get("proven_facts", []),
        )

    return initial_input, research_id, preset_id, task_id


async def handle_new_research_logic(
    db: AsyncSession,
    message: str,
    research_id: str | None,
    preset_name: str | None,
    control: Any,
    tenant_id: str,
    user_id: str,
    task_id: str,
    validator: Any,
) -> tuple[ResearchState, str, str]:
    """处理新研究会话的创建逻辑"""
    resolved_id = research_id or str(uuid.uuid4())
    resolved_preset_name = preset_name or control.speed or None
    preset = await select_preset(db, message, resolved_preset_name, user_id, tenant_id)
    
    await validator.validate(preset)
    preset_id = cast(str, preset.id)

    _, resolved_speed_for_intent, _ = resolve_control_params(preset, control)

    await crud.create_research_session(
        db=db,
        session_id=resolved_id,
        user_id=user_id,
        tenant_id=tenant_id,
        preset_id=preset_id,
        title=message[:100]
    )
    await crud.create_research_task(
        db=db,
        session_id=resolved_id,
        query=message,
        intent_type=resolved_speed_for_intent,
        task_id=task_id,
    )
    await db.commit()
    
    preset_mode, preset_speed, preset_enable_hitl = resolve_control_params(preset, control)

    if control.enable_hitl:
        logger.info("UI 启用人工审批断点 (HITL) | enable_hitl=True")

    initial_input = create_initial_state(
        query=message,
        research_id=resolved_id,
        task_id=task_id,
        tenant_id=tenant_id,
        user_id=user_id,
        preset_id=preset_id,
        speed=preset_speed,
        execution_mode=preset_mode,
        enable_hitl=preset_enable_hitl,
        messages=[HumanMessage(content=message)],
    )
    return initial_input, resolved_id, preset_id


async def resume_research_logic(
    db: AsyncSession,
    research_id: str,
    approved_dimensions: list[str] | None,
    approved_sources: list[str] | None,
    tenant_id: str,
    user_id: str,
    engine: ResearchEngineService
) -> tuple[Any, Any, str, str | None, list[dict] | None]:
    """恢复挂起的研究任务业务逻辑"""
    trace_id_var.set(research_id)

    stmt = (
        select(ResearchTask)
        .options(selectinload(ResearchTask.session))
        .where(
            ResearchTask.session_id == research_id,
            ResearchTask.status == "suspended",
            ResearchTask.pending_approval
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

    active_graph = engine.get_graph()
    run_config = engine.get_run_config(research_id, tenant_id, user_id, preset_id, task_id=task_id)
    
    resume_state: dict[str, Any] = {
        "interaction": {
            "dimensions_approved": True,
            "breakpoint_type": "none"
        }
    }
    if approved_dimensions is not None:
        resume_state["runtime"] = {
            "pipeline": {
                "dimensions": approved_dimensions
            }
        }
        resume_state["interaction"]["approved_dimensions"] = approved_dimensions
    
    if approved_sources is not None:
        resume_state.setdefault("interaction", {})["approved_sources"] = approved_sources
        resume_state["interaction"]["sources_approved"] = True

    logger.info("Resuming research task | task_id={} resume_state_keys={}", task_id, resume_state.keys())
    await active_graph.aupdate_state(run_config, resume_state)

    task.pending_approval = False
    await db.commit()

    return active_graph, run_config, task_id, preset_id, task.thought_steps
