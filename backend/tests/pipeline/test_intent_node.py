"""测试 intent_node 的分析与去重功能。"""
from __future__ import annotations
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from langchain_core.messages import AIMessage

from backend.pipeline.state import create_initial_state
from backend.pipeline.nodes.intent import intent_node


@pytest.mark.asyncio
async def test_intent_node_new_research():
    # 模拟新研究场景下的意图分析
    state = create_initial_state(
        query="反重力是否真实存在？",
        research_id="res_123",
        tenant_id="tenant_abc",
        user_id="user_123",
        preset_id="preset_123"
    )
    
    config = {
        "configurable": {
            "tenant_id": "tenant_abc",
            "user_id": "user_123",
            "research_id": "res_123",
            "preset_id": "preset_123"
        }
    }
    
    mock_llm_response = AIMessage(
        content='''{
            "intent_type": "verify",
            "search_plan": "查找关于反重力实验和理论的科学文献",
            "dimensions": ["物理学原理", "实验证据", "学术界共识"]
        }'''
    )
    
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)
    
    mock_db = MagicMock()
    mock_db.get = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.pipeline.nodes.intent.get_llm_for_stage", AsyncMock(return_value=mock_llm)), \
         patch("backend.db.engine.async_session", return_value=mock_session), \
         patch("backend.pipeline.nodes.intent.get_node_config", AsyncMock(return_value={"max_dimensions": 4}), create=True), \
         patch("backend.pipeline.nodes.intent._load_preset_business", AsyncMock(return_value={"allow_ai_override": True}), create=True):
        
        updates = []
        async for chunk in intent_node(state, config):
            updates.append(chunk)
            
        # 最后一轮更新应该包含核心逻辑产出
        result = updates[-1]
        
        assert result["runtime"]["shared"]["intent_type"] == "verify"
        assert "物理学原理" in result["runtime"]["pipeline"]["dimensions"]
        assert len(result["runtime"]["pipeline"]["dimensions"]) == 3


@pytest.mark.asyncio
async def test_intent_node_follow_up_dedup():
    # 模拟追问场景下的增量维度向量去重
    state = create_initial_state(
        query="那超导现象呢？",
        research_id="res_123",
        tenant_id="tenant_abc",
        user_id="user_123",
        preset_id="preset_123",
        context_mode="follow_up",
        last_research_summary="之前研究了反重力的实验证据",
        last_research_dimensions=["物理学原理", "实验证据"]
    )
    
    config = {
        "configurable": {
            "tenant_id": "tenant_abc",
            "user_id": "user_123",
            "research_id": "res_123",
            "preset_id": "preset_123"
        }
    }
    
    mock_llm_response = AIMessage(
        content='''{
            "intent_type": "compare",
            "search_plan": "对比超导和反重力机制",
            "keep_dimensions": ["物理学原理", "实验证据"],
            "new_dimensions": ["物理学机制", "实验验证", "超导应用"],
            "dedup_intensity": "standard"
        }'''
    )
    
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)
    
    mock_vectors = [
        [1.0, 0.0, 0.0],  # 物理学原理
        [0.0, 1.0, 0.0],  # 实验证据
        [0.99, 0.0, 0.0], # 物理学机制 (与第一个余弦相似度 ~0.99)
        [0.0, 0.98, 0.0], # 实验验证 (与第二个相似度 ~0.98)
        [0.0, 0.0, 1.0],  # 超导应用 (全新)
    ]
    
    mock_db = MagicMock()
    mock_db.get = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.pipeline.nodes.intent.get_llm_for_stage", AsyncMock(return_value=mock_llm)), \
         patch("backend.db.engine.async_session", return_value=mock_session), \
         patch("backend.pipeline.nodes.intent.get_node_config", AsyncMock(return_value={"max_dimensions": 4}), create=True), \
         patch("backend.pipeline.nodes.intent.embed_documents_with_preset", AsyncMock(return_value=mock_vectors)), \
         patch("backend.pipeline.nodes.intent._load_preset_business", AsyncMock(return_value={"allow_ai_override": True}), create=True):
        
        updates = []
        async for chunk in intent_node(state, config):
            updates.append(chunk)
            
        result = updates[-1]
        
        assert result["runtime"]["shared"]["intent_type"] == "compare"
        assert len(result["runtime"]["pipeline"]["dimensions"]) == 3
        assert "超导应用" in result["runtime"]["pipeline"]["dimensions"]
        assert "物理学机制" not in result["runtime"]["pipeline"]["dimensions"]


@pytest.mark.asyncio
async def test_intent_node_exception_handling():
    # 模拟异常发生时的优雅退化
    state = create_initial_state(
        query="异常测试",
        research_id="res_123",
        tenant_id="tenant_abc"
    )
    
    config = {
        "configurable": {
            "tenant_id": "tenant_abc",
            "research_id": "res_123"
        }
    }
    
    mock_db = MagicMock()
    mock_db.get = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.pipeline.nodes.intent.get_llm_for_stage", AsyncMock(side_effect=RuntimeError("LLM offline"))), \
         patch("backend.db.engine.async_session", return_value=mock_session), \
         patch("backend.pipeline.nodes.intent.get_node_config", AsyncMock(return_value={"max_dimensions": 4}), create=True):
        
        updates = []
        async for chunk in intent_node(state, config):
            updates.append(chunk)
            
        # 异常链路收集 updates
        result = {}
        for u in updates:
            # 简单合并嵌套的 dict
            for k, v in u.items():
                if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                    result[k].update(v)
                else:
                    result[k] = v
            
        # 应该退化为默认探查状态
        assert result["runtime"]["shared"]["intent_type"] == "explore"
        assert result["runtime"]["pipeline"]["dimensions"] == ["一般信息"]
        assert "output" in result
        assert result["output"]["diagnostics"]["error_log"][0].node == "intent_analyze"


@pytest.mark.asyncio
async def test_intent_node_intelligent_pruning():
    """测试在追问场景下，智能剔除不相干的历史维度，仅保留指定的 keep_dimensions。"""
    state = create_initial_state(
        query="关于小米汽车的自动驾驶",
        research_id="res_123",
        tenant_id="tenant_abc",
        user_id="user_123",
        context_mode="follow_up",
        last_research_dimensions=["iPhone电池寿命", "iPhone屏幕材质"] # 这些是不相干的旧维度
    )
    
    config = {
        "configurable": {
            "tenant_id": "tenant_abc",
            "user_id": "user_123",
            "research_id": "res_123"
        }
    }
    
    # AI 认为上一轮的电池和屏幕不相关，因此 keep_dimensions 为空
    mock_llm_response = AIMessage(
        content='''{
            "intent_type": "explore",
            "search_plan": "探查小米汽车自动驾驶技术",
            "keep_dimensions": [],
            "new_dimensions": ["智能辅助驾驶", "算法与硬件"],
            "dedup_intensity": "standard"
        }'''
    )
    
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)
    mock_vectors = [
        [1.0, 0.0],  # 智能辅助驾驶
        [0.0, 1.0],  # 算法与硬件
    ]
    
    mock_db = MagicMock()
    mock_db.get = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch("backend.pipeline.nodes.intent.get_llm_for_stage", AsyncMock(return_value=mock_llm)), \
         patch("backend.db.engine.async_session", return_value=mock_session), \
         patch("backend.pipeline.nodes.intent.get_node_config", AsyncMock(return_value={"max_dimensions": 4}), create=True), \
         patch("backend.pipeline.nodes.intent.embed_documents_with_preset", AsyncMock(return_value=mock_vectors)), \
         patch("backend.pipeline.nodes.intent._load_preset_business", AsyncMock(return_value={}), create=True):
        
        updates = []
        async for chunk in intent_node(state, config):
            updates.append(chunk)
            
        result = updates[-1]
        dims = result["runtime"]["pipeline"]["dimensions"]
        # 旧的 iPhone 相关的维度应该被彻底清空，只保留小米汽车的新维度
        assert "iPhone电池寿命" not in dims
        assert "iPhone屏幕材质" not in dims
        assert "智能辅助驾驶" in dims
        assert "算法与硬件" in dims
        assert len(dims) == 2


@pytest.mark.asyncio
async def test_intent_node_dedup_intensity():
    """测试不同 dedup_intensity 去重强度对去重阈值及结果的影响。"""
    state = create_initial_state(
        query="物理实验",
        research_id="res_1",
        tenant_id="t1",
        context_mode="new_research"
    )
    config = {"configurable": {"tenant_id": "t1", "user_id": "u1"}}
    
    # 模拟两个极其相近的维度
    mock_llm_response = AIMessage(
        content='''{
            "intent_type": "explore",
            "search_plan": "测试去重档位",
            "dimensions": ["引力波检测实验", "引力波测量实验"],
            "dedup_intensity": "strict"
        }'''
    )
    mock_llm = MagicMock(ainvoke=AsyncMock(return_value=mock_llm_response))
    
    # 两个维度余弦相似度设为 0.78
    mock_vectors = [
        [1.0, 0.0],
        [0.78, 0.625]
    ]
    
    mock_db = MagicMock()
    mock_db.get = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    # 1. 严格档位 (strict, 阈值为 0.68, 由于 0.78 > 0.68 -> 会被判定为重复并过滤)
    with patch("backend.pipeline.nodes.intent.get_llm_for_stage", AsyncMock(return_value=mock_llm)), \
         patch("backend.db.engine.async_session", return_value=mock_session), \
         patch("backend.pipeline.nodes.intent.get_node_config", AsyncMock(return_value={"max_dimensions": 4}), create=True), \
         patch("backend.pipeline.nodes.intent.embed_documents_with_preset", AsyncMock(return_value=mock_vectors)), \
         patch("backend.pipeline.nodes.intent._load_preset_business", AsyncMock(return_value={}), create=True):
        
        updates = []
        async for chunk in intent_node(state, config):
            updates.append(chunk)
        result = updates[-1]
        dims = result["runtime"]["pipeline"]["dimensions"]
        # 第二个相似维度应当被严格过滤
        assert len(dims) == 1
        assert dims == ["引力波检测实验"]

    # 2. 宽松档位 (relaxed, 阈值为 0.80, 由于 0.78 <= 0.80 -> 允许共存，不会被过滤)
    mock_llm_response_relaxed = AIMessage(
        content='''{
            "intent_type": "explore",
            "search_plan": "测试去重档位",
            "dimensions": ["引力波检测实验", "引力波测量实验"],
            "dedup_intensity": "relaxed"
        }'''
    )
    mock_llm_relaxed = MagicMock(ainvoke=AsyncMock(return_value=mock_llm_response_relaxed))

    with patch("backend.pipeline.nodes.intent.get_llm_for_stage", AsyncMock(return_value=mock_llm_relaxed)), \
         patch("backend.db.engine.async_session", return_value=mock_session), \
         patch("backend.pipeline.nodes.intent.get_node_config", AsyncMock(return_value={"max_dimensions": 4}), create=True), \
         patch("backend.pipeline.nodes.intent.embed_documents_with_preset", AsyncMock(return_value=mock_vectors)), \
         patch("backend.pipeline.nodes.intent._load_preset_business", AsyncMock(return_value={}), create=True):
        
        updates = []
        async for chunk in intent_node(state, config):
            updates.append(chunk)
        result = updates[-1]
        dims = result["runtime"]["pipeline"]["dimensions"]
        # 两个相似维度皆可被保留
        assert len(dims) == 2
        assert "引力波检测实验" in dims
        assert "引力波测量实验" in dims
