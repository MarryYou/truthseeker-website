import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services.app_lifecycle import _periodic_checkpoints_cleanup

@pytest.mark.asyncio
async def test_periodic_checkpoints_cleanup():
    """测试定期 checkpoints 清除协程的 SQL 拼接与调用逻辑"""
    mock_cursor = AsyncMock()
    mock_cursor.rowcount = 5
    
    mock_cursor_context = MagicMock()
    mock_cursor_context.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor_context.__aexit__ = AsyncMock()
    
    mock_conn = AsyncMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor_context)
    
    mock_conn_context = MagicMock()
    mock_conn_context.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn_context.__aexit__ = AsyncMock()
    
    mock_pool = MagicMock()
    mock_pool.connection = MagicMock(return_value=mock_conn_context)
    
    sleep_calls = 0
    async def mock_sleep(delay):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            return
        else:
            raise asyncio.CancelledError()
            
    with patch("asyncio.sleep", side_effect=mock_sleep):
        with pytest.raises(asyncio.CancelledError):
            await _periodic_checkpoints_cleanup(mock_pool)
            
    assert mock_cursor.execute.call_count == 3
    
    calls = mock_cursor.execute.call_args_list
    sql_1 = calls[0][0][0]
    sql_2 = calls[1][0][0]
    sql_3 = calls[2][0][0]
    
    assert "DELETE FROM checkpoint_writes" in sql_1
    assert "DELETE FROM checkpoint_blobs" in sql_2
    assert "DELETE FROM checkpoints" in sql_3
    assert "created_at < NOW() - INTERVAL '30 days'" in sql_1
    assert "created_at < NOW() - INTERVAL '30 days'" in sql_2
    assert "created_at < NOW() - INTERVAL '30 days'" in sql_3
