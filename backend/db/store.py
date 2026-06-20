"""🆕 AsyncResearchStore — LangGraph Store 的异步语义化读写封装

通过本文件访问 Store，节点 Nodes 不需要直接操作复杂的 LangGraph Store API。
Namespace 规则：(STORE_NS_PREFIX, tenant_id, research_id, data_type)
data_type 可选值: "search_results" | "filtered" | "claims" | "report"
"""
from __future__ import annotations
from typing import Any
from langgraph.store.base import BaseStore
from langchain_core.runnables import RunnableConfig
from backend.core.config import STORE_NS_PREFIX
from backend.utils.llm_utils import clean_null_bytes

class ResearchStore:
    """包装类，支持异步访问 LangGraph Store。"""
    def __init__(self, store: BaseStore, *, tenant_id: str, research_id: str, task_id: str = ""):
        self._store = store
        self._tenant_id = tenant_id
        self._research_id = research_id
        self._task_id = task_id

    def _ns(self, data_type: str) -> tuple[str, ...]:
        """生成符合命名空间隔离规则的 Namespace 元组。
        
        有 task_id 时为 5 层 (PREFIX, tenant, session, task, type) → Task 级隔离
        无 task_id 时退化为 4 层 (PREFIX, tenant, session, type) → 向后兼容
        """
        base = (STORE_NS_PREFIX, self._tenant_id, self._research_id)
        if self._task_id:
            return (*base, self._task_id, data_type)
        return (*base, data_type)

    # ── 1. 原始搜索结果 ──
    async def save_search_results(self, key: str, data: list[dict[str, Any]]) -> None:
        """异步存储指定 Key（如关键词）下的搜索结果列表"""
        # 兜底清理 NUL 字节，防止 PostgreSQL 写入报错
   
        safe_data = clean_null_bytes(data)
        await self._store.aput(self._ns("search_results"), key=key, value={"items": safe_data})

    async def load_search_results(self, key: str) -> list[dict[str, Any]]:
        """异步获取指定 Key 下的搜索结果"""
        item = await self._store.aget(self._ns("search_results"), key=key)
        return item.value.get("items", []) if item else []

    async def list_search_result_keys(self) -> list[str]:
        """异步列出当前任务下所有搜索结果的 Key"""
        items = await self._store.asearch(self._ns("search_results"))
        return [i.key for i in items]

    async def load_all_search_results(self) -> list[dict[str, Any]]:
        """异步汇总加载当前研究任务下所有的搜索网页条目"""
        keys = await self.list_search_result_keys()
        all_items = []
        for key in keys:
            results = await self.load_search_results(key)
            all_items.extend(results)
        return all_items

    async def load_session_search_results(self) -> list[dict[str, Any]]:
        """异步汇总加载当前会话（Session）下【所有历史任务】的搜索网页条目。
        
        用于实现跨任务知识共享，防止追问时重复搜索。
        """
        # 命名空间搜索前缀：(PREFIX, tenant, session)
        session_ns_prefix = (STORE_NS_PREFIX, self._tenant_id, self._research_id)
        
        # 搜索所有以 search_results 结尾的项
        # LangGraph Store search 支持通配符或后缀匹配并不直接，我们获取所有，然后在内存中过滤
        all_items = await self._store.asearch(session_ns_prefix)
        
        combined_results = []
        seen_urls = set()
        
        for item in all_items:
            # 命名空间最后一位是 data_type
            if item.namespace[-1] == "search_results":
                results = item.value.get("items", [])
                for r in results:
                    url = r.get("url") or r.get("source_url")
                    if url and url not in seen_urls:
                        combined_results.append(r)
                        seen_urls.add(url)
        return combined_results

    # ── 2. 筛选清洗后的网页结果 ──
    async def save_filtered_results(self, key: str, data: list[dict[str, Any]]) -> None:
        """异步存储筛选清洗后的条目"""
        safe_data = clean_null_bytes(data)
        await self._store.aput(self._ns("filtered"), key=key, value={"items": safe_data})

    async def load_filtered_results(self, key: str = "final") -> list[dict[str, Any]]:
        """异步获取筛选清洗后的条目"""
        item = await self._store.aget(self._ns("filtered"), key=key)
        return item.value.get("items", []) if item else []

    # ── 3. 待验证的原子声明 (Claims) ──
    async def save_claims(self, key: str, data: list[dict[str, Any]]) -> None:
        """异步存储从文本中拆解出的原子声明"""
        await self._store.aput(self._ns("claims"), key=key, value={"items": data})

    async def load_claims(self, key: str = "final") -> list[dict[str, Any]]:
        """异步获取拆解出的原子声明"""
        item = await self._store.aget(self._ns("claims"), key=key)
        return item.value.get("items", []) if item else []

    # ── 4. 最终报告 (Final Report) ──
    async def save_report(self, key: str, content: str) -> None:
        """异步存储生成的最终 Markdown 报告内容"""
        await self._store.aput(self._ns("report"), key=key, value={"content": content})

    async def load_report(self, key: str = "final") -> str:
        """异步获取最终 Markdown 报告内容"""
        item = await self._store.aget(self._ns("report"), key=key)
        return item.value.get("content", "") if item else ""

    # ── 5. 关键词扩展缓存 (Keyword Cache) ──
    async def save_keyword_cache(self, value: dict[str, Any]) -> None:
        """异步存储当前研究的关键词扩展缓存结果，以加速重连与重入"""
        await self._store.aput(self._ns("keyword_cache"), key="cache", value=value)

    async def load_keyword_cache(self) -> dict[str, Any] | None:
        """异步获取当前研究的关键词扩展缓存结果"""
        item = await self._store.aget(self._ns("keyword_cache"), key="cache")
        return item.value if item else None


def get_store_from_config(config: RunnableConfig) -> ResearchStore:
    """从配置中获取异步化的 ResearchStore。"""
    configurable = config.get("configurable", {})
    raw_store = configurable.get("store")
    if raw_store is None:
        raise ValueError("LangGraph Config 中缺少底层的 store 实例。")
    tenant_id = configurable.get("tenant_id", "default")
    research_id = configurable.get("research_id", "")
    task_id = configurable.get("task_id", "")
    return ResearchStore(raw_store, tenant_id=tenant_id, research_id=research_id, task_id=task_id)
