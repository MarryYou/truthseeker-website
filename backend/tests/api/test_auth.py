import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_auth_login_redirect(client: AsyncClient):
    """测试登录跳转到 Logto"""
    with patch("backend.api.auth.LogtoClient") as mock_logto:
        mock_instance = mock_logto.return_value
        mock_instance.signIn = AsyncMock(return_value="https://logto.app/authorize")
        
        response = await client.get("/api/v1/auth/login", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "https://logto.app/authorize"
        # 验证是否设置了临时 Cookie
        assert "ts_auth_sid" in response.cookies

@pytest.mark.asyncio
async def test_auth_me_unauthorized(client: AsyncClient):
    """测试未登录时访问 /me"""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_auth_logout(client: AsyncClient):
    """测试退出登录"""
    with patch("backend.api.auth.LogtoClient") as mock_logto, \
         patch("backend.core.session.get_redis") as mock_get_redis:
        
        # Mock Redis
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        mock_instance = mock_logto.return_value
        mock_instance.signOut = AsyncMock(return_value="https://logto.app/logout")
        
        response = await client.get("/api/v1/auth/logout")
        assert response.status_code == 307
        assert response.headers["location"] == "https://logto.app/logout"
        # 验证 Cookie 是否被删除
        assert "ts_session" not in response.cookies
        
        # 验证 Redis delete 被调用
        mock_redis.delete.assert_called()
