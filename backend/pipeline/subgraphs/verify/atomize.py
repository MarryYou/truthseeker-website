"""atomize 节点 — 从 filtered_results 中提取原子声明，并按维度分组。

设计：
  - 默认走 batch 模式：所有维度 sources 合并为 1 次 LLM call
  - 当维度数 × 信源数过多 (>20 维度信源对) 时 fallback 到 per-dimension 并发
  - 输出 claims（含 text / importance / source_index / source_url / dimension）
"""
from __future__ import annotations
import asyncio
import json
import re
import time
from collections import defaultdict
from typing import AsyncIterator, Any

from langchain_core.runnables import RunnableConfig

from backend.core.llm import get_llm_for_stage
from backend.core.logging import logger
from backend.db.store import get_store_from_config
from backend.pipeline.subgraphs.verify.state import VerifyState
from backend.pipeline.types import ErrorEntry
from backend.pipeline.constants import (
    ATOMIZE_MAX_SOURCES,
    ATOMIZE_MAX_CLAIMS_PER_DIM,
)
from backend.utils.retry import retry
# from backend.pipeline.prompts import ATOMIZE_PROMPT, ATOMIZE_BATCH_PROMPT (Obsolete)
from langchain_core.messages import SystemMessage, HumanMessage
from backend.pipeline.prompts import ATOMIZE_SYSTEM, ATOMIZE_HUMAN
from backend.utils.llm_utils import parse_llm_json, extract_llm_content


@retry(max_retries=1, base_delay=1.0)
async def _atomize_one_dim(
    llm: Any,
    query: str,
    dim: str,
    items: list[dict],
) -> list[dict]:
    """对单个维度并发进行原子化提取"""
    capped = items[:ATOMIZE_MAX_SOURCES]
    results_json = json.dumps(
        [{"index": i, "title": r.get("title", ""), "summary": (r.get("full_text") or r.get("content") or r.get("summary") or r.get("snippet", ""))[:1500]}
         for i, r in enumerate(capped) if r],
        ensure_ascii=False
    )
    
    sys_prompt = ATOMIZE_SYSTEM
    human_prompt = ATOMIZE_HUMAN.format(
        query=query, 
        dimension=dim, 
        results_json=results_json
    )

    messages = [SystemMessage(content=sys_prompt), HumanMessage(content=human_prompt)]
    try:
        resp = await llm.ainvoke(messages)
        raw = extract_llm_content(resp)
        
        json_match = re.search(r"<json>(.*?)</json>", raw, re.DOTALL)
        parsed = parse_llm_json(json_match.group(1) if json_match else raw)
        raw_claims = parsed.get("claims", []) if isinstance(parsed, dict) else []
        
        enriched: list[dict] = []
        for claim in raw_claims[:ATOMIZE_MAX_CLAIMS_PER_DIM]:
            claim["dimension"] = dim
            _enrich_claim(claim, capped)
            enriched.append(claim)
        return enriched
    except Exception as e:
        logger.warning("维度 '{}' 原子化失败 | error={}", dim, e)
        return []


async def atomize_node(state: VerifyState, config: RunnableConfig) -> AsyncIterator[dict[str, Any]]:
    """从 filtered_results 提取原子声明，采用维度聚焦模式 (支持思考链汇报)"""
    start_ts = time.time()
    logger.info("atomize 启动 | 开始提取原子声明")
    
    step_id = "verify_atomize"
    yield {"thought_steps": [{
        "id": step_id, 
        "label": "证据逻辑拆解", 
        "status": "running"
    }]}

    try:
        query = state.get("query", "")
        dimensions = state.get("dimensions", [])
        user_id = state.get("user_id", "default")
        preset_id = state.get("preset_id")

        filtered_items: list[dict] = state.get("_filtered_items", [])
        if not filtered_items:
            try:
                rs = get_store_from_config(config)
                filtered_key = state.get("store_refs", {}).get("filtered", "final")
                filtered_items = await rs.load_filtered_results(filtered_key)
            except Exception:
                filtered_items = []

        # 过滤掉被拒收/剔除的信源
        rejected_urls_raw = state.get("rejected_urls")
        rejected_urls = set(rejected_urls_raw) if isinstance(rejected_urls_raw, list) else set()
        if rejected_urls:
            filtered_items = [
                item for item in filtered_items 
                if item and (item.get("url") or item.get("source_url", "")) not in rejected_urls
            ]

        if not filtered_items:
            yield {"thought_steps": [{
                "id": step_id, 
                "status": "completed",
                "new_sub_step": {"message": "无入选信源，跳过逻辑拆解。", "type": "info"}
            }]}
            yield {
                "claims": [],
                "insufficient_dimensions": dimensions[:],
            }
            return

        # 1. 按 dimension 分组
        dim_groups: dict[str, list[dict]] = defaultdict(list)
        for item in filtered_items:
            dim = item.get("dimension") or "通用"
            dim_groups[dim].append(item)

        missing_dims = [d for d in dimensions if d not in dim_groups]
        
        yield {"thought_steps": [{
            "id": step_id, 
            "new_sub_step": {
                "message": f"正在将 {len(filtered_items)} 个信源按维度进行逻辑解构...", 
                "type": "info"
            }
        }]}

        llm = await get_llm_for_stage(
            "understanding",
            user_id=user_id,
            preset_id=preset_id,
        )

        # 并发对每个维度进行原子化提取
        sem = asyncio.Semaphore(5)
        async def _with_sem(d, it):
            async with sem:
                return await _atomize_one_dim(llm, query, d, it)

        results = await asyncio.gather(*[_with_sem(d, it) for d, it in dim_groups.items()])
        all_enriched = [c for group in results if group is not None for c in group]

        yield {"thought_steps": [{
            "id": step_id, 
            "status": "completed",
            "new_sub_step": {
                "message": f"逻辑拆解完毕。共提取出 {len(all_enriched)} 条核心原子断言。", 
                "type": "success"
            }
        }]}

        duration = round(time.time() - start_ts, 2)
        logger.info("atomize 完成 | 提取声明数={} | 耗时={}s", len(all_enriched), duration)
        yield {
            "claims": all_enriched,
            "insufficient_dimensions": missing_dims,
        }
    except Exception as e:
        logger.error("atomize 节点发生异常 | error={}", e)
        yield {"thought_steps": [{
            "id": step_id, 
            "status": "error",
            "new_sub_step": {"message": f"证据拆解出错: {str(e)}", "type": "error"}
        }]}
        yield {
            "error_log": [ErrorEntry(node="verify_atomize", message="原子声明提取失败", detail=str(e))]
        }


def _enrich_claim(claim: dict, capped_items: list[dict]) -> None:
    """为 claim 补充 source_url / source_name / supporting_urls"""
    effective_len = min(len(capped_items), ATOMIZE_MAX_SOURCES)
    src_indices = claim.get("source_indices", [])
    valid_indices = [i for i in src_indices if 0 <= i < effective_len]
    if valid_indices:
        item = capped_items[valid_indices[0]]
        claim["source_url"] = item.get("url") or item.get("source_url", "")
        claim["source_name"] = item.get("source_name") or item.get("title", "未知信源")
        supporting = []
        for i in valid_indices[1:]:
            s_url = capped_items[i].get("url") or capped_items[i].get("source_url")
            if s_url:
                supporting.append(s_url)
        if supporting:
            claim["supporting_urls"] = supporting

