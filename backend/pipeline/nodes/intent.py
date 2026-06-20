from __future__ import annotations
import asyncio
import json
import re
from typing import Any, AsyncIterator
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage
import numpy as np

from backend.pipeline.state import StateHelper
from backend.pipeline.types import ResearchState, PipelineAbortError
from backend.pipeline.constants import (
    DIMENSION_DEDUP_THRESHOLDS,
    DIMENSION_DEDUP_SIMILARITY,
    SPEED_PROFILES,
)
from backend.db.engine import async_session
from backend.pipeline.prompts import (
    INTENT_ANALYZE_SYSTEM, INTENT_ANALYZE_HUMAN,
    FOLLOW_UP_INTENT_SYSTEM, FOLLOW_UP_INTENT_HUMAN,
)
from backend.core.llm import get_llm_for_stage
from backend.utils.llm_utils import extract_llm_content, parse_llm_json
from backend.services.embedding_service import embed_documents_with_preset
from backend.core.logging import logger


_LLM_MAX_RETRIES = 1
_LLM_RETRY_DELAY = 2.0


async def _llm_invoke_with_retry(llm: Any, messages: list) -> Any:
    """带重试的 LLM 调用。失败超出重试次数则抛出 PipelineAbortError。"""
    last_exc: Exception | None = None
    for attempt in range(_LLM_MAX_RETRIES + 1):
        try:
            return await llm.ainvoke(messages)
        except Exception as exc:
            last_exc = exc
            if attempt < _LLM_MAX_RETRIES:
                logger.warning(
                    "意图分析 LLM 重试 | attempt={}/{} error={}",
                    attempt + 1, _LLM_MAX_RETRIES, exc,
                )
                await asyncio.sleep(_LLM_RETRY_DELAY)
    raise PipelineAbortError(f"意图分析 LLM 调用失败: {last_exc}")


async def _deduplicate_dimensions(
    base_dims: list[str],
    new_dims: list[str],
    threshold: float,
    tenant_id: str | None,
    user_id: str | None,
    preset_id: str | None,
    db: Any = None
) -> list[str]:
    """使用 Embedding 语义去重，在保留 base_dims 的前提下过滤 new_dims 中与基准及彼此重复的项。"""
    if not new_dims:
        return base_dims
    
    all_dims = base_dims + new_dims
    try:
        if db is not None:
            vectors = await embed_documents_with_preset(db, all_dims, user_id=user_id, preset_id=preset_id)
        else:
            async with async_session() as session:
                vectors = await embed_documents_with_preset(session, all_dims, user_id=user_id, preset_id=preset_id)
        vecs = [np.array(v) for v in vectors]
    except Exception as e:
        logger.warning("维度语义去重生成 Embedding 失败，降级退回字面合并 | error={}", e)
        # 降级：仅进行字面字词去重
        keep_dims = list(base_dims)
        for d in new_dims:
            if d not in keep_dims:
                keep_dims.append(d)
        return keep_dims

    keep_dims: list[str] = []
    base_len = len(base_dims)
    for i, dim in enumerate(all_dims):
        if i < base_len:
            keep_dims.append(dim)
            continue
        is_dup = False
        for j, _ in enumerate(keep_dims):
            sim = float(np.dot(vecs[i], vecs[j]) / (np.linalg.norm(vecs[i]) * np.linalg.norm(vecs[j]) + 1e-8))
            if sim > threshold:
                is_dup = True
                break
        if not is_dup:
            keep_dims.append(dim)
    return keep_dims


async def intent_node(state: ResearchState, config: RunnableConfig) -> AsyncIterator[dict[str, Any]]:
    """意图分析节点 (职责单一：拆解研究维度)"""
    h = StateHelper(state)
    query = h.query
    context_mode = state["context"].get("context_mode", "new_research")
    tenant_id = state["context"].get("tenant_id")
    user_id = h.user_id
    preset_id = state["context"].get("preset_id")

    # ── 1. 配置读取 ──
    speed = h.speed
    profile = SPEED_PROFILES.get(speed, SPEED_PROFILES["research_pipeline"])
    overrides = h.strategy_overrides

    # 维度范围解析
    max_dim_val = overrides.get("intent_max_dimensions") or overrides.get("max_dimensions") or profile.get("intent_max_dimensions") or {"min": 2, "max": 4}
    max_dim_text = f"{max_dim_val['min']}-{max_dim_val['max']}" if isinstance(max_dim_val, dict) else str(max_dim_val)
    
    step_id = "intent_analyze"
    yield h.update_thought_step(step_id, "", status="running", label="意图理解与维度拆解")

    try:
        llm = await get_llm_for_stage(
            "understanding",
            user_id=user_id,
            preset_id=preset_id,
        )

        proven_facts = state["memory"].get("proven_facts", [])
        proven_facts_json = json.dumps(proven_facts, ensure_ascii=False) if proven_facts else "暂无已知事实"

        if context_mode == "follow_up":
            # ── 追问模式 ──
            last_dimensions = state["runtime"]["shared"].get("last_research_dimensions", [])
            last_unresolved = state["runtime"]["shared"].get("last_unresolved", [])
            history_summary = state["memory"].get("history_summary", "")

            sys_prompt = FOLLOW_UP_INTENT_SYSTEM.format(max_dim_range=max_dim_text)
            human_prompt = FOLLOW_UP_INTENT_HUMAN.format(
                query=query,
                original_query=state["runtime"]["shared"].get("original_query", ""),
                proven_facts_json=proven_facts_json,
                covered_dimensions="、".join(last_dimensions) if last_dimensions else "无",
                unresolved="\n".join(f"- {u}" for u in last_unresolved) if last_unresolved else "无明确未解决问题",
                follow_up_history_summary=history_summary or "无",
            )
        else:
            # ── 新研究模式 ──
            sys_prompt = INTENT_ANALYZE_SYSTEM.format(max_dim_range=max_dim_text)
            human_prompt = INTENT_ANALYZE_HUMAN.format(
                query=query,
                proven_facts_json=proven_facts_json
            )

        messages = [SystemMessage(content=sys_prompt), HumanMessage(content=human_prompt)]
        resp = await _llm_invoke_with_retry(llm, messages)
        raw = extract_llm_content(resp)
        
        # XML 解析
        json_match = re.search(r"<json>(.*?)</json>", raw, re.DOTALL)
        parsed = parse_llm_json(json_match.group(1) if json_match else raw)

        intent_type = parsed.get("intent_type", "explore")
        search_plan = parsed.get("search_plan", "")
        dedup_intensity = parsed.get("dedup_intensity", "standard")
        dedup_threshold = DIMENSION_DEDUP_THRESHOLDS.get(dedup_intensity, DIMENSION_DEDUP_SIMILARITY)
        
        configurable = config.get("configurable", {})
        db = configurable.get("db")

        if context_mode == "follow_up":
            last_dimensions = state["runtime"]["shared"].get("last_research_dimensions", [])
            keep_dims_parsed = parsed.get("keep_dimensions", [])
            new_dimensions = parsed.get("new_dimensions", [])
            
            # 安全白名单过滤，并做大模型写漏/解析空时的退化继承兜底
            if not keep_dims_parsed and not new_dimensions:
                keep_dims_base = list(last_dimensions)
            else:
                keep_dims_base = [d for d in keep_dims_parsed if d in last_dimensions]
            
            # 使用自适应阈值对大纲进行语义去重
            dimensions = await _deduplicate_dimensions(
                keep_dims_base,
                new_dimensions or [],
                dedup_threshold,
                tenant_id,
                user_id,
                preset_id,
                db=db
            )
        else:
            raw_dimensions = parsed.get("dimensions", [])
            # 新研究模式下也进行自适应档位的基础语义去重保护
            dimensions = await _deduplicate_dimensions(
                [],
                raw_dimensions or [],
                dedup_threshold,
                tenant_id,
                user_id,
                preset_id,
                db=db
            )

        # 计算最大维度数量
        if isinstance(max_dim_val, dict):
            max_dimensions = int(max_dim_val.get("max", 4))
        else:
            max_dimensions = int(max_dim_val)
        
        if dimensions:
            dimensions = dimensions[:max_dimensions]
        if not dimensions:
            dimensions = ["一般信息"]

        yield h.update_thought_step(step_id, f"意图分析完毕。判定类型: {intent_type}，拆解维度: {len(dimensions)} 个。", type="success", status="completed")

        yield {
            "runtime": {
                "shared": {"intent_type": intent_type},
                "pipeline": {
                    "search_plan": search_plan,
                    "dimensions": dimensions,
                    "dedup_intensity": dedup_intensity,
                }
            }
        }

    except Exception as e:
        logger.error("意图分析失败 | error={}", e)
        yield h.update_thought_step(step_id, f"意图分析出错，无法继续研究: {str(e)}", type="error", status="error")
        yield h.add_error(step_id, "意图分析失败", str(e))
        raise PipelineAbortError(f"意图分析节点异常，任务终止: {str(e)}") from e
