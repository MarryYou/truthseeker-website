"""筛选评估 Node — 已拆分为 Coarse 和 LLM 两阶段"""
from __future__ import annotations
from typing import Any, AsyncIterator
from langchain_core.runnables import RunnableConfig

from backend.pipeline.state import StateHelper
from backend.pipeline.types import ResearchState, PipelineAbortError
from backend.pipeline.constants import (
    FILTER_MID_SCORE_THRESHOLD,
    EMBEDDING_DEDUP_THRESHOLD,
    BATCH_FILTER_CONCURRENCY,
    SPEED_PROFILES,
)
from backend.db.store import get_store_from_config
from backend.utils.llm_utils import get_node_config
from backend.core.logging import logger
from backend.services.filter_service import FilterService
from backend.pipeline.nodes.filter_utils import _apply_token_pruning, _extract_valuable_results


async def coarse_filter_node(state: ResearchState, config: RunnableConfig) -> AsyncIterator[dict[str, Any]]:
    """阶段 1: 粗筛与缓存比对"""
    h = StateHelper(state)
    step_id = "filter_results"
    yield h.update_thought_step(step_id, "", status="running", label="信息初步筛选")
    
    rs = get_store_from_config(config)
    fs = FilterService(rs, state["context"].get("tenant_id"), h.user_id, state["context"].get("preset_id"))
    
    rejected_urls = set(state["runtime"]["shared"].get("rejected_urls", []))
    manual_injections = set(state["runtime"]["shared"].get("manual_injections", []))
    
    # 1. 加载全量结果
    all_results = await rs.load_session_search_results() or await rs.load_all_search_results()
    valuable_urls = state["runtime"]["pipeline"].get("valuable_urls", [])
    all_results = _extract_valuable_results(all_results, valuable_urls, manual_injections)
    
    # 2. 粗筛
    node_config = await get_node_config(config, step_id)
    min_relevance = node_config.get("min_relevance_score", FILTER_MID_SCORE_THRESHOLD)
    candidates = fs.coarse_filter(all_results, rejected_urls, manual_injections, min_relevance)
    
    if not candidates:
        yield h.update_thought_step(step_id, "相关性不足，无可入选信源。", type="warning", status="completed")
        await rs.save_filtered_results("final", [])
        return

    # 3. 缓存判定
    cached_results, need_eval = await fs.load_and_split_cache(candidates, manual_injections)
    
    yield {
        **h.update_thought_step(step_id, f"粗筛锁定 {len(candidates)} 条，其中 {len(cached_results)} 条命中缓存。"),
        "runtime": {"pipeline": {"_filter_candidates": need_eval, "_filter_cached": cached_results}}
    }


async def llm_filter_node(state: ResearchState, config: RunnableConfig) -> AsyncIterator[dict[str, Any]]:
    """阶段 2: LLM 语义评估与向量去重"""
    h = StateHelper(state)
    step_id = "filter_results"
    query = h.query
    intent_type = h.intent_type
    dimensions = h.dimensions
    
    need_eval = state["runtime"]["pipeline"].get("_filter_candidates", [])
    cached_results = state["runtime"]["pipeline"].get("_filter_cached", [])

    rs = get_store_from_config(config)
    fs = FilterService(rs, state["context"].get("tenant_id"), h.user_id, state["context"].get("preset_id"))
    
    node_config = await get_node_config(config, step_id)
    batch_concurrency = node_config.get("batch_concurrency", BATCH_FILTER_CONCURRENCY)
    dedup_similarity = node_config.get("dedup_similarity", EMBEDDING_DEDUP_THRESHOLD)

    # 4. LLM 评估
    keep_items = list(cached_results)
    seen_urls = {it.get("url") or it.get("source_url", "") for it in keep_items}
    
    overrides = h.strategy_overrides
    speed_val = h.speed
    default_vl = SPEED_PROFILES.get(speed_val, SPEED_PROFILES["research_pipeline"])["verification_level"]
    verification_level = overrides.get("verification_level") or default_vl

    try:
        if need_eval:
            if verification_level == "skip":
                for r in need_eval:
                    url = r.get("url") or r.get("source_url", "")
                    if url not in seen_urls:
                        keep_items.append(r)
                        seen_urls.add(url)
            else:
                yield h.update_thought_step(step_id, "正在进行大模型语义核验...")
                llm_keep = await fs.process_llm_eval(query, intent_type, dimensions, need_eval, batch_concurrency)
                for it in llm_keep:
                    url = it.get("url") or it.get("source_url", "")
                    if url not in seen_urls:
                        keep_items.append(it)
                        seen_urls.add(url)

        # 5. 去重
        if len(keep_items) > 1 and verification_level != "skip":
            yield h.update_thought_step(step_id, "正在进行语义去重...")
            db = config.get("configurable", {}).get("db")
            keep_items = await fs.semantic_deduplicate(keep_items, dedup_similarity, db=db)

        # 6. 裁剪与保存
        keep_items, _ = _apply_token_pruning(keep_items, dimensions)
        
        # 补全维度
        if dimensions:
            for item in keep_items:
                if not item.get("dimension"):
                    item["dimension"] = dimensions[0]

        if not keep_items:
            raise PipelineAbortError("筛选后无可用信源。")

        await rs.save_filtered_results("final", keep_items)
        step_output = h.update_thought_step(step_id, f"锁定 {len(keep_items)} 条核心信源。", type="success", status="completed")
        step_output["output"]["diagnostics"]["store_refs"] = {"filtered": "final"}
        yield step_output

    except Exception as e:
        logger.error("LLM 筛选失败 | error={}", e)
        yield h.update_thought_step(step_id, "筛选出错", status="error")
        yield h.add_error(step_id, "筛选失败", str(e))
        raise PipelineAbortError(f"筛选节点异常: {e}") from e
