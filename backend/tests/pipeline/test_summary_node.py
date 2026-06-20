import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage

from backend.pipeline.state import create_initial_state
from backend.pipeline.nodes.summary import summary_node

@pytest.mark.asyncio
async def test_summary_node_success():
    """测试总结节点成功生成摘要"""
    state = create_initial_state(query="iPhone 16 什么时候发布？", research_id="res_1", tenant_id="t1")
    state["output"]["pipeline"]["report_prompt"] = "iPhone 16 预计在 2024 年 9 月发布。搭载 A18 芯片。"
    
    mock_llm_response = AIMessage(content="iPhone 16 将于 2024 年 9 月发布，搭载 A18 芯片。")
    
    with patch("backend.pipeline.nodes.summary.get_llm_for_stage", AsyncMock(return_value=MagicMock(ainvoke=AsyncMock(return_value=mock_llm_response)))):
        result = await summary_node(state, RunnableConfig(configurable={}))
        
        assert "history_summary" in result.get("memory", {})
        assert "2024" in result["memory"]["history_summary"]

@pytest.mark.asyncio
async def test_summary_node_empty_answer():
    """测试当无回答内容时跳过总结"""
    state = create_initial_state(query="测试", research_id="res_1", tenant_id="t1")
    state["output"]["pipeline"]["report_prompt"] = ""
    
    result = await summary_node(state, RunnableConfig(configurable={}))
    assert result == {}

@pytest.mark.asyncio
async def test_summary_node_exception_fallback():
    """测试异常时的兜底逻辑"""
    state = create_initial_state(query="复杂问题", research_id="res_1", tenant_id="t1")
    state["output"]["pipeline"]["report_prompt"] = "很多内容..."
    
    with patch("backend.pipeline.nodes.summary.get_llm_for_stage", AsyncMock(side_effect=RuntimeError("LLM error"))):
        result = await summary_node(state, RunnableConfig(configurable={}))
        assert "history_summary" in result.get("memory", {})
        assert "关于 复杂问题 的讨论" in result["memory"]["history_summary"]
