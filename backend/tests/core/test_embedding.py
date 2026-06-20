import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.core import embedding


@pytest.mark.asyncio
async def test_embed_documents_empty_texts():
    """测试空文本输入直接返回空列表"""
    result = await embedding.embed_documents([])
    assert result == []


@pytest.mark.asyncio
async def test_embed_documents_dashscope_routing():
    """测试路由到 dashscope.MultiModalEmbedding 的分支（并验证按索引重排功能）"""
    texts = ["测试文本1", "测试文本2"]
    cfg = {"provider": "dashscope", "model": "test-model"}
    decrypted_key = "mock_dashscope_key"
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # 模拟 SDK 返回了乱序的结果（现实中有可能发生，这里验证 sort 逻辑）
    mock_resp.output = {
        "embeddings": [
            {"index": 1, "embedding": [0.2, 0.2, 0.2]},
            {"index": 0, "embedding": [0.1, 0.1, 0.1]}
        ]
    }
    
    with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        mock_thread.return_value = mock_resp
        
        result = await embedding.embed_documents(texts, cfg=cfg, decrypted_api_key=decrypted_key)
        
        # 验证是否按照 index 0, 1 正确排序还原
        assert result == [[0.1, 0.1, 0.1], [0.2, 0.2, 0.2]]


@pytest.mark.asyncio
async def test_embed_documents_dashscope_api_failure():
    """测试 dashscope API 返回非 200 时抛出 RuntimeError"""
    texts = ["测试文本"]
    cfg = {"provider": "dashscope", "model": "test-model"}
    decrypted_key = "mock_dashscope_key"
    
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.code = "InvalidParameter"
    mock_resp.message = "Parameter is missing"
    
    with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        mock_thread.return_value = mock_resp
        
        with pytest.raises(RuntimeError) as exc_info:
            await embedding.embed_documents(texts, cfg=cfg, decrypted_api_key=decrypted_key)
            
        assert "DashScope MultiModalEmbedding 调用失败" in str(exc_info.value)
        assert "InvalidParameter" in str(exc_info.value)


@pytest.mark.asyncio
async def test_embed_documents_openai_routing():
    """测试路由到 langchain_openai.OpenAIEmbeddings 的分支"""
    texts = ["OpenAI 测试"]
    cfg = {"provider": "openai", "model": "text-embedding-3-small", "params": {"base_url": "mock-url"}}
    decrypted_key = "mock_openai_key"
    
    # 模拟 aembed_documents 返回
    mock_aembed = AsyncMock(return_value=[[0.5, 0.5, 0.5]])
    
    with patch("langchain_openai.OpenAIEmbeddings.aembed_documents", mock_aembed):
        result = await embedding.embed_documents(texts, cfg=cfg, decrypted_api_key=decrypted_key)
        assert result == [[0.5, 0.5, 0.5]]
        mock_aembed.assert_called_once_with(texts)


@pytest.mark.asyncio
async def test_embed_documents_missing_key_blocked():
    """测试在缺失 API Key 时直接报错阻断"""
    texts = ["测试"]
    with pytest.raises(ValueError) as exc_info:
        await embedding.embed_documents(texts, cfg={"provider": "openai"}, decrypted_api_key=None, tenant_id="blocked-tenant")
    assert "未配置对应的 API 密钥" in str(exc_info.value)
    
    
@pytest.mark.asyncio
async def test_embed_documents_unsupported_provider():
    """测试不支持的厂商抛错"""
    texts = ["测试"]
    cfg = {"provider": "unknown_provider", "model": "test"}
    decrypted_key = "test_key"
    
    with pytest.raises(ValueError) as exc_info:
        await embedding.embed_documents(texts, cfg=cfg, decrypted_api_key=decrypted_key)
        
    assert "不支持的 Embedding 厂商" in str(exc_info.value)


@pytest.mark.asyncio
async def test_embed_documents_missing_cfg():
    """测试不提供 cfg 时抛出 ValueError"""
    with pytest.raises(ValueError) as exc_info:
        await embedding.embed_documents(["测试文本"], cfg=None)
    assert "未提供有效的 embedding 配置" in str(exc_info.value)
