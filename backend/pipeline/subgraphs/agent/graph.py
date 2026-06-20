"""Agent 子图 — 使用 LangChain create_agent + middleware 实现"""
from __future__ import annotations
from typing import Any
from langchain.agents import create_agent
from langchain_core.tools import tool
from backend.search.orchestrator import SearchOrchestrator
from backend.core.logging import logger
from backend.db.store import ResearchStore
from backend.db.engine import async_session
from .middleware import ResearchAgentMiddleware


def build_agent(
    llm: Any,
    raw_store: Any,
    tenant_id: str,
    user_id: str,
    research_id: str,
    task_id: str,
    preset_id: str | None,
    execution_mode: str,
    query: str,
    suggested_engines: list[str] | None = None,
    max_results_per_query: int = 5,
    rate_limit_delay: float = 0.5,
    max_rounds: int = 3,
):
    """构建 create_agent 实例（含工具和中间件）"""
    engines = suggested_engines if isinstance(suggested_engines, list) and suggested_engines else ["tavily", "bocha"]

    max_steps = max_rounds + 2

    @tool
    async def search_web(query: str, count: int | None = None) -> str:
        """在互联网上搜索最新信息。当需要获取实时、准确的信息时使用。"""
        effective_count = min(max(1, count or max_results_per_query), max_results_per_query)
        async with async_session() as session:
            orchestrator = SearchOrchestrator(session, tenant_id, user_id)
            results = await orchestrator.search(
                query=query,
                engines=engines,
                preset_id=preset_id,
                max_results_per_query=effective_count,
                rate_limit_delay=rate_limit_delay,
            )
            if not results:
                return "未找到相关搜索结果。"
            try:
                store = ResearchStore(raw_store, tenant_id=tenant_id, research_id=research_id, task_id=task_id)
                await store.save_search_results(query, results)
            except Exception as e:
                logger.error("搜索结果落库失败 | error={}", e)
        formatted = [f"标题: {r.get('title')}\n链接: {r.get('url')}\n摘要: {r.get('snippet')}\n" for r in results]
        return "\n---\n".join(formatted)

    @tool
    async def answer_directly() -> str:
        """直接回答用户的问题，无需搜索。适用于常识、定义、解释、闲聊、感谢、问候等不需要实时信息的场景。"""
        return "direct_answer"

    tools = [search_web, answer_directly]

    return create_agent(
        model=llm,
        tools=tools,
        middleware=[ResearchAgentMiddleware(execution_mode=execution_mode, query=query, max_steps=max_steps)],
        name="truthseeker_agent",
    )
