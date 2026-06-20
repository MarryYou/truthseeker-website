"""Tavily 搜索插件"""
from __future__ import annotations
import httpx
from typing import Any
from backend.search.base import SearchPlugin
from backend.search.registry import plugin_registry
from backend.core.logging import logger
from backend.utils.retry import retry


class TavilySearchPlugin(SearchPlugin):
    @property
    def name(self) -> str:
        return "tavily"

    @property
    def is_reader(self) -> bool:
        return False

    async def test_connection(self, api_key: str) -> bool:
        """真实运行 Tavily 搜索以验证 Key 的有效性"""
        url = "https://api.tavily.com/search"
        payload = {"api_key": api_key, "query": "Tavily AI", "max_results": 1}
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(url, json=payload)
                
                # 1. 拦截明确的 401/403
                if resp.status_code in (401, 403):
                    raise ValueError("Tavily 认证失败：API Key 无效或权限不足")
                
                resp.raise_for_status()
                data = resp.json()
                
                # 2. 检查响应体中的错误字段
                if "error" in data or "detail" in data:
                    msg = data.get("error") or data.get("detail") or "未知错误"
                    raise ValueError(f"Tavily API 报错: {msg}")
                
                # 3. 确保返回了结果列表
                if "results" not in data:
                    raise ValueError("Tavily API 响应异常：未返回预期的 results 字段")
                    
                return True
            except (httpx.HTTPError, ValueError) as e:
                if isinstance(e, ValueError):
                    raise e
                raise ValueError(f"Tavily 连接失败: {str(e)}") from e

    @retry(max_retries=2, base_delay=1.0)
    async def search(
        self, 
        query: str, 
        api_key: str, 
        context: dict[str, Any] | None = None,
        **kwargs: Any
    ) -> list[dict]:
        if not api_key:
            logger.warning("Tavily 搜索密钥为空，跳过查询")
            return []

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": api_key,
            "query": query,
            # 差异化配置参数从 kwargs 动态读取，不存在则赋予默认值
            "search_depth": kwargs.get("search_depth", "basic"),
            "max_results": kwargs.get("max_results", 10),
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                
                if response.status_code == 429:
                    logger.warning("Tavily 搜索触发频率限制 (429)，准备重试...")
                    response.raise_for_status() # 抛出异常触发 @retry
                elif response.status_code == 403:
                    logger.error("Tavily 搜索认证失败 (403)，请检查 API Key 是否正确有效。")
                    return []

                response.raise_for_status()
                data = response.json()
                
                results = []
                for item in data.get("results", []):
                    results.append({
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "content": item.get("content"),
                        "snippet": item.get("content")[:200] if item.get("content") else "",
                        "source_type": "web",
                        "engine": self.name,
                        "relevance_score": item.get("score", 0.5)
                    })
                return results
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                return []
            logger.error("Tavily 搜索 HTTP 异常 | status={} error={}", e.response.status_code, e)
            raise e
        except Exception as e:
            logger.error("Tavily 搜索请求执行故障 | error={}", e)
            raise e


# 全局自动注册插件单例
plugin_registry.register(TavilySearchPlugin())
