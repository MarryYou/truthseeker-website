"""网页筛选核心逻辑服务 — 从 Node 中解耦出的纯业务逻辑"""
from __future__ import annotations
import asyncio
import json
import re
from typing import Any
from backend.pipeline.constants import (
    FILTER_LLM_BODY_TRUNCATE,
    EMBEDDING_DEDUP_THRESHOLD,
    BATCH_FILTER_CONCURRENCY,
)
from backend.core.llm import get_llm_for_stage
from backend.services.embedding_service import embed_documents_with_preset
from backend.utils.llm_utils import parse_llm_json, extract_llm_content
from backend.utils.retry import retry
from backend.pipeline.nodes.filter_utils import (
    calculate_cosine_similarity,
    calc_batch_size,
    get_surgical_window,
)
from langchain_core.messages import SystemMessage, HumanMessage
from backend.pipeline.prompts import FILTER_SYSTEM, FILTER_HUMAN
from backend.db.engine import async_session

class FilterService:
    def __init__(
        self, 
        rs: Any, 
        tenant_id: str | None = None, 
        user_id: str = "default", 
        preset_id: str | None = None
    ):
        self.rs = rs
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.preset_id = preset_id

    def coarse_filter(
        self,
        all_results: list[dict],
        rejected_urls: set[str],
        manual_injections: set[str],
        min_relevance: float,
    ) -> list[dict]:
        """相关性粗筛逻辑"""
        candidates = []
        for i, r in enumerate(all_results):
            url = r.get("url") or r.get("source_url", "")
            if url in rejected_urls:
                continue
                
            score = r.get("relevance_score")
            if url in manual_injections:
                r["relevance_score"] = 1.0
                candidates.append(r)
                continue

            if score is None:
                score = max(0.0, 1.0 - i * 0.1)
                r["relevance_score"] = score
            
            if score >= min_relevance:
                candidates.append(r)
        return candidates

    async def load_and_split_cache(
        self,
        candidates: list[dict],
        manual_injections: set[str],
    ) -> tuple[list[dict], list[dict]]:
        """加载缓存并划分为：命中缓存项 和 需LLM评估项"""
        cache_list = await self.rs.load_filtered_results("filter_cache")
        cache_map = {c.get("url"): c for c in cache_list if c.get("url")}
        
        cached_results = []
        need_eval = []

        for r in candidates:
            url = r.get("url") or r.get("source_url", "")
            if url in manual_injections:
                need_eval.append(r)
                continue
                
            if url in cache_map:
                cached_info = cache_map[url]
                r["keep_reason"] = cached_info.get("keep_reason", "")
                if cached_info.get("summary"):
                    r["summary"] = cached_info["summary"]
                if cached_info.get("keep", False):
                    cached_results.append(r)
            else:
                need_eval.append(r)

        return cached_results, need_eval

    async def process_llm_eval(
        self,
        query: str,
        intent_type: str,
        dimensions: list[str],
        items_to_eval: list[dict],
        batch_concurrency: int = BATCH_FILTER_CONCURRENCY,
    ) -> list[dict]:
        """执行大模型分批核验"""
        if not items_to_eval:
            return []

        # 构造带索引的临时列表供 LLM 对应
        indexed_items = [(i, r) for i, r in enumerate(items_to_eval)]
        batch_size = calc_batch_size(items_to_eval)
        batches = [indexed_items[i : i + batch_size] for i in range(0, len(indexed_items), batch_size)]

        semaphore = asyncio.Semaphore(batch_concurrency)
        db_write_lock = asyncio.Lock()

        async def _filter_one_batch(batch):
            async with semaphore:
                res = await self._call_filter_llm(query, intent_type, batch, dimensions)
                if res and isinstance(res, list):
                    # 异步写回缓存
                    new_caches = []
                    for item in res:
                        idx = item.get("index", -1)
                        if 0 <= idx < len(items_to_eval):
                            original = items_to_eval[idx]
                            url = original.get("url") or original.get("source_url", "")
                            if url:
                                new_caches.append({
                                    "url": url,
                                    "keep": item.get("keep", False),
                                    "summary": item.get("summary", ""),
                                    "keep_reason": item.get("reason", "")
                                })
                    if new_caches:
                        async with db_write_lock:
                            current_caches = await self.rs.load_filtered_results("filter_cache")
                            current_map = {c.get("url"): c for c in current_caches if c.get("url")}
                            for nc in new_caches:
                                current_map[nc["url"]] = nc
                            await self.rs.save_filtered_results("filter_cache", list(current_map.values()))
                return res

        batch_results = await asyncio.gather(*[_filter_one_batch(b) for b in batches], return_exceptions=True)

        keep_items = []
        seen_urls = set()
        for res_list in batch_results:
            if isinstance(res_list, list):
                for item in res_list:
                    if not item.get("keep", False):
                        continue
                    idx = item.get("index", -1)
                    if 0 <= idx < len(items_to_eval):
                        original = items_to_eval[idx]
                        original["summary"] = item.get("summary", "")
                        original["keep_reason"] = item.get("reason", "")
                        url = original.get("url", original.get("source_url", ""))
                        if url not in seen_urls:
                            keep_items.append(original)
                            seen_urls.add(url)
        return keep_items

    @retry(max_retries=1, base_delay=0.5)
    async def _call_filter_llm(self, query: str, intent_type: str, batch: list[tuple[int, dict]], dimensions: list[str]) -> list[dict]:
        items_to_send = []
        for idx, r in batch:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            body = get_surgical_window(r.get("content", ""), dimensions, window_size=FILTER_LLM_BODY_TRUNCATE)
            mixed_context = f"【标题】: {title}\n【摘要片段】: {snippet}\n【正文采样】: {body}"
            items_to_send.append({"index": idx, "source_name": title, "content": mixed_context})

        llm = await get_llm_for_stage("understanding", user_id=self.user_id, preset_id=self.preset_id)
        messages = [
            SystemMessage(content=FILTER_SYSTEM),
            HumanMessage(content=FILTER_HUMAN.format(query=query, intent_type=intent_type, items_json=json.dumps(items_to_send, ensure_ascii=False)))
        ]
        resp = await llm.ainvoke(messages)
        raw = extract_llm_content(resp)
        json_match = re.search(r"<json>(.*?)</json>", raw, re.DOTALL)
        return parse_llm_json(json_match.group(1) if json_match else raw)

    async def semantic_deduplicate(self, items: list[dict], threshold: float = EMBEDDING_DEDUP_THRESHOLD, db: Any = None) -> list[dict]:
        """向量语义去重"""
        if len(items) <= 1:
            return items
        texts = [f"{it.get('title', '')} {it.get('summary', it.get('snippet', ''))}" for it in items]
        
        if db is not None:
            vectors = await embed_documents_with_preset(db, texts, user_id=self.user_id, preset_id=self.preset_id)
        else:
            async with async_session() as session:
                vectors = await embed_documents_with_preset(session, texts, user_id=self.user_id, preset_id=self.preset_id)
        
        final_keep = []
        final_vectors = []
        for idx, item in enumerate(items):
            is_dup = False
            for existing_idx, existing_vec in enumerate(final_vectors):
                sim = calculate_cosine_similarity(vectors[idx], existing_vec)
                if sim > threshold:
                    if item.get("relevance_score", 0) > final_keep[existing_idx].get("relevance_score", 0):
                        final_keep[existing_idx] = item
                        final_vectors[existing_idx] = vectors[idx]
                    is_dup = True
                    break
            if not is_dup:
                final_keep.append(item)
                final_vectors.append(vectors[idx])
        return final_keep
