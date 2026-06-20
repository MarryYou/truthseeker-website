"""测试 coarse_filter_node + llm_filter_node 两阶段筛选流程。"""
from __future__ import annotations
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from langgraph.store.memory import InMemoryStore
from backend.pipeline.state import create_initial_state
from backend.pipeline.nodes.filter import coarse_filter_node, llm_filter_node
from backend.db.store import ResearchStore


@pytest.mark.asyncio
async def test_filter_basic_flow():
    search_data = [
        {"title": "Valid Web", "url": "https://example.com/1", "content": "Useful info about gravity", "relevance_score": 0.8},
        {"title": "Low Score Web", "url": "https://example.com/2", "content": "Irrelevant text", "relevance_score": 0.1},
        {"title": "Another Valid Web", "url": "https://example.com/3", "content": "More useful facts", "relevance_score": 0.7},
    ]

    state = create_initial_state(query="反重力装置", research_id="res_1", tenant_id="tenant_1")
    state["runtime"]["shared"]["intent_type"] = "verify"

    raw_store = InMemoryStore()
    rs = ResearchStore(raw_store, tenant_id="tenant_1", research_id="res_1")
    await rs.save_search_results("round_0", [search_data[0], search_data[1]])
    await rs.save_search_results("round_1", [search_data[2]])

    config = {
        "configurable": {"tenant_id": "tenant_1", "research_id": "res_1", "store": raw_store}
    }

    # ---- Phase 1: coarse_filter ----
    with patch("backend.pipeline.nodes.filter.get_node_config", AsyncMock(return_value={
        "min_relevance_score": 0.35,
    })):
        async for chunk in coarse_filter_node(state, config):
            if "runtime" in chunk:
                state["runtime"]["pipeline"]["_filter_candidates"] = chunk["runtime"]["pipeline"]["_filter_candidates"]
                state["runtime"]["pipeline"]["_filter_cached"] = chunk["runtime"]["pipeline"].get("_filter_cached", [])

    # ---- Phase 2: llm_filter ----
    mock_llm_response = MagicMock()
    mock_llm_response.content = '''[
        {"index": 0, "keep": true, "reason": "很有用", "summary": "重力实验信息"},
        {"index": 2, "keep": true, "reason": "数据详实", "summary": "更多研究事实"}
    ]'''
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)

    distinct_vectors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

    # Need to patch at the FilterService / filter_service module level
    from backend.pipeline.nodes.filter import logger as flog  # noqa

    with patch("backend.services.filter_service.get_llm_for_stage", AsyncMock(return_value=mock_llm)), \
         patch("backend.services.filter_service.embed_documents_with_preset", AsyncMock(return_value=distinct_vectors)), \
         patch("backend.pipeline.nodes.filter.get_node_config", AsyncMock(return_value={
             "batch_concurrency": 10, "dedup_similarity": 0.85,
         })):
        result = None
        async for chunk in llm_filter_node(state, config):
            if "output" in chunk and "diagnostics" in chunk["output"]:
                result = chunk

        assert result["output"]["diagnostics"]["store_refs"] == {"filtered": "final"}

        filtered_results = await rs.load_filtered_results("final")
        assert len(filtered_results) == 2
        urls = {item["url"] for item in filtered_results}
        assert "https://example.com/2" not in urls

        item_1 = next(item for item in filtered_results if item["url"] == "https://example.com/1")
        assert item_1["keep_reason"] == "很有用"


@pytest.mark.asyncio
async def test_filter_no_candidates():
    state = create_initial_state(query="反重力", research_id="res_2", tenant_id="tenant_1")

    raw_store = InMemoryStore()
    rs = ResearchStore(raw_store, tenant_id="tenant_1", research_id="res_2")
    await rs.save_search_results("round_0", [
        {"title": "Low 1", "url": "https://example.com/1", "relevance_score": 0.1}
    ])

    config = {
        "configurable": {"tenant_id": "tenant_1", "research_id": "res_2", "store": raw_store}
    }

    with patch("backend.pipeline.nodes.filter.get_node_config", AsyncMock(return_value={"min_relevance_score": 0.35})):
        async for chunk in coarse_filter_node(state, config):
            if "output" in chunk and "diagnostics" in chunk["output"]:
                pass

        assert await rs.load_filtered_results("final") == []


@pytest.mark.asyncio
async def test_filter_with_valuable_urls():
    search_data = [
        {"title": "Valuable Web", "url": "https://example.com/valuable", "content": "Useful info", "relevance_score": 0.8},
        {"title": "Not Valuable Web", "url": "https://example.com/not_valuable", "content": "Other info", "relevance_score": 0.9},
    ]

    state = create_initial_state(query="反重力装置", research_id="res_3", tenant_id="tenant_1")
    state["runtime"]["shared"]["intent_type"] = "verify"
    state["runtime"]["pipeline"]["valuable_urls"] = ["https://example.com/valuable"]

    raw_store = InMemoryStore()
    rs = ResearchStore(raw_store, tenant_id="tenant_1", research_id="res_3")
    await rs.save_search_results("round_0", search_data)

    config = {
        "configurable": {"tenant_id": "tenant_1", "research_id": "res_3", "store": raw_store}
    }

    with patch("backend.pipeline.nodes.filter.get_node_config", AsyncMock(return_value={
        "min_relevance_score": 0.35,
    })):
        async for chunk in coarse_filter_node(state, config):
            if "runtime" in chunk:
                state["runtime"]["pipeline"]["_filter_candidates"] = chunk["runtime"]["pipeline"]["_filter_candidates"]
                state["runtime"]["pipeline"]["_filter_cached"] = chunk["runtime"]["pipeline"].get("_filter_cached", [])

    mock_llm_response = MagicMock()
    mock_llm_response.content = '''[
        {"index": 0, "keep": true, "reason": "很有用", "summary": "重力实验信息"}
    ]'''
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)

    with patch("backend.services.filter_service.get_llm_for_stage", AsyncMock(return_value=mock_llm)), \
         patch("backend.services.filter_service.embed_documents_with_preset", AsyncMock(return_value=[[1.0, 0.0, 0.0]])), \
         patch("backend.pipeline.nodes.filter.get_node_config", AsyncMock(return_value={
             "batch_concurrency": 10, "dedup_similarity": 0.85,
         })):
        async for chunk in llm_filter_node(state, config):
            pass

        filtered_results = await rs.load_filtered_results("final")
        assert len(filtered_results) == 1
        assert filtered_results[0]["url"] == "https://example.com/valuable"


@pytest.mark.asyncio
async def test_filter_valuable_urls_fallback():
    search_data = [
        {"title": "Web 1", "url": "https://example.com/1", "content": "Useful info 1", "relevance_score": 0.8},
        {"title": "Web 2", "url": "https://example.com/2", "content": "Useful info 2", "relevance_score": 0.7},
    ]

    state = create_initial_state(query="反重力装置", research_id="res_4", tenant_id="tenant_1")
    state["runtime"]["shared"]["intent_type"] = "verify"
    state["runtime"]["pipeline"]["valuable_urls"] = ["https://example.com/unrelated"]

    raw_store = InMemoryStore()
    rs = ResearchStore(raw_store, tenant_id="tenant_1", research_id="res_4")
    await rs.save_search_results("round_0", search_data)

    config = {
        "configurable": {"tenant_id": "tenant_1", "research_id": "res_4", "store": raw_store}
    }

    with patch("backend.pipeline.nodes.filter.get_node_config", AsyncMock(return_value={
        "min_relevance_score": 0.35,
    })):
        async for chunk in coarse_filter_node(state, config):
            if "runtime" in chunk:
                state["runtime"]["pipeline"]["_filter_candidates"] = chunk["runtime"]["pipeline"]["_filter_candidates"]
                state["runtime"]["pipeline"]["_filter_cached"] = chunk["runtime"]["pipeline"].get("_filter_cached", [])

    mock_llm_response = MagicMock()
    mock_llm_response.content = '''[
        {"index": 0, "keep": true, "reason": "1有用", "summary": "信息1"},
        {"index": 1, "keep": true, "reason": "2有用", "summary": "信息2"}
    ]'''
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)

    with patch("backend.services.filter_service.get_llm_for_stage", AsyncMock(return_value=mock_llm)), \
         patch("backend.services.filter_service.embed_documents_with_preset", AsyncMock(return_value=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])), \
         patch("backend.pipeline.nodes.filter.get_node_config", AsyncMock(return_value={
             "batch_concurrency": 10, "dedup_similarity": 0.85,
         })):
        async for chunk in llm_filter_node(state, config):
            pass

        filtered_results = await rs.load_filtered_results("final")
        assert len(filtered_results) == 2
        urls = {item["url"] for item in filtered_results}
        assert urls == {"https://example.com/1", "https://example.com/2"}
