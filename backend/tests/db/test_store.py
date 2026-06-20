"""测试 ResearchStore 的读写与租户/任务 Namespace 隔离。"""
from __future__ import annotations
import pytest
from langgraph.store.memory import InMemoryStore
from backend.db.store import ResearchStore, get_store_from_config


@pytest.mark.asyncio
async def test_research_store_basic_flow():
    # 1. 准备底层的 InMemoryStore
    raw_store = InMemoryStore()
    
    # 2. 构造 ResearchStore (隔离租户 tenant_1 和 研究ID res_1)
    store = ResearchStore(raw_store, tenant_id="tenant_1", research_id="res_1")
    
    # 3. 测试搜索结果保存与加载
    search_data = [{"title": "Test Web", "url": "https://example.com"}]
    await store.save_search_results("query_1", search_data)
    
    loaded_search = await store.load_search_results("query_1")
    assert loaded_search == search_data
    
    # 4. 测试列出所有的 Key 和加载所有结果
    await store.save_search_results("query_2", [{"title": "Web 2", "url": "https://example2.com"}])
    keys = await store.list_search_result_keys()
    assert set(keys) == {"query_1", "query_2"}
    
    all_results = await store.load_all_search_results()
    assert len(all_results) == 2
    
    # 5. 测试筛选结果保存与加载
    filtered_data = [{"title": "Filtered Web", "url": "https://example.com"}]
    await store.save_filtered_results("final", filtered_data)
    assert await store.load_filtered_results("final") == filtered_data
    
    # 6. 测试声明保存与加载
    claims_data = [{"claim": "This is a statement", "verdict": "supported"}]
    await store.save_claims("final", claims_data)
    assert await store.load_claims("final") == claims_data
    
    # 7. 测试报告保存与加载
    report_content = "# Final Report\nHello world!"
    await store.save_report("final", report_content)
    assert await store.load_report("final") == report_content


@pytest.mark.asyncio
async def test_research_store_namespace_isolation():
    # 验证不同租户和研究线程之间的数据完全物理隔离
    raw_store = InMemoryStore()
    
    store_a = ResearchStore(raw_store, tenant_id="tenant_a", research_id="res_1")
    store_b = ResearchStore(raw_store, tenant_id="tenant_b", research_id="res_1")
    store_c = ResearchStore(raw_store, tenant_id="tenant_a", research_id="res_2")
    
    await store_a.save_report("final", "Report A")
    await store_b.save_report("final", "Report B")
    await store_c.save_report("final", "Report C")
    
    assert await store_a.load_report("final") == "Report A"
    assert await store_b.load_report("final") == "Report B"
    assert await store_c.load_report("final") == "Report C"


def test_get_store_from_config():
    raw_store = InMemoryStore()
    config = {
        "configurable": {
            "store": raw_store,
            "tenant_id": "tenant_x",
            "research_id": "res_x"
        }
    }
    
    store = get_store_from_config(config)
    assert store._tenant_id == "tenant_x"
    assert store._research_id == "res_x"
    assert store._store is raw_store
