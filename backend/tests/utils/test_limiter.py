"""分布式限流器单元测试"""
from __future__ import annotations
import time
from unittest.mock import AsyncMock, patch
import pytest
from backend.utils.limiter import DistributedLimiter

@pytest.mark.asyncio
async def test_distributed_limiter_booking():
    """测试限流器的原子时间戳预约逻辑"""
    limiter = DistributedLimiter(key_prefix="test_limiter")
    resource_id = "test_res"
    delay = 0.2
    
    # 模拟 Redis 客户端
    mock_redis = AsyncMock()
    
    # 第一次获取返回当前时间 (即 target_time = now, sleep_time <= 0)
    now = time.time()
    mock_redis.eval.side_effect = [str(now), str(now + delay)]
    
    with patch("backend.utils.limiter.get_redis", return_value=mock_redis), \
         patch("asyncio.sleep", AsyncMock()) as mock_sleep:
         
        # 1. 第一次调用：target_time 为当前时间，不应等待/睡眠
        await limiter.wait_for_cooldown(resource_id, delay)
        mock_sleep.assert_not_called()
        
        # 2. 第二次调用：target_time 为未来时间，应当睡眠
        await limiter.wait_for_cooldown(resource_id, delay)
        mock_sleep.assert_called_once()
        # 睡眠时间大约是 delay
        sleep_arg = mock_sleep.call_args[0][0]
        assert abs(sleep_arg - delay) < 0.05

@pytest.mark.asyncio
async def test_distributed_limiter_update_cooldown():
    """测试 update_cooldown 的 no-op 行为"""
    limiter = DistributedLimiter(key_prefix="test_limiter")
    # 不应该对 Redis 发起任何 set 写入操作
    mock_redis = AsyncMock()
    with patch("backend.utils.limiter.get_redis", return_value=mock_redis):
        await limiter.update_cooldown("test_res")
        mock_redis.set.assert_not_called()

@pytest.mark.asyncio
async def test_distributed_limiter_error_fallback():
    """测试 Redis 异常时的兜底逻辑"""
    limiter = DistributedLimiter(key_prefix="test_error")
    
    with patch("backend.utils.limiter.get_redis", side_effect=Exception("Redis Down")):
        # 不应抛出异常，而是直接跳过限流
        await limiter.wait_for_cooldown("res", 1.0)
        await limiter.update_cooldown("res")
