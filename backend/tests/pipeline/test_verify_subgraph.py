"""测试 verify 子图的各个节点及子图整体运行流。"""
from __future__ import annotations
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore

from backend.pipeline.subgraphs.verify.state import VerifyState
from backend.pipeline.subgraphs.verify.atomize import atomize_node
from backend.pipeline.subgraphs.verify.profile import profile_node
from backend.pipeline.subgraphs.verify.tripartite import tripartite_node
from backend.pipeline.subgraphs.verify.arbitrate import arbitrate_node
from backend.pipeline.subgraphs.verify.graph import verify_subgraph
from backend.db.store import ResearchStore


def _make_config(raw_store, tenant_id="tenant_1", research_id="res_1", user_id="user_1", preset_id="preset_1"):
    return {
        "configurable": {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "research_id": research_id,
            "preset_id": preset_id,
            "store": raw_store,
        }
    }


# ── 1. 测试 atomize_node ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_atomize_node_basic():
    raw_store = InMemoryStore()
    rs = ResearchStore(raw_store, tenant_id="tenant_1", research_id="res_1")
    await rs.save_filtered_results("final", [
        {"title": "网页A", "url": "https://a.com", "summary": "事实A描述", "dimension": "维度1"},
        {"title": "网页B", "url": "https://b.com", "summary": "事实B描述", "dimension": "维度1"},
    ])

    state: VerifyState = {
        "query": "测试查询",
        "dimensions": ["维度1", "维度2"], # 维度2完全缺失
        "tenant_id": "tenant_1",
        "user_id": "user_1",
    }

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="""{
        "claims": [
                {"text": "提取出的声明1", "importance": "primary", "source_indices": [0]},
                {"text": "提取出的声明2", "importance": "secondary", "source_indices": [1]}
            ]
        }"""))

    with patch("backend.pipeline.subgraphs.verify.atomize.get_llm_for_stage", AsyncMock(return_value=mock_llm)):
        updates = []
        async for chunk in atomize_node(state, _make_config(raw_store)):
            updates.append(chunk)
        result = updates[-1]

    # 维度2缺失，应在 insufficient_dimensions 中
    assert "维度2" in result["insufficient_dimensions"]
    assert len(result["claims"]) == 2
    assert result["claims"][0]["source_url"] == "https://a.com"
    assert result["claims"][1]["source_url"] == "https://b.com"
    assert result["claims"][0]["dimension"] == "维度1"


# ── 2. 测试 profile_node ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_profile_node_heuristics_and_llm():
    raw_store = InMemoryStore()
    state: VerifyState = {
        "_filtered_items": [
            # 域名高置信，不应走 LLM (gov=0.9 >= 0.75)
            {"url": "https://navy.mil", "pub_date": "2025-01-01T00:00:00Z", "summary": "官方声明"},
            # 域名低置信，走 LLM (com=0.6 < 0.75)
            {"url": "https://badcom.com", "pub_date": "2025-01-01T00:00:00Z", "summary": "商业宣传宣传"},
        ],
        "tenant_id": "tenant_1",
        "user_id": "user_1",
        "verification_level": "strict"
    }

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="""[
        {
            "index": 0,
            "content_quality": 0.3,
            "has_marketing_tone": true,
            "has_expert_evidence": false
        }
    ]"""))

    with patch("backend.pipeline.subgraphs.verify.profile.get_llm_for_stage", AsyncMock(return_value=mock_llm)), \
         patch("backend.pipeline.subgraphs.verify.profile.get_node_config", AsyncMock(return_value={})):
        updates = []
        async for chunk in profile_node(state, _make_config(raw_store)):
            updates.append(chunk)
        result = updates[-1]

    profiles = result["source_profiles"]
    assert len(profiles) == 2

    # 验证政府网直接启发式评分 (base=0.9)
    assert profiles["https://navy.mil"]["llm_assessed"] is False
    assert profiles["https://navy.mil"]["domain_score"] >= 0.9

    # 验证商业网走 LLM 评估且获得 marketing 标记
    assert profiles["https://badcom.com"]["llm_assessed"] is True
    assert profiles["https://badcom.com"]["content_quality"] == 0.3
    assert profiles["https://badcom.com"]["has_marketing_tone"] is True


# ── 3. 测试 tripartite_node ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tripartite_node_flow():
    state: VerifyState = {
        "query": "测试",
        "claims": [
            # 正常需跨源校验
            {"text": "事实A", "importance": "primary", "source_url": "https://a.com", "dimension": "维度1"},
            # 单信源，应直接标 single_source
            {"text": "事实B", "importance": "secondary", "source_url": "https://b.com", "dimension": "维度2"},
            # indirect，应跳过跨源校验
            {"text": "背景事实", "importance": "indirect", "source_url": "https://c.com", "dimension": "维度3"},
        ],
        "_filtered_items": [
            {"url": "https://a.com", "summary": "证据1", "dimension": "维度1"},
            {"url": "https://other.com", "summary": "证据2", "dimension": "维度1"},
            {"url": "https://b.com", "summary": "单一证据", "dimension": "维度2"},
        ],
        "source_profiles": {
            "https://a.com": {"credibility": 0.8},
            "https://other.com": {"credibility": 0.7},
            "https://b.com": {"credibility": 0.6},
        },
        "tenant_id": "tenant_1",
        "user_id": "user_1",
    }

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="""{
        "verdict": "consistent",
        "citation_confidence": 0.9,
        "consistency_score": 0.95,
        "conflicts": [],
        "reasoning": "非常一致"
    }"""))

    with patch("backend.pipeline.subgraphs.verify.tripartite.get_llm_for_stage", AsyncMock(return_value=mock_llm)), \
         patch("backend.pipeline.subgraphs.verify.tripartite.get_node_config", AsyncMock(return_value={})):
        updates = []
        async for chunk in tripartite_node(state, {}):
            updates.append(chunk)
        result = updates[-1]

    claims = result["claims"]
    assert len(claims) == 3

    # 验证1 (事实A)：走了 LLM，verdict 为 consistent
    claim_a = next(c for c in claims if c["text"] == "事实A")
    assert claim_a["verdict"] == "consistent"
    assert claim_a["consistency_score"] == 0.95


# ── 4. 测试 arbitrate_node ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_arbitrate_node_flow():
    raw_store = InMemoryStore()
    state: VerifyState = {
        "claims": [
            {"text": "A", "dimension": "维度1", "importance": "primary", "verdict": "contradictory", "consistency_score": 0.1},
            {"text": "B", "dimension": "维度2", "importance": "primary", "verdict": "consistent", "consistency_score": 1.0},
            {"text": "C", "dimension": "维度2", "importance": "secondary", "verdict": "mostly_consistent", "consistency_score": 0.8},
        ],
        "dimensions": ["维度1", "维度2", "维度3"], # 维度3缺失
        "insufficient_dimensions": ["维度3"],
        "store_refs": {},
        "tenant_id": "tenant_1",
        "research_id": "res_1"
    }

    updates = []
    async for chunk in arbitrate_node(state, _make_config(raw_store)):
        updates.append(chunk)
    result = updates[-1]

    assert "conflict_dimensions" in result
    assert "overall_confidence" in result


# ── 5. 测试 verify_subgraph 整体运行（集成测试） ─────────────────────────────

@pytest.mark.asyncio
async def test_verify_subgraph_integration():
    raw_store = InMemoryStore()
    rs = ResearchStore(raw_store, tenant_id="tenant_1", research_id="res_1")
    await rs.save_filtered_results("final", [
        {"title": "新华网报道", "url": "https://xinhua.net", "summary": "量子计算获得新突破，时速非常快", "dimension": "性能"},
        {"title": "某商业博客", "url": "https://com-blog.com", "summary": "量子计算速度飞快", "dimension": "性能"},
    ])

    initial_state = VerifyState(
        query="量子计算进展",
        dimensions=["性能", "成本"],
        tenant_id="tenant_1",
        user_id="user_1",
        store_refs={},
        verification_level="strict"
    )

    # Mock atomize LLM
    mock_atomize_llm = MagicMock()
    mock_atomize_llm.ainvoke = AsyncMock(return_value=AIMessage(content="""{
        "claims": [
            {"text": "量子计算突破", "importance": "primary", "source_indices": [0]},
            {"text": "量子计算速度快", "importance": "secondary", "source_indices": [1]}
        ]
    }"""))

    # Mock profile LLM
    mock_profile_llm = MagicMock()
    mock_profile_llm.ainvoke = AsyncMock(return_value=AIMessage(content="""[
        {
            "index": 1,
            "content_quality": 0.6,
            "has_marketing_tone": false,
            "has_expert_evidence": true
        }
    ]"""))

    # Mock tripartite LLM
    mock_tripartite_llm = MagicMock()
    mock_tripartite_llm.ainvoke = AsyncMock(return_value=AIMessage(content="""{
        "verdict": "consistent",
        "citation_confidence": 0.9,
        "consistency_score": 0.95,
        "conflicts": [],
        "reasoning": "信源均支持该陈述"
    }"""))

    with patch("backend.pipeline.subgraphs.verify.atomize.get_llm_for_stage", AsyncMock(return_value=mock_atomize_llm)), \
         patch("backend.pipeline.subgraphs.verify.profile.get_llm_for_stage", AsyncMock(return_value=mock_profile_llm)), \
         patch("backend.pipeline.subgraphs.verify.tripartite.get_llm_for_stage", AsyncMock(return_value=mock_tripartite_llm)), \
         patch("backend.pipeline.subgraphs.verify.profile.get_node_config", AsyncMock(return_value={})), \
         patch("backend.pipeline.subgraphs.verify.tripartite.get_node_config", AsyncMock(return_value={})):
        
        final_state = await verify_subgraph.ainvoke(initial_state, _make_config(raw_store))

    assert "overall_confidence" in final_state


def test_safe_float():
    from backend.pipeline.subgraphs.verify.tripartite import _safe_float
    assert _safe_float(None, 0.5) == 0.5
    assert _safe_float(0.85, 0.5) == 0.85
    assert _safe_float("0.85", 0.5) == 0.85
    assert _safe_float("0.0-1.0", 0.5) == 0.5
    assert _safe_float("0.85 (based on 3 sources)", 0.5) == 0.85
    assert _safe_float("85%", 0.5) == 0.85
    assert _safe_float("90", 0.5) == 0.90
    assert _safe_float("invalid text", 0.5) == 0.5
