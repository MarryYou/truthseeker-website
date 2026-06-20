import pytest
import json
from unittest.mock import MagicMock, AsyncMock
from backend.services.context import resolve_context
from backend.db.models import ResearchSession, ResearchTask

@pytest.mark.asyncio
async def test_resolve_context_success():
    # 模拟数据库 Session
    mock_db = AsyncMock()
    
    # 模拟 ResearchSession 记录
    mock_research = ResearchSession(
        id="res_123",
        tenant_id="tenant_123",
        user_id="user_123",
        preset_id="preset_123"
    )
    
    # 模拟历史任务
    conclusion = {
        "core_answer": "这是旧报告的内容",
        "key_findings": ["发现1"],
        "covered_aspects": ["维度1"],
        "unresolved": []
    }
    mock_task = ResearchTask(
        id="task_1",
        session_id="res_123",
        query="旧问题",
        status="completed",
        research_conclusion=json.dumps(conclusion),
        ordinal=1
    )
    
    # 设置 Mock DB 返回
    mock_result_session = MagicMock()
    mock_result_session.scalar_one_or_none.return_value = mock_research
    
    mock_result_tasks = MagicMock()
    mock_result_tasks.scalars.return_value.all.return_value = [mock_task]
    
    # 按顺序设置 execute 返回值
    mock_db.execute.side_effect = [mock_result_session, mock_result_tasks]
    
    # 执行测试
    result = await resolve_context(
        db=mock_db,
        tenant_id="tenant_123",
        user_id="user_123",
        research_id="res_123",
        query="新问题"
    )
    
    # 验证逻辑
    assert result["query"] == "新问题"
    assert result["research_id"] == "res_123"
    assert result["context_mode"] == "follow_up"
    assert len(result["follow_up_history"]) == 1
    assert result["follow_up_history"][0]["query"] == "旧问题"
    assert result["last_research_summary"] == "这是旧报告的内容"
    assert result["last_research_dimensions"] == ["维度1"]

@pytest.mark.asyncio
async def test_resolve_context_unauthorized():
    mock_db = AsyncMock()
    mock_research = ResearchSession(
        id="res_123",
        tenant_id="tenant_OTHER",
        user_id="user_123",
        preset_id="preset_123"
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_research
    mock_db.execute.return_value = mock_result
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as excinfo:
        await resolve_context(
            db=mock_db,
            tenant_id="tenant_123",
            user_id="user_123",
            research_id="res_123",
            query="新问题"
        )
    assert excinfo.value.status_code == 403
