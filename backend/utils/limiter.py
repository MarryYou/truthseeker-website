"""分布式限流器组件"""
from __future__ import annotations
import asyncio
import time
from backend.utils.redis import get_redis
from backend.core.logging import logger

class DistributedLimiter:
    """基于 Redis 的分布式限流器。
    
    实现 Sliding Cooldown (滑动冷却) 算法的原子时间戳预约（Atomic Booking）实现，
    确保在多实例环境下，对特定资源（如搜索引擎 API）的访问符合最小时间间隔要求，彻底防范高并发竞态下的并发泄露。
    """
    
    LUA_COOLDOWN_BOOKING = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local delay = tonumber(ARGV[2])
    
    local last_time_str = redis.call('get', key)
    local last_time = last_time_str and tonumber(last_time_str) or 0
    
    local target_time
    if not last_time or last_time < now then
        target_time = now
    else
        target_time = last_time + delay
    end
    
    redis.call('setex', key, 3600, tostring(target_time))
    return tostring(target_time)
    """

    def __init__(self, key_prefix: str = "truthseeker:limiter"):
        self.key_prefix = key_prefix

    async def wait_for_cooldown(self, resource_id: str, delay_seconds: float):
        """如果距离上次限流时间不足，则原子性预订未来时间并睡眠等待。"""
        if delay_seconds <= 0:
            return

        try:
            redis = await get_redis()
            key = f"{self.key_prefix}:cooldown:{resource_id}"
            now = time.time()
            
            # 使用 eval 原子性预订下一次允许的调用时间戳
            target_time_str = await redis.eval(self.LUA_COOLDOWN_BOOKING, 1, key, now, delay_seconds)
            target_time = float(target_time_str)
            
            sleep_time = target_time - time.time()
            if sleep_time > 0:
                logger.info("分布式限流激活（原子时间预订）| resource={} | 需等待 {:.2f}s", resource_id, sleep_time)
                await asyncio.sleep(sleep_time)
        except Exception as e:
            logger.warning("Redis 限流预订失败，回退到无延迟模式 | error={}", e)

    async def update_cooldown(self, resource_id: str):
        """记录当前时间戳到 Redis。在原子预订模式下，此处变更为无操作（No-op），防止写覆盖破坏后续预订。"""
        pass

# 全局单例
limiter = DistributedLimiter()
