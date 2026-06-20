import pytest
from httpx import AsyncClient
from unittest.mock import patch
from backend.db.models import ResearchPreset, User, UserModelAsset, UserProvider

@pytest.mark.asyncio
async def test_chat_new_research_unauthorized(client: AsyncClient):
    """测试未登录发起新研究"""
    # 使用无斜杠路径匹配 @router.post("")
    response = await client.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_chat_new_research_success(client: AsyncClient, db_session):
    """测试登录后发起新研究（Mock SSE Handler）"""
    # 1. 构造测试数据
    user = User(id="user-123", email="test@example.com", tenant_id="tenant-123", role="user")
    db_session.add(user)
    
    # 添加模型资产
    asset = UserModelAsset(
        id="mock-asset-123", 
        tenant_id="tenant-123", 
        user_id="user-123", 
        provider_name="deepseek", 
        model_name="deepseek-v4-flash"
    )
    db_session.add(asset)

    # 添加模型凭证
    llm_key = UserProvider(
        id="key-123", 
        tenant_id="tenant-123", 
        user_id="user-123", 
        category="llm", 
        provider_name="deepseek", 
        encrypted_key="mock-encrypted"
    )
    db_session.add(llm_key)

    # 添加搜索引擎凭证 (默认使用的 bocha)
    search_key = UserProvider(
        id="key-456", 
        tenant_id="tenant-123", 
        user_id="user-123", 
        category="search", 
        provider_name="bocha", 
        encrypted_key="mock-encrypted"
    )
    db_session.add(search_key)
    
    preset = ResearchPreset(
        id="preset-123", 
        name="research_pipeline", 
        tenant_id="tenant-123", 
        user_id="user-123",
        nodes_config={
            "business": {"speed": "research_pipeline"}, 
            "stages": {
                "research_pipeline": {"asset_id": "mock-asset-123"}
            }
        },
        is_system_default=True
    )
    db_session.add(preset)
    await db_session.commit()

    # 2. Mock SessionManager、入队和 SSE 消费者
    with patch("backend.api.auth.SessionManager.get_session") as mock_get_session, \
         patch("backend.worker.enqueue_research") as _, \
         patch("backend.api.chat.sse_from_redis") as mock_sse:

        mock_get_session.return_value = {"user_id": "user-123", "tenant_id": "tenant-123", "role": "user"}

        # Mock sse_from_redis 返回一个异步生成器
        async def mock_iter(*args, **kwargs):
            yield "event: token\ndata: {\"text\": \"Hello\"}\n\n"
            yield "event: complete\ndata: {\"research_id\": \"res-123\"}\n\n"

        mock_sse.return_value = mock_iter()

        # 3. 发起请求
        response = await client.post(
            "/api/v1/chat", 
            json={"message": "什么是三层级响应体系？"},
            cookies={"ts_session": "valid-session"}
        )
        
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        # 验证结果流
        content = response.text
        assert "event: token" in content
        assert "Hello" in content
        assert "event: complete" in content
