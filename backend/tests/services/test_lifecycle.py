import pytest
import time
from unittest.mock import AsyncMock, patch
from backend.services.research_lifecycle import save_research_result, map_claims_to_frontend
from backend.db.models import ResearchTask, ResearchSession
from langgraph.store.memory import InMemoryStore

@pytest.mark.asyncio
async def test_research_archive_success():
    """测试研究任务成功归档"""
    # 1. 准备数据
    mock_db = AsyncMock()
    mock_task = ResearchTask(id="task_1", status="running", run_config_snapshot={})
    
    # 模拟 get 方法根据类型返回不同记录
    async def mock_get(model_class, pk):
        if model_class == ResearchTask:
            return mock_task
        elif model_class == ResearchSession:
            return ResearchSession(id="res_1", status="active", total_duration_seconds=0)
        return None
    mock_db.get.side_effect = mock_get
    
    raw_store = InMemoryStore()
    
    # 模拟最终状态
    final_state = {
        "report_prompt": "Final report",
        "dimensions": ["D1"],
        "history_summary": "Summary",
        "output": {
            "pipeline": {
                "overall_confidence": 0.8
            }
        }
    }
    
    # Mock crud.update_research_task
    with patch("backend.db.crud.update_research_task", AsyncMock()) as mock_update:
        await save_research_result(
            db=mock_db,
            tenant_id="t1",
            research_id="res_1",
            task_id="task_1",
            final_state=final_state,
            raw_store=raw_store,
            start_time=time.time() - 10,
            status="completed"
        )
        
        # 2. 验证
        mock_update.assert_called_once()
        args, kwargs = mock_update.call_args
        assert kwargs["status"] == "completed"
        assert kwargs["summary"] == "Final report"
        assert kwargs["overall_confidence"] == 0.8

def test_map_claims_to_frontend():
    """测试声明映射逻辑"""
    raw_claims = [
        {
            "text": "事实1",
            "dimension": "性能",
            "verdict": "consistent",
            "consistency_score": 0.9,
            "reasoning": "证据充分",
            "source_url": "https://a.com"
        }
    ]
    
    mapped = map_claims_to_frontend(raw_claims)
    assert len(mapped) == 1
    assert mapped[0]["claim"] == "事实1"
    assert mapped[0]["verdict"] == "verified" # consistent -> verified
    assert mapped[0]["supporting_sources"] == ["https://a.com"]
