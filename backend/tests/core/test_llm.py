import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage
from backend.core.llm import get_llm_for_stage, test_llm_connection as check_llm_connection, invalidate_llm_cache


@pytest.mark.asyncio
async def test_get_llm_missing_key_blocked():
    """测试在租户完全没有配置 API 密钥或预设不存在时，系统是否会如期抛出 RuntimeError 强行阻断"""
    # 场景 1：缺少预设阻断
    with patch("backend.core.llm._get_full_model_config", AsyncMock(side_effect=RuntimeError("用户缺少有效的研究预设配置"))):
        with pytest.raises(RuntimeError) as exc_info:
            await get_llm_for_stage("understanding", user_id="tenant-no-key")
        assert "缺少有效" in str(exc_info.value)
        

@pytest.mark.asyncio
async def test_llm_cache_and_invalidation():
    """测试 LLM 实例缓存及主动失效机制"""
    plain_key = "mock-cache-api-key"
    mock_config = {
        "provider": "openai",
        "model": "gpt-4",
        "api_key": plain_key,
        "base_url": None,
        "temperature": 0.1,
        "max_tokens": 1000,
        "params": {}
    }
    
    with patch("backend.core.llm._get_full_model_config", AsyncMock(return_value=mock_config)):
        # 第一次获取，应该缓存
        llm1 = await get_llm_for_stage("understanding", user_id="user-123", preset_id="preset-1")
        # 第二次获取，相同 user_id, preset_id, stage 应该返回同一个实例
        llm2 = await get_llm_for_stage("understanding", user_id="user-123", preset_id="preset-1")
        assert llm1 is llm2
        
        # 不同阶段应该生成新的实例
        llm3 = await get_llm_for_stage("search", user_id="user-123", preset_id="preset-1")
        assert llm3 is not llm1
        
        # 主动失效指定用户的某个 stage
        invalidate_llm_cache(user_id="user-123", stage="understanding")
        llm4 = await get_llm_for_stage("understanding", user_id="user-123", preset_id="preset-1")
        assert llm4 is not llm1
        
        # 主动失效指定用户的所有 stage
        invalidate_llm_cache(user_id="user-123")
        llm5 = await get_llm_for_stage("search", user_id="user-123", preset_id="preset-1")
        assert llm5 is not llm3

        # 重新获取，放入缓存
        llm_p1 = await get_llm_for_stage("understanding", user_id="user-123", preset_id="preset-1")
        llm_p2 = await get_llm_for_stage("understanding", user_id="user-123", preset_id="preset-2")
        assert llm_p1 is not llm_p2

        # 只失效 preset-1
        invalidate_llm_cache(user_id="user-123", preset_id="preset-1")
        llm_p1_new = await get_llm_for_stage("understanding", user_id="user-123", preset_id="preset-1")
        assert llm_p1_new is not llm_p1

        # 但 preset-2 应该保持不变
        llm_p2_same = await get_llm_for_stage("understanding", user_id="user-123", preset_id="preset-2")
        assert llm_p2_same is llm_p2


@pytest.mark.asyncio
async def test_test_llm_connection_success():
    """测试连通性校验通过的情况"""
    cfg = {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1"
    }
    
    mock_client = MagicMock()
    mock_client.ainvoke = AsyncMock(return_value=MagicMock())
    
    with patch("backend.core.llm._create_llm_from_resolved_config", return_value=mock_client):
        result = await check_llm_connection(cfg, "sk-test-123")
        assert result is True
        mock_client.ainvoke.assert_called_once()
        args, kwargs = mock_client.ainvoke.call_args
        assert isinstance(args[0][0], HumanMessage)
        assert args[0][0].content == "ping"


@pytest.mark.asyncio
async def test_test_llm_connection_failure():
    """测试连通性校验失败的情况"""
    cfg = {"provider": "openai"}
    
    mock_client = MagicMock()
    mock_client.ainvoke = AsyncMock(side_effect=Exception("Connection timeout or invalid key"))
    
    with patch("backend.core.llm._create_llm_from_resolved_config", return_value=mock_client):
        with pytest.raises(Exception) as exc_info:
            await check_llm_connection(cfg, "invalid-key")
        assert "Connection timeout" in str(exc_info.value)
