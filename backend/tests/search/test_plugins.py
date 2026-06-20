import pytest
import respx
from httpx import Response
from unittest.mock import AsyncMock, patch
from backend.search.tavily import TavilySearchPlugin
from backend.search.bocha import BochaSearchPlugin
from backend.search.zhihu import ZhihuPlugin

@pytest.mark.asyncio
@respx.mock
async def test_tavily_plugin():
    plugin = TavilySearchPlugin()
    respx.post("https://api.tavily.com/search").mock(return_value=Response(200, json={
        "results": [{"title": "T1", "url": "https://t1.com", "content": "S1"}]
    }))
    
    results = await plugin.search("test", "sk-123")
    assert len(results) == 1
    assert results[0]["title"] == "T1"

@pytest.mark.asyncio
@respx.mock
async def test_bocha_plugin():
    plugin = BochaSearchPlugin()
    respx.post("https://api.bochaai.com/v1/web-search").mock(return_value=Response(200, json={
        "data": {"webPages": {"value": [{"name": "B1", "url": "https://b1.com", "snippet": "S1"}]}}
    }))
    
    results = await plugin.search("test", "sk-123")
    assert len(results) == 1
    assert results[0]["title"] == "B1"

@pytest.mark.asyncio
@respx.mock
async def test_zhihu_plugin():
    plugin = ZhihuPlugin()
    respx.get(url__regex=r"https://developer.zhihu.com/api/v1/content/global_search.*").mock(return_value=Response(200, json={
        "Code": 0,
        "Data": {"Items": [{"Title": "Z1", "Url": "https://z1.com", "ContentText": "S1"}]}
    }))
    
    results = await plugin.search("test", "sk-123")
    assert len(results) == 1
    assert results[0]["title"] == "Z1"