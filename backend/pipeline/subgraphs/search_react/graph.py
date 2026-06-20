"""SearchReAct — 使用 create_agent + middleware 实现搜索"""
from __future__ import annotations
from typing import Any
from langchain.agents import create_agent
from langchain_core.tools import tool
from backend.search.orchestrator import SearchOrchestrator
from backend.core.logging import logger
from backend.db.store import ResearchStore
from backend.db.engine import async_session
from .middleware import SearchAgentMiddleware


def _infer_dimension(query: str, dimensions: list[str]) -> str:
    """从搜索 query 中推断所属维度——匹配维度名称中的连续汉字子串。"""
    if not dimensions:
        return ""
    if len(dimensions) == 1:
        return dimensions[0]
    # 尝试子串匹配：维度名中的长关键词出现在 query 中即命中
    for dim in dimensions:
        # 取维度名前 6 个字（覆盖大部分维度名特征）
        seg = dim[:6]
        if len(seg) > 1 and seg in query:
            return dim
    return ""


def build_search_agent(
    llm: Any,
    raw_store: Any,
    tenant_id: str,
    user_id: str,
    research_id: str,
    task_id: str,
    preset_id: str | None,
    suggested_engines: list[str] | None = None,
    max_results: int = 5,
    dimensions: list[str] | None = None,
    max_rounds: int = 3,
    keywords_per_dim: int = 3,
    bilingual: bool = False,
    include_year: bool = False,
):
    """构建搜索 Agent 实例"""
    engines = suggested_engines if isinstance(suggested_engines, list) and suggested_engines else ["tavily", "bocha"]
    dims = dimensions or []

    # max_steps = max_rounds 次搜索LLM调用 + 1次评估输出
    max_steps = max_rounds + 2

    @tool
    async def search_web(query: str, dimension: str = "", count: int | None = None) -> str:
        """在互联网上搜索信息。传入 dimension 以便标记结果归属的维度（可选）。"""
        effective = min(max(1, count or max_results), max_results)

        # 实时检查已执行查询次数（基于 维度数 * 关键词数 的动态熔断机制）
        store = ResearchStore(raw_store, tenant_id=tenant_id, research_id=research_id, task_id=task_id)
        try:
            # 🚨 升级：检查整个会话的历史搜索词，实现跨任务去重
            session_results = await store.load_session_search_results()
            searched_queries = set(r.get("query_keyword") for r in session_results if r.get("query_keyword"))
            
            # 同时也检查是否有 URL 已经被搜过且内容相似
            if any(query.lower() in (r.get("title", "").lower() + r.get("snippet", "").lower()) for r in session_results):
                 logger.info("SearchReAct: 发现历史任务已涵盖关键词 '{}' 的相关信息，跳过重复搜索", query)
                 return "系统提示：该关键词在之前的对话中已有相关的详细搜索结果。请直接基于历史上下文进行分析，无需重复搜索。"

            # 计算最大允许查询次数
            max_queries_limit = max(1, len(dims)) * keywords_per_dim
            
            if len(searched_queries) >= max_queries_limit and query not in searched_queries:
                logger.info("SearchReAct: 已达到最大搜索次数上限 (维度{} * 关键词{} = {}), 拒绝继续检索词: {}", len(dims), keywords_per_dim, max_queries_limit, query)
                return f"系统提示：当前已累积执行 {len(searched_queries)} 次搜索（预设上限：{max_queries_limit}次）。请停止调用 search_web，直接基于已有数据输出您的评估结论。"
        except Exception as e:
            logger.warning("检查已搜索总数失败: {}", e)

        async with async_session() as session:
            orchestrator = SearchOrchestrator(session, tenant_id, user_id)
            results = await orchestrator.search(query=query, engines=engines, preset_id=preset_id, max_results_per_query=effective)
            if not results:
                return "未找到相关搜索结果。"
            # 标记维度：优先使用显式传入的，否则尝试推断
            inferred = dimension or _infer_dimension(query, dims)
            if inferred:
                for r in results:
                    r["dimension"] = inferred
            try:
                await store.save_search_results(query, results)
            except Exception as e:
                logger.error("搜索结果落库失败 | error={}", e)
        formatted = [f"标题: {r.get('title')}\n链接: {r.get('url')}\n摘要: {r.get('snippet')}\n" for r in results]
        return "\n---\n".join(formatted)

    return create_agent(
        model=llm,
        tools=[search_web],
        middleware=[SearchAgentMiddleware(max_steps=max_steps, bilingual=bilingual, include_year=include_year)],
        name="search_react",
    )
