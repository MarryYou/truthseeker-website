from __future__ import annotations
import time
from typing import Any
from backend.core.logging import logger

async def _check_search_cache(store: Any, cache_ns: tuple[str, ...], kw: str, dim: str | None) -> tuple[str, list[dict] | None]:
    """读取指定关键词的本地搜索缓存"""
    try:
        item = await store.aget(cache_ns, key=kw)
        if item and isinstance(item.value, dict):
            val = item.value
            created_at = val.get("created_at", 0.0)
            if time.time() - created_at < 24 * 3600:
                cached_results = val.get("results", [])
                mapped_results = []
                for r in cached_results:
                    copied = dict(r)
                    copied["query_keyword"] = kw
                    copied["dimension"] = dim
                    mapped_results.append(copied)
                return kw, mapped_results
    except Exception as e:
        logger.error("读取搜索缓存失败 | keyword='{}' error={}", kw, e)
    return kw, None
