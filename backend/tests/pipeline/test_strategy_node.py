import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage

from backend.pipeline.state import create_initial_state
from backend.pipeline.nodes.strategy import strategy_planner_node

@pytest.mark.asyncio
async def test_strategy_planner_hard_intercept():
    """测试硬性拦截：社交辞令应直接进入 fast_react"""
    state = create_initial_state(query="你好", research_id="res_1", tenant_id="t1")
    config = RunnableConfig(configurable={})
    
    updates = []
    async for chunk in strategy_planner_node(state, config):
        updates.append(chunk)
        
    result = updates[-1]
    assert result["control"]["execution_mode"] == "fast_react"
    assert "检测到简单社交" in result["output"]["diagnostics"]["thought_steps"][0]["new_sub_step"]["message"]

@pytest.mark.asyncio
async def test_strategy_planner_ui_override():
    """测试 UI 覆盖：如果 state 已指定模式，则跳过 AI 规划"""
    state = create_initial_state(query="深度分析 iPhone 16", research_id="res_1", tenant_id="t1")
    state["control"]["execution_mode"] = "expert_search"
    config = RunnableConfig(configurable={})
    
    updates = []
    async for chunk in strategy_planner_node(state, config):
        updates.append(chunk)
        
    # 如果模式已指定，节点应输出根据该模式派生的 strategy_overrides
    assert len(updates) == 1
    assert "runtime" in updates[0]
    assert updates[0]["runtime"]["pipeline"]["strategy_overrides"]["verification_level"] == "standard"

@pytest.mark.asyncio
async def test_strategy_planner_ai_decision():
    """测试 AI 决策逻辑"""
    state = create_initial_state(query="对比特斯拉和小米汽车", research_id="res_1", tenant_id="t1", speed="research_pipeline")
    config = RunnableConfig(configurable={"preset_id": "p1", "db": MagicMock()})
    
    mock_llm_response = AIMessage(content='''{
        "execution_mode": "research_pipeline"
    }''')
    
    with patch("backend.pipeline.nodes.strategy.get_llm_for_stage", AsyncMock(return_value=MagicMock(ainvoke=AsyncMock(return_value=mock_llm_response)))), \
         patch("backend.pipeline.nodes.strategy._load_preset_business", AsyncMock(return_value={})), \
         patch("backend.pipeline.nodes.strategy.get_node_config", AsyncMock(return_value={}), create=True):
        
        updates = []
        async for chunk in strategy_planner_node(state, config):
            updates.append(chunk)
            
        result = updates[-1]
        assert result["control"]["execution_mode"] == "research_pipeline"
        # 应该直接加载 research_pipeline 的静态 profile 属性，因为已废除 AI 动态调参
        assert result["runtime"]["pipeline"]["strategy_overrides"]["max_dimensions"] == {"min": 3, "max": 6}
        assert result["runtime"]["pipeline"]["strategy_overrides"]["verification_level"] == "strict"

@pytest.mark.asyncio
async def test_strategy_planner_preset_merge():
    """测试在指定静态直通模式时，策略节点合并 Preset 业务参数的优先级逻辑"""
    state = create_initial_state(query="深度分析 iPhone 16", research_id="res_1", tenant_id="t1")
    state["control"]["execution_mode"] = "fast_react"
    
    # 自定义配置：微调 fast_react 的参数，比如 max_results_per_query=5 (默认 profile 是 3)
    preset_business = {
        "max_results_per_query": 5,
        "verification_level": "standard", # 强制覆盖 skip
    }
    
    config = RunnableConfig(configurable={"preset_id": "p1", "db": MagicMock()})
    
    with patch("backend.pipeline.nodes.strategy._load_preset_business", AsyncMock(return_value=preset_business)):
        updates = []
        async for chunk in strategy_planner_node(state, config):
            updates.append(chunk)
            
        result = updates[-1]
        assert result["control"]["execution_mode"] == "fast_react"
        overrides = result["runtime"]["pipeline"]["strategy_overrides"]
        # 验证 Preset 显式指定参数成功合并与覆盖
        assert overrides["max_results_per_query"] == 5
        assert overrides["verification_level"] == "standard"
        # 验证缺省参数成功从 fast_react 静态 Profile 兜底补充
        assert overrides["max_search_rounds"] == 1  # fast_react 默认 max_search_rounds
        assert overrides["max_dimensions"] == 2      # fast_react 默认 intent_max_dimensions


