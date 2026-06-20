"""知乎全网搜索插件。

基于知乎开发者「全网搜索 API」搜索全网内容，兼容站内搜索。
API 文档：https://developer.zhihu.com/docs?key=global_search
"""

from __future__ import annotations

import time
from typing import Any
import httpx


from backend.search.base import SearchPlugin
from backend.search.registry import plugin_registry
from backend.core.logging import logger


# ─── 接口端点 ──────────────────────────────────────────
_GLOBAL_SEARCH_URL = "https://developer.zhihu.com/api/v1/content/global_search"


def _classify_source(url: str) -> str:
    """根据 URL 域名简单分类来源类型。"""
    host = url.lower()
    if "zhihu.com" in host:
        return "community"
    if any(d in host for d in ("gov.cn", "people.com.cn", "xinhua.net", "cctv.com")):
        return "official"
    if any(d in host for d in ("weibo.com", "twitter.com", "x.com")):
        return "social_media"
    if any(d in host for d in ("jd.com", "taobao.com", "tmall.com", "amazon.")):
        return "ecommerce"
    if any(d in host for d in ("qq.com", "163.com", "sohu.com", "sina.com.cn", "ifeng.com")):
        return "media"
    return "web"


class ZhihuPlugin(SearchPlugin):
    """知乎全网搜索插件。

    使用知乎开放平台全网搜索 API (global_search)，覆盖全网网页内容。
    支持高级 Filter 语法（按站点 host、发布时间 publish_time 过滤）。
    """

    @property
    def name(self) -> str:
        return "zhihu"

    @property
    def is_reader(self) -> bool:
        return False

    async def test_connection(self, api_key: str) -> bool:
        """真实运行知乎搜索以验证 Key 的有效性"""
        import time
        url = "https://developer.zhihu.com/api/v1/content/global_search"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Request-Timestamp": str(int(time.time())),
            "Content-Type": "application/json",
        }
        # 执行一次真实的极简搜索
        params = {"Query": "知乎", "Count": 1, "SearchDB": "all"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(url, headers=headers, params=params)
                
                # 1. 拦截 401/403
                if resp.status_code in (401, 403):
                    raise ValueError("知乎认证失败：API Key 无效或无权限")
                
                resp.raise_for_status()
                body = resp.json()
                
                # 2. 检查业务逻辑 Code
                code = body.get("Code", -1)
                if code != 0:
                    msg = body.get("Message") or "认证异常"
                    raise ValueError(f"知乎 API 报错: {msg} (Code: {code})")
                
                # 3. 验证数据结构
                if "Data" not in body or "Items" not in body.get("Data", {}):
                    raise ValueError("知乎 API 响应异常：未返回预期的 Data/Items 字段")
                
                return True
            except (httpx.HTTPError, ValueError) as e:
                if isinstance(e, ValueError):
                    raise e
                raise ValueError(f"知乎连接失败: {str(e)}") from e

    async def search(
        self, 
        query: str, 
        api_key: str, 
        context: dict[str, Any] | None = None,
        **kwargs: Any
    ) -> list[dict]:

        """执行知乎全网搜索。

        API 规范：
        - GET https://developer.zhihu.com/api/v1/content/global_search
        - Headers: Authorization Bearer, X-Request-Timestamp, Content-Type
        - Query 参数: Query (关键词), Count (1-20), Filter (可选), SearchDB (可选)
        """
        if not api_key:
            logger.warning("知乎搜索密钥为空，跳过查询")
            return []

        timestamp = str(int(time.time()))
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Request-Timestamp": timestamp,
            "Content-Type": "application/json",
        }

        max_results = kwargs.get("max_results", 10)
        params: dict[str, str | int] = {
            "Query": query,
            "Count": min(max_results, 20),
            "SearchDB": "all",
        }

        # 根据时间范围构建 Filter
        time_range = kwargs.get("freshness", "no_limit")
        filter_parts: list[str] = []
        if time_range in ("day", "week", "month", "year"):
            now = int(time.time())
            seconds_map = {"day": 86400, "week": 604800, "month": 2592000, "year": 31536000}
            threshold = now - seconds_map[time_range]
            filter_parts.append(f"publish_time>={threshold}")
        if filter_parts:
            params["Filter"] = " AND ".join(filter_parts)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    _GLOBAL_SEARCH_URL,
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                body = resp.json()

            # 解析响应
            code = body.get("Code", -1)
            if code != 0:
                msg = body.get("Message", "unknown")
                logger.warning("知乎搜索返回错误 | code={} msg={}", code, msg)
                if code == 30001:  # 频率超限 (second limit exceeded)
                    raise ConnectionError(f"知乎搜索请求频率超限: {msg}")
                return []

            data = body.get("Data", {})
            items = data.get("Items", [])

            results: list[dict] = []
            for item in items:
                url = item.get("Url", "")
                if not url:
                    continue

                title = item.get("Title", "")
                content_text = item.get("ContentText", "")
                vote_up = item.get("VoteUpCount", 0)
                comment_count = item.get("CommentCount", 0)
                authority = item.get("AuthorityLevel", "0")
                content_type = item.get("ContentType", "")
                author = item.get("AuthorName", "")
                edit_time = item.get("EditTime", 0)

                # content 格式化：摘要 + 作者信息
                content_parts = []
                if content_text:
                    content_parts.append(content_text)
                if author:
                    content_parts.append(f"作者: {author}")
                content_str = " | ".join(content_parts) if content_parts else title

                # 根据 URL 实际域名分类
                source_type = _classify_source(url)

                # 安全转换 authority 为 float
                try:
                    authority_val = float(authority)
                except ValueError:
                    authority_val = 0.0

                results.append({
                    "title": title,
                    "url": url,
                    "content": content_str,
                    "snippet": content_text[:200] if content_text else "",
                    "source_type": source_type,
                    "engine": self.name,
                    "relevance_score": round(authority_val * 0.1 + vote_up * 0.01, 3),
                    "metadata": {
                        "published_date": str(edit_time) if edit_time else None,
                        "content_type": content_type,
                        "vote_up_count": vote_up,
                        "comment_count": comment_count,
                        "authority_level": authority,
                        "author_name": author,
                    },
                })

            logger.debug(
                "知乎全网搜索完成 | query={} results={}",
                query[:40], len(results),
            )
            return results

        except Exception as e:
            logger.error("知乎搜索请求异常: {}", e)
            return []


# 全局自动注册插件单例
plugin_registry.register(ZhihuPlugin())
