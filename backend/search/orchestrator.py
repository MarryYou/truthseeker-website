"""多搜索引擎并发调度与去重编排器"""
from __future__ import annotations
import asyncio
import time
from typing import Any, cast
from backend.search.registry import plugin_registry
from backend.core.logging import logger
from backend.db.crud import get_decrypted_provider_key
from backend.utils.limiter import limiter

# 显式引入具体插件文件，以触发底层的 @plugin_registry.register() 自动注册机制

class SearchOrchestrator:
    # 类级别/实例级别记录上一次调用的结束时间，用于单机兜底限流
    _last_call_time: float = 0.0

    def __init__(self, db: Any, tenant_id: str, user_id: str | None = None):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def search(
        self,
        query: str,
        engines: list[str],
        preset_id: str | None = None,
        max_results_per_query: int = 10,
        max_concurrent_engines: int = 3,
        rate_limit_delay: float = 0.0,
        engine_params: dict[str, Any] | None = None,
    ) -> list[dict]:
        """多搜索引擎并发调用与去重编排接口 (纯执行层)"""
        if not engines:
            logger.warning("未勾选任何搜索引擎，返回空结果")
            return []

        # 1. 分布式滑动窗口限流控制 (Sliding Cooldown)
        resource_id = f"search:{self.user_id or self.tenant_id}"
        
        if rate_limit_delay > 0.0:
            logger.debug("执行搜索限流策略 | resource_id={} delay={}s", resource_id, rate_limit_delay)
            await limiter.wait_for_cooldown(resource_id, rate_limit_delay)
            
            now = time.time()
            elapsed = now - SearchOrchestrator._last_call_time
            if SearchOrchestrator._last_call_time > 0.0 and elapsed < rate_limit_delay:
                sleep_time = rate_limit_delay - elapsed
                await asyncio.sleep(sleep_time)

        # 2. 构造并发调用任务
        tasks = []
        engine_params = engine_params or {}

        # 构造统一上下文对象，传递给插件
        context = {
            "db": self.db,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "preset_id": preset_id
        }

        for engine_name in engines:
            plugin = plugin_registry.get_plugin(engine_name)
            if not plugin or getattr(plugin, 'is_reader', False):
                continue

            # 获取凭证
            try:
                api_key = await get_decrypted_provider_key(
                    self.db, cast(str, self.user_id or "default"), "search", engine_name
                )
                logger.debug("搜索引擎凭证 | engine={} has_key={} db_type={}", engine_name, bool(api_key), type(self.db).__name__)
            except Exception as e:
                logger.error("获取搜索引擎凭证异常 | engine={} error={}", engine_name, e)
                continue

            if not api_key:
                logger.error("未配置搜索引擎 API Key | engine={} user_id={}", engine_name, self.user_id)
                continue

            # 准备参数
            kwargs = engine_params.get(engine_name, {})
            kwargs.setdefault("max_results", max_results_per_query)
            
            # 显式传递 context，不再使用 setattr 注入
            tasks.append(plugin.search(query, api_key=api_key, context=context, **kwargs))

        if not tasks:
            return []

        # 3. 执行
        logger.info("启动并发搜索 | query='{}' engines={}", query[:50], engines)
        sem = asyncio.Semaphore(max_concurrent_engines)
        async def _run_with_sem(t):
            async with sem:
                return await t
            
        raw_results = await asyncio.gather(*[_run_with_sem(t) for t in tasks], return_exceptions=True)

        # 4. 去重与更新限流
        seen_urls = set()
        flat_results = []
        for res in raw_results:
            if isinstance(res, list):
                for item in res:
                    url = item.get("url")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        flat_results.append(item)

        await limiter.update_cooldown(resource_id)
        SearchOrchestrator._last_call_time = time.time()
        return flat_results
