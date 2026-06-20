"""测试 report_node 的最终报告生成与自愈逻辑。"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore

from backend.pipeline.state import create_initial_state
from backend.pipeline.nodes.report import report_node
from backend.db.store import ResearchStore

MOCK_REPORT_MD = """# 最终报告
## 执行摘要
反重力仍处于理论阶段。

## 详细分析
### 1. 物理原理
目前没有已知物理理论支持宏观反重力。

[来源A](https://a.com)
"""

def _make_config(raw_store):
    return {
        "configurable": {
            "tenant_id": "tenant_1",
            "research_id": "res_1",
            "store": raw_store
        }
    }

@pytest.mark.asyncio
async def test_report_node_basic():
    """验证基本报告生成流程"""
    raw_store = InMemoryStore()
    rs = ResearchStore(raw_store, tenant_id="tenant_1", research_id="res_1")
    
    # 预存 claims 和筛选结果
    await rs.save_claims("final", [
        {"text": "反重力装置处于实验阶段", "source_url": "https://a.com", "dimension": "技术成熟度", "confidence": 0.8},
    ])
    await rs.save_filtered_results("final", [
        {"title": "来源A", "url": "https://a.com", "summary": "实验阶段", "dimension": "技术成熟度"},
    ])
    
    state = create_initial_state(query="反重力装置研究进展", research_id="res_1", tenant_id="tenant_1")
    state["runtime"]["shared"]["intent_type"] = "explore"
    state["runtime"]["pipeline"]["dimensions"] = ["技术成熟度", "商用时间表"]
    state["runtime"]["pipeline"]["conflict_dimensions"] = ["商用时间表"]
    state["runtime"]["pipeline"]["insufficient_dimensions"] = []
    state["output"]["pipeline"]["overall_confidence"] = 0.65
    
    config = _make_config(raw_store)
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=MOCK_REPORT_MD))
    # report_node uses astream internally
    async def _fake_astream(prompt):
        yield AIMessage(content=MOCK_REPORT_MD)
    mock_llm.astream = MagicMock(return_value=_fake_astream("dummy"))
    
    with patch("backend.pipeline.nodes.report.get_llm_for_stage", AsyncMock(return_value=mock_llm)):
        updates = []
        async for chunk in report_node(state, config):
            updates.append(chunk)
            
        result = updates[-1]
        assert "report_prompt" in result["output"]["pipeline"]
        assert "# 最终报告" in result["output"]["pipeline"]["report_prompt"]

@pytest.mark.asyncio
async def test_report_node_with_no_claims():
    """无 claims 时，应仍能正常生成报告"""
    raw_store = InMemoryStore()
    rs = ResearchStore(raw_store, tenant_id="tenant_1", research_id="res_1")
    # claims 为空，但有筛选结果
    await rs.save_filtered_results("final", [
        {"title": "来源X", "url": "https://x.com", "summary": "通用信息", "dimension": "通用"},
    ])
    
    state = create_initial_state(query="任意查询", research_id="res_1", tenant_id="tenant_1")
    state["output"]["pipeline"]["overall_confidence"] = 0.5
    config = _make_config(raw_store)
    
    NO_CLAIMS_REPORT = "# 报告\n内容"
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=NO_CLAIMS_REPORT))
    async def _fake_astream2(prompt):
        yield AIMessage(content=NO_CLAIMS_REPORT)
    mock_llm.astream = MagicMock(return_value=_fake_astream2("dummy"))
    
    with patch("backend.pipeline.nodes.report.get_llm_for_stage", AsyncMock(return_value=mock_llm)):
        updates = []
        async for chunk in report_node(state, config):
            updates.append(chunk)
        
        result = updates[-1]
        assert "report_prompt" in result["output"]["pipeline"]

@pytest.mark.asyncio
async def test_report_node_exception_handling():
    """LLM 异常时逻辑"""
    raw_store = InMemoryStore()
    state = create_initial_state(query="测试", research_id="res_1", tenant_id="tenant_1")
    config = _make_config(raw_store)
    
    with patch("backend.pipeline.nodes.report.get_llm_for_stage", AsyncMock(side_effect=RuntimeError("Report LLM offline"))):
        # 现在的实现中，若数据加载为空或 LLM 彻底失败，会抛出 PipelineAbortError
        from backend.pipeline.types import PipelineAbortError
        with pytest.raises(PipelineAbortError):
            async for _ in report_node(state, config):
                pass
