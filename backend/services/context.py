from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ResearchSession, ResearchTask

logger = logging.getLogger(__name__)


async def resolve_context(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    research_id: str,
    query: str,
) -> dict[str, Any]:
    """处理多轮追问上下文提取，并实施强越权防护。
    
    基于 Task-Checkpointer 双层架构：直接从 SQL research_tasks 表读取历史任务的
    research_conclusion 结构化摘要，不再依赖 LangGraph Checkpointer 快照。
    
    1. 查询 SQL ResearchSessions 表确认该研究属于当前租户 and 用户，防横向越权。
    2. 查询该 session 下所有已完成的 ResearchTask，解析 research_conclusion JSON。
    3. 构造多轮压缩的 follow_up_history：最近 2 轮给完整详情，更早轮次仅保留 core_answer。
    4. 返回供新一轮 Graph 运行的初始 input dict。
    """
    # ── 1. 越权校验 ────────────────────────────────────────────────────
    result = await db.execute(
        select(ResearchSession).where(
            ResearchSession.id == research_id
        )
    )
    session_record = result.scalar_one_or_none()
    if not session_record:
        raise HTTPException(status_code=404, detail="找不到指定的研究会话记录")

    # 🚨 越权防护：必须强校验 tenant_id 与 user_id
    if session_record.tenant_id != tenant_id or session_record.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问该研究会话（多租户越权防护已触发）")

    # ── 2. 从 SQL 查询所有已完成的 ResearchTask ─────────────────────────
    result = await db.execute(
        select(ResearchTask)
        .where(
            ResearchTask.session_id == research_id,
            ResearchTask.status.in_(["completed", "running"]),
        )
        .order_by(ResearchTask.ordinal.asc())
    )
    tasks = result.scalars().all()

    # ── 3. 构造多轮压缩的 follow_up_history ─────────────────────────────
    follow_up_history: list[dict[str, Any]] = []
    total = len(tasks)

    for idx, task in enumerate(tasks):
        conclusion = _parse_conclusion(task.research_conclusion)

        # 最近 2 轮给完整结构化详情，更早轮次仅保留 core_answer
        is_recent = (idx >= total - 2)

        if is_recent and conclusion:
            entry: dict[str, Any] = {
                "query": task.query,
                "core_answer": conclusion.get("core_answer", ""),
                "key_findings": conclusion.get("key_findings", []),
                "covered_aspects": conclusion.get("covered_aspects", []),
                "unresolved": conclusion.get("unresolved", []),
            }
        elif conclusion:
            entry = {
                "query": task.query,
                "core_answer": conclusion.get("core_answer", ""),
            }
        else:
            # 无结构化摘要时降级为普通文本截取
            summary_text = task.summary or ""
            entry = {
                "query": task.query,
                "core_answer": summary_text[:800] if summary_text else "",
            }

        follow_up_history.append(entry)

    # ── 4. 提取历史已验证事实 (Proven Facts) 与结构化上下文 ─────────────────
    last_task = tasks[-1] if tasks else None
    last_conclusion = _parse_conclusion(last_task.research_conclusion) if last_task else {}

    last_research_summary = ""
    last_dimensions: list[Any] = []
    last_unresolved: list[str] = []
    
    # 汇总全量的历史事实摘要 (History Summaries)，限制总长度以防 Token 溢出
    history_summaries = []
    proven_facts = []
    for t in tasks:
        conc = _parse_conclusion(t.research_conclusion)
        if conc.get("history_summary"):
            history_summaries.append(conc["history_summary"])
        
        # 知识承袭：从历史任务的已验证 claims 重构 proven_facts
        if t.claims and isinstance(t.claims, list):
            for c in t.claims:
                if c.get("verdict") in ("verified", "likely_true"):
                    dim_match = [w.replace("维度: ", "") for w in c.get("warnings", []) if isinstance(w, str) and w.startswith("维度: ")]
                    dim = dim_match[0] if dim_match else "通用"
                    srcs = c.get("supporting_sources") or []
                    src_url = srcs[0] if srcs else ""
                    proven_facts.append({
                        "claim": c.get("claim"),
                        "dimension": dim,
                        "source_url": src_url
                    })

    # 智能截断：保留最近 3 轮的完整摘要，其余舍弃
    recent_summaries = history_summaries[-3:]
    aggregated_history_summary = "\n\n".join(recent_summaries)

    if last_conclusion:
        last_research_summary = last_conclusion.get("core_answer", "")
        last_dimensions = last_conclusion.get("covered_aspects", [])
        last_unresolved = last_conclusion.get("unresolved", [])
    elif last_task:
        # 降级：从 task 的 summary / dimensions 列读取
        last_research_summary = (last_task.summary or "")[:800]
        last_dimensions = last_task.dimensions or []

    # 提取上一次任务实际运行的控制参数，用于追问继承
    last_speed = None
    last_verification_level = None

    if last_task:
        last_snap = last_task.run_config_snapshot
        if last_snap and isinstance(last_snap, dict):
            # v3.0: 优先读取 control 字典，兼容 legacy business
            control = last_snap.get("control", {})
            bus = last_snap.get("business", {})
            last_speed = control.get("speed") or bus.get("speed")
            last_verification_level = control.get("verification_level") or bus.get("verification_level")

    # ── 5. 组装并返回初始 input ──────────────────────────────────────────
    preset_id = session_record.preset_id
    original_query = tasks[0].query if tasks else query

    return {
        "query": query,
        "original_query": original_query,
        "research_id": research_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "preset_id": preset_id,
        "context_mode": "follow_up",
        "last_research_summary": last_research_summary,
        "last_research_dimensions": last_dimensions,
        "last_unresolved": last_unresolved,
        "follow_up_history": follow_up_history,
        "history_summary": aggregated_history_summary,
        "last_speed": last_speed,
        "last_verification_level": last_verification_level,
        "proven_facts": proven_facts,
    }


def _parse_conclusion(raw: str | None) -> dict[str, Any]:
    """安全解析 research_conclusion JSON 字段。"""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        logger.warning("research_conclusion JSON 解析失败，降级为空字典")
        return {}
