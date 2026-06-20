import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from backend.db.engine import async_engine
from backend.db.models import Base

from backend.search.orchestrator import SearchOrchestrator
@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """每次测试前初始化表结构"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_search_orchestrator_multi_engine_call():
    """测试 SearchOrchestrator 并发调度多个搜索引擎"""
    user_id = "test-user-123"
    async_session = AsyncMock() # 模拟 DB Session
    
    # 模拟从数据库获取配置
    with patch("backend.search.orchestrator.get_decrypted_provider_key") as mock_get_key:
        
        # 模拟 Key
        mock_get_key.return_value = "dummy-key"
        
        # 模拟预设
        mock_preset = MagicMock()
        mock_preset.nodes_config = {
            "stages": {
                "search": {
                    "params": {
                        "tavily": {"search_depth": "advanced"},
                        "bocha": {"freshness": "one_week"}
                    }
                }
            }
        }
        async_session.get.return_value = mock_preset
        
        # 模拟底层插件
        with patch("backend.search.tavily.TavilySearchPlugin.search", new_callable=AsyncMock) as mock_tavily, \
             patch("backend.search.bocha.BochaSearchPlugin.search", new_callable=AsyncMock) as mock_bocha:
             
            mock_tavily.return_value = [{"title": "Tavily Result", "url": "https://foo.com/1", "snippet": "A"}]
            mock_bocha.return_value = [{"title": "Bocha Result", "url": "https://bar.com/2", "snippet": "B"}]
            
            orchestrator = SearchOrchestrator(db=async_session, tenant_id="test-tenant", user_id=user_id)
            results = await orchestrator.search(
                query="test query",
                engines=["tavily", "bocha"],
                preset_id="preset-123"
            )
            
            assert len(results) == 2
            urls = {r["url"] for r in results}
            assert "https://foo.com/1" in urls
            assert "https://bar.com/2" in urls


