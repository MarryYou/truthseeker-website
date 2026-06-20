"""测试不同 Speed Profiles 对管线参数的覆盖逻辑。"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from backend.pipeline.state import create_initial_state
from backend.pipeline.nodes.intent import intent_node
from backend.pipeline.nodes.strategy import strategy_planner_node


@pytest.mark.asyncio
async def test_strategy_planner_speed_aware():
    """测试 strategy_planner_node 是否能感知 speed 级别并正确输出 strategy_overrides"""
    state = create_initial_state(
        query="iPhone 16 详情",
        research_id="r1",
        tenant_id="t1",
        speed="fast_react"
    )
    
    config = RunnableConfig(configurable={"preset_id": "p1", "db": MagicMock()})
    
    # Mock LLM 返回 execution_mode
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
        assert result["runtime"]["pipeline"]["strategy_overrides"]["max_dimensions"] == {"min": 3, "max": 6}
        assert result["runtime"]["pipeline"]["strategy_overrides"]["verification_level"] == "strict"


@pytest.mark.asyncio
async def test_intent_node_uses_speed_profile():
    """测试 intent_node 在无 overrides 时是否正确从 SPEED_PROFILES 读取基准值"""
    # 设置 speed = "fast_react"，预期 intent_max_dimensions = 2 (根据 constants.py)
    state = create_initial_state(
        query="测试",
        research_id="r1",
        tenant_id="t1",
        speed="fast_react"
    )
    
    mock_llm = MagicMock()
    # 返回 5 个维度，看 intent_node 是否会按 fast profile (max=2) 截断
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content='''{
        "intent_type": "explore",
        "dimensions": ["D1", "D2", "D3", "D4", "D5"],
        "keywords": []
    }'''))
    
    config = RunnableConfig(configurable={})
    
    with patch("backend.pipeline.nodes.intent.get_llm_for_stage", AsyncMock(return_value=mock_llm)), \
         patch("backend.pipeline.nodes.intent.get_node_config", AsyncMock(return_value={"max_dimensions": 10}), create=True), \
         patch("backend.pipeline.nodes.intent._load_preset_business", AsyncMock(return_value={}), create=True):
        
        updates = []
        async for chunk in intent_node(state, config):
            updates.append(chunk)
            
        result = updates[-1]
        # fast profile 的 intent_max_dimensions 是 2
        assert len(result["runtime"]["pipeline"]["dimensions"]) == 2
