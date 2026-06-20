import pytest
from unittest.mock import AsyncMock, patch
from langchain_core.messages import AIMessage, ToolMessage
from backend.pipeline.state import create_initial_state
from backend.pipeline.graph import compile_graph, _route_after_verify


def test_state_initialization():
    """测试初始状态工厂方法生成的 ResearchState 是否属性齐备且默认值正确"""
    state = create_initial_state(
        query="is anti-gravity real?",
        research_id="research-abc",
        tenant_id="tenant-123"
    )
    
    assert state["runtime"]["shared"]["query"] == "is anti-gravity real?"
    assert state["context"]["research_id"] == "research-abc"
    assert state["context"]["tenant_id"] == "tenant-123"
    assert state["runtime"]["pipeline"]["search_round"] == 0
    assert state["runtime"]["pipeline"]["search_strategy"] == "broad"
    assert state["output"]["diagnostics"]["error_log"] == []
    assert state["output"]["diagnostics"]["store_refs"] == {}


def test_route_after_verify_logic():
    """测试验证完毕后的条件边路由逻辑"""
    # 场景 1: 有矛盾维度，且未超轮次上限 -> 回退补充搜索 (search_more)
    state_conflict = {
        "control": {"speed": "research_pipeline"},
        "runtime": {
            "pipeline": {
                "conflict_dimensions": ["physics_laws"],
                "search_round": 1,
                "strategy_overrides": {"max_search_rounds": 3}
            }
        }
    }
    assert _route_after_verify(state_conflict) == "search_more"
    
    # 场景 2: 有矛盾，但轮次已达上限 -> 只能强制进入报告 (report)
    state_limit = {
        "control": {"speed": "research_pipeline"},
        "runtime": {
            "pipeline": {
                "conflict_dimensions": ["physics_laws"],
                "search_round": 2,
                "strategy_overrides": {"max_search_rounds": 2}
            }
        }
    }
    assert _route_after_verify(state_limit) == "report"
    
    # 场景 3: 无矛盾维度 -> 直接前往撰写报告 (report)
    state_no_conflict = {
        "control": {"speed": "research_pipeline"},
        "runtime": {
            "pipeline": {
                "conflict_dimensions": [],
                "search_round": 1,
                "strategy_overrides": {"max_search_rounds": 3}
            }
        }
    }
    assert _route_after_verify(state_no_conflict) == "report"


def test_graph_compiles_successfully():
    """测试管线图成功 build 并 compile"""
    compiled_g = compile_graph()
    assert compiled_g is not None
    
    # 验证关键节点均被正确注册
    nodes = compiled_g.nodes
    assert "intent_analyze" in nodes
    assert "search_react" in nodes
    assert "coarse_filter" in nodes
    assert "llm_filter" in nodes
    assert "cross_verify" in nodes
    assert "generate_report_prompt" in nodes


@pytest.mark.asyncio
async def test_search_react_wrapper_node_valuable_urls():
    from backend.pipeline.graph import search_react_wrapper_node
    
    state = create_initial_state(
        query="反重力",
        research_id="res_1",
        tenant_id="tenant_1"
    )
    
    # Mock subgraph output messages
    # 包含 fetch_full_content 工具调用，以及最终 AIMessage 内容里引用的 URL
    mock_messages = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "fetch_full_content",
                "args": {"url": "https://example.com/fetched1"},
                "id": "tc1"
            }]
        ),
        ToolMessage(content="content1", tool_call_id="tc1"),
        AIMessage(
            content="根据研究，有些内容引用自 https://example.com/referenced1。 谢谢！"
        )
    ]
    
    mock_subgraph_output = {
        "messages": mock_messages,
        "searched_keywords_history": ["keyword1"],
        "thought_steps": [{"step": "step1"}]
    }
    
    mock_subgraph = AsyncMock()
    mock_subgraph.ainvoke = AsyncMock(return_value=mock_subgraph_output)
    
    with patch("backend.pipeline.graph.search_react_subgraph", mock_subgraph):
        res = await search_react_wrapper_node(state, {})
        
        # 验证 valuable_urls 提取出 fetched_urls + referenced_urls 后的结果
        valuable_urls = res["runtime"]["pipeline"]["valuable_urls"]
        assert "https://example.com/fetched1" in valuable_urls
        assert "https://example.com/referenced1" in valuable_urls
        assert len(valuable_urls) == 2
