from __future__ import annotations

import json
import time
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.store.base import BaseStore
from backend.db import crud
from backend.db.store import ResearchStore
from backend.db.models import ResearchTask, ResearchSession
from backend.core.logging import logger
from backend.pipeline.constants import (
    FRONTEND_VERDICT_MAP,
    MAX_CORE_ANSWER_LENGTH,
    MAX_PREVIOUS_DIMENSIONS,
    MAX_UNRESOLVED_QUESTIONS,
    MAX_HISTORY_TURNS
)

def map_claims_to_frontend(raw_claims: list[dict]) -> list[dict]:
    """将 LangGraph 内部的原始声明比对数据映射为前端 UI 期望的 VerificationClaim 格式。"""
    mapped = []

    for c in raw_claims:
        # 1. 基础转换
        verdict = FRONTEND_VERDICT_MAP.get(cast(str, c.get("verdict", "unverifiable")), "unverifiable")
        
        # 2. 构造证据结构
        supports = []
        refutes = []
        
        if verdict in ["verified", "likely_true"]:
            supports.append(c.get("reasoning", "多方信源陈述一致。"))
        elif verdict == "disputed":
            refutes = c.get("conflicts", [])
            supports.append(c.get("reasoning", "部分信源存在冲突。"))
            
        # 3. 汇总信源 URL
        sources = []
        if c.get("source_url"):
            sources.append(c.get("source_url"))

        mapped.append({
            "claim": c.get("text", "未知断言"),
            "verdict": verdict,
            "confidence": float(c.get("consistency_score", 0.5)),
            "evidence": {
                "supports": supports,
                "refutes": refutes
            },
            "supporting_sources": sources,
            "warnings": [f"维度: {c.get('dimension')}"] if c.get("dimension") else []
        })
    return mapped

async def save_research_result(
    db: AsyncSession,
    tenant_id: str,
    research_id: str,
    task_id: str,
    final_state: dict[str, Any],
    raw_store: BaseStore,
    start_time: float,
    status: str = "completed",
    thought_steps: list[dict] | None = None,
    pending_approval: bool = False,
    breakpoint_type: str | None = None,
) -> None:
    """在 LangGraph 运行结束或中断时，从 Store 中归纳元数据，并更新 SQL ResearchTask 数据库。"""
    try:
        # 💡 优化：首先检查记录物理存在性，若已经被删除，直接终止归档
        existing_task = await db.get(ResearchTask, task_id)
        if not existing_task:
            logger.info("归档已忽略 | 数据库中找不到此任务记录 (可能已被物理删除) | task_id={}", task_id)
            return

        # ── 1. 还原 ResearchStore ──────────────────────────────────────────
        store = ResearchStore(raw_store, tenant_id=tenant_id, research_id=research_id, task_id=task_id)
        
        # ── 2. 核实原子声明 (Claims) 统计 ──────────────────────────────────────
        raw_claims = await store.load_claims("final")
        logger.debug("lifecycle 归档 | 从 Store 加载 claims_count={}", len(raw_claims))
        claims_count = len(raw_claims)
        frontend_claims = map_claims_to_frontend(raw_claims)
        
        # 判定已核实的声明数量
        verified_count = sum(1 for c in raw_claims if c.get("verdict") in ["consistent", "mostly_consistent"])
        
        # ── 3. 信源网页去重统计 ──────────────────────────────────────────────
        all_searched_pages = await store.load_all_search_results()
        unique_urls = {p.get("url") for p in all_searched_pages if p.get("url")}
        source_count = len(unique_urls)
        
        # ── 4. 最终 Markdown 报告提取 ────────────────────────────────────────
        report = await store.load_report("final")
        if not report:
            # 兼容嵌套 state 结构
            report = final_state.get("output", {}).get("pipeline", {}).get("report_prompt", "") or \
                     final_state.get("output", {}).get("agent", {}).get("report_prompt", "") or \
                     final_state.get("report_prompt", "")
            
        # ── 5. 计算置信度和时间开销 ──────────────────────────────────────────
        overall_confidence = float(final_state.get("output", {}).get("pipeline", {}).get("overall_confidence", 0.0))
        duration_seconds = int(time.time() - start_time)
        
        # 提取诊断信息
        diagnostics = final_state.get("output", {}).get("diagnostics", {})
        warnings = diagnostics.get("warnings", [])
        raw_errors = diagnostics.get("error_log", [])
        error_log = []
        for err in raw_errors:
            if hasattr(err, "__dict__"):
                error_log.append(err.__dict__)
            elif isinstance(err, dict):
                error_log.append(err)
            else:
                error_log.append({"message": str(err)})
                
        # ── 6. 生成结构化研究结论摘要 ────────────────────────────────────
        research_conclusion: str | None = None
        dimensions = final_state.get("runtime", {}).get("pipeline", {}).get("dimensions", [])
        history_summary = final_state.get("memory", {}).get("history_summary", "")

        if status == "completed" and report:
            research_conclusion = _extract_research_conclusion(
                report=report,
                dimensions=dimensions,
                claims=raw_claims,
                overall_confidence=overall_confidence,
                history_summary=history_summary,
            )

        # ── 6.5 更新运行时快照 (合并 AI 策略) ──────────────────────────────
        run_config_snapshot = existing_task.run_config_snapshot or {}
        
        # 强行记录本次任务实际采取的执行模式，以便历史追溯
        run_config_snapshot["execution_mode"] = final_state.get("control", {}).get("execution_mode", "research_pipeline")
        
        strategy_overrides = final_state.get("runtime", {}).get("pipeline", {}).get("strategy_overrides")
        if strategy_overrides:
            run_config_snapshot["strategy_overrides"] = strategy_overrides

        # ── 7. 物理数据库保存 ────────────────────────────────────────────────
        await crud.update_research_task(
            db=db,
            task_id=task_id,
            status=status,
            summary=report,
            dimensions=dimensions,
            claims=frontend_claims,
            claims_count=claims_count,
            verified_count=verified_count,
            overall_confidence=overall_confidence,
            source_count=source_count,
            duration_seconds=duration_seconds,
            warnings=warnings,
            error_log=error_log,
            thought_steps=thought_steps or [],
            research_conclusion=research_conclusion,
            run_config_snapshot=run_config_snapshot,
            pending_approval=pending_approval,
            breakpoint_type=breakpoint_type,
        )
        
        # ── 7.5 更新 Session 状态与耗时汇总 ────────────────────────────────
        if pending_approval:
            session_status = "suspended"
        elif status in ("completed", "running"):
            session_status = status
        elif status in ("failed", "paused"):
            session_status = status
        else:
            session_status = "paused"

        session_record = await db.get(ResearchSession, research_id)
        if session_record:
            session_record.status = session_status
            if duration_seconds:
                # 💡 物理更新，避免存入 SQLAlchemy 表达式对象导致序列化崩溃
                current_total = session_record.total_duration_seconds or 0
                session_record.total_duration_seconds = current_total + duration_seconds
            await db.flush()
        else:
            await crud.update_research_status(db, research_id, session_status)
    except Exception as e:
        try:
            await crud.update_research_status(db, research_id, "paused")
        except Exception:
            pass
        raise e


def _extract_research_conclusion(
    report: str,
    dimensions: list[Any],
    claims: list[dict[str, Any]],
    overall_confidence: float,
    history_summary: str | None = None,
) -> str:
    """从最终报告和声明的元数据中提取结构化的研究结论 JSON 摘要。

    该摘要用于追问上下文投喂，替代原来的截断式摘要。
    结构:
    {
        "core_answer": "对研究问题的一句话核心回答",
        "key_findings": ["发现1", "发现2", ...],
        "covered_aspects": ["维度1", "维度2", ...],
        "unresolved": ["未解决问题1", ...],
        "history_summary": "该轮问答的事实性简练总结"
    }
    """
    # core_answer: 取报告首段 (通常是对问题的直接回答)
    core_answer = ""
    paragraphs = report.strip().split("\n\n")
    for p in paragraphs:
        p_stripped = p.strip()
        if p_stripped and not p_stripped.startswith("#"):
            core_answer = p_stripped[:MAX_CORE_ANSWER_LENGTH]
            break

    # key_findings: 从 claims 中提取高置信度发现
    key_findings: list[str] = []
    for claim in claims:
        text = claim.get("text", "")
        verdict = claim.get("verdict", "")
        if verdict in ("consistent", "mostly_consistent") and text:
            key_findings.append(text[:200])
    key_findings = key_findings[:MAX_PREVIOUS_DIMENSIONS]  # 限制数量

    # covered_aspects: 从 dimensions 提取
    covered_aspects: list[str] = []
    for dim in dimensions:
        if isinstance(dim, str):
            covered_aspects.append(dim)
        elif isinstance(dim, dict):
            covered_aspects.append(dim.get("name", dim.get("dimension", str(dim))))
    covered_aspects = covered_aspects[:MAX_HISTORY_TURNS]

    # unresolved: 低置信度 / 不可验证 / 相关性缺失的声明
    unresolved: list[str] = []
    for claim in claims:
        text = claim.get("text", "")
        verdict = claim.get("verdict", "")
        if verdict in ("unverifiable", "contradictory") and text:
            unresolved.append(text[:200])
        elif verdict == "single_source" and text and overall_confidence < 0.6:
            unresolved.append(text[:200])
    unresolved = list(set(unresolved))[:MAX_UNRESOLVED_QUESTIONS]

    conclusion = {
        "core_answer": core_answer,
        "key_findings": key_findings,
        "covered_aspects": covered_aspects,
        "unresolved": unresolved,
        "history_summary": history_summary or "",
    }
    return json.dumps(conclusion, ensure_ascii=False)
