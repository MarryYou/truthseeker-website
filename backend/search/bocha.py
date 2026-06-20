"""博查搜索插件"""
from __future__ import annotations
import httpx
from typing import Any
from backend.search.base import SearchPlugin
from backend.search.registry import plugin_registry
from backend.core.logging import logger


from backend.utils.retry import retry


class BochaSearchPlugin(SearchPlugin):
    @property
    def name(self) -> str:
        return "bocha"

    @property
    def is_reader(self) -> bool:
        return False

    async def test_connection(self, api_key: str) -> bool:
        """真实运行博查搜索以验证 Key 的有效性"""
        url = "https://api.bochaai.com/v1/web-search"
        # 执行一次真实的极简搜索
        payload = {"query": "博查", "count": 1}
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                
                # 1. 拦截明确的 401/403
                if resp.status_code in (401, 403):
                    raise ValueError("博查认证失败：API Key 无效或权限不足")
                
                resp.raise_for_status()
                data = resp.json()
                
                # 2. 校验业务逻辑返回码 (博查通常返回 200，但内部可能包含错误码)
                if data.get("code") != 200:
                    msg = data.get("msg") or "未知认证错误"
                    raise ValueError(f"博查 API 报错: {msg} (Code: {data.get('code')})")
                
                # 3. 验证是否返回了搜索数据结构（证明 Key 权限正常）
                if "data" not in data or "webPages" not in data.get("data", {}):
                    raise ValueError("博查 API 响应异常：未返回预期的搜索结果结构")
                    
                return True
            except (httpx.HTTPError, ValueError) as e:
                if isinstance(e, ValueError):
                    raise e
                raise ValueError(f"博查连接失败: {str(e)}") from e

    @retry(max_retries=2, base_delay=1.0)
    async def search(
        self, 
        query: str, 
        api_key: str, 
        context: dict[str, Any] | None = None,
        **kwargs: Any
    ) -> list[dict]:
        if not api_key:
            logger.warning("博查搜索密钥为空，跳过查询")
            return []

        url = "https://api.bochaai.com/v1/web-search"
        payload = {
            "query": query,
            "count": kwargs.get("max_results", 10),
            # 差异化配置参数从 kwargs 动态读取，不存在则赋予默认值
            "freshness": kwargs.get("freshness", "no_limit"),
        }
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code == 429:
                    logger.warning("博查搜索触发频率限制 (429)，准备重试...")
                    response.raise_for_status() # 抛出异常触发 @retry
                elif response.status_code == 403:
                    logger.error("博查搜索认证失败 (403)，请检查 API Key 是否正确有效。")
                    return []
                
                response.raise_for_status()
                data = response.json()

                web_pages = data.get("data", {}).get("webPages", {}).get("value", [])
                logger.debug("博查原始响应 | query='{}' status={} code={} pages={}", query, response.status_code, data.get("code"), len(web_pages))

                results = []
                for item in web_pages:
                    results.append({
                        "title": item.get("name"),
                        "url": item.get("url"),
                        "content": item.get("snippet"),
                        "snippet": item.get("snippet"),
                        "source_type": "web",
                        "engine": self.name,
                        "relevance_score": 0.5
                    })
                if not results:
                    logger.warning("博查返回空结果 | query='{}' 完整响应: code={} msg={} data_keys={}", query, data.get("code"), data.get("msg"), list(data.get("data", {}).keys()))
                return results
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                return []
            logger.error("博查搜索 HTTP 异常 | status={} error={}", e.response.status_code, e)
            raise e
        except Exception as e:
            logger.error("博查搜索请求执行故障 | error={}", e)
            raise e


# 全局自动注册插件单例
plugin_registry.register(BochaSearchPlugin())
