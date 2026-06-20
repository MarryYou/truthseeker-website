import pytest
from httpx import AsyncClient
from unittest.mock import patch
from backend.db.models import User, UserModelAsset

@pytest.mark.asyncio
async def test_get_secrets_unauthorized(client: AsyncClient):
    response = await client.get("/api/v1/settings/secrets")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_upsert_secret_success(client: AsyncClient, db_session):
    # 使用随机生成的 ID 和 Email 确保隔离
    import uuid
    uid = str(uuid.uuid4())
    user = User(id=uid, email=f"test-{uid}@example.com", tenant_id="tenant-123", role="user")
    db_session.add(user)
    await db_session.commit()

    with patch("backend.api.auth.SessionManager.get_session") as mock_get_session:
        mock_get_session.return_value = {"user_id": uid, "tenant_id": "tenant-123", "role": "user"}

        payload = {
            "category": "llm",
            "provider_name": "deepseek",
            "plain_key": "sk-mock-key",
            "base_url": "https://api.deepseek.com/v1"
        }
        
        with patch("backend.services.settings_service.test_provider_connection", return_value=True):
            response = await client.put(
                "/api/v1/settings/secrets", 
                json=payload,
                cookies={"ts_session": "valid-session"}
            )
            assert response.status_code == 200
            assert response.json()["message"] == "供应商凭证更新成功"

@pytest.mark.asyncio
async def test_list_assets(client: AsyncClient, db_session):
    import uuid
    uid = str(uuid.uuid4())
    user = User(id=uid, email=f"test-{uid}@example.com", tenant_id="tenant-123", role="user")
    db_session.add(user)
    
    asset = UserModelAsset(
        id=f"asset-{uid}", tenant_id="tenant-123", user_id=uid,
        provider_name="openai", model_name="gpt-4o"
    )
    db_session.add(asset)
    await db_session.commit()

    with patch("backend.api.auth.SessionManager.get_session") as mock_get_session:
        mock_get_session.return_value = {"user_id": uid, "tenant_id": "tenant-123", "role": "user"}

        response = await client.get("/api/v1/settings/assets", cookies={"ts_session": "valid-session"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(a["model_name"] == "gpt-4o" for a in data)
