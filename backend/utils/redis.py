"""Redis 异步客户端单例与工具函数

注意：Redis 客户端是事件循环绑定的。
当事件循环变更时（如在 pytest 中跨测试函数），
get_client() 会自动销毁旧连接并创建新客户端。
"""
from __future__ import annotations
import asyncio
import redis.asyncio as async_redis
import redis as sync_redis
from backend.core.config import REDIS_URL
from backend.core.logging import logger

class RedisClient:
    _instance: async_redis.Redis | None = None
    _sync_instance: sync_redis.Redis | None = None
    _loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def get_client(cls) -> async_redis.Redis:
        """获取异步 Redis 客户端（单例，自动检测事件循环变更）。"""
        current_loop = asyncio.get_event_loop()

        # 如果事件循环变了（如 pytest 测试间），销毁旧连接
        if cls._instance is not None and cls._loop is not None and cls._loop != current_loop:
            logger.debug("检测到事件循环变更，重建 Redis 异步客户端")
            try:
                cls._instance = None
            except Exception:
                pass
            cls._loop = current_loop

        if cls._instance is None:
            logger.info("正在初始化 Redis 异步客户端 | URL={}", REDIS_URL)
            cls._instance = async_redis.from_url(
                REDIS_URL,
                decode_responses=True,
                health_check_interval=30,
                socket_keepalive=True,
            )
            cls._loop = current_loop
        return cls._instance

    @classmethod
    def get_sync_client(cls) -> sync_redis.Redis:
        """获取同步 Redis 客户端（单例）。"""
        if cls._sync_instance is None:
            logger.info("正在初始化 Redis 同步客户端 | URL={}", REDIS_URL)
            cls._sync_instance = sync_redis.from_url(REDIS_URL, decode_responses=True, health_check_interval=30)
        return cls._sync_instance

    @classmethod
    async def close(cls):
        """关闭所有 Redis 连接。"""
        if cls._instance:
            try:
                await cls._instance.close()
            except Exception:
                pass
            cls._instance = None
            cls._loop = None
            logger.info("Redis 异步客户端已关闭")
        if cls._sync_instance:
            try:
                cls._sync_instance.close()
            except Exception:
                pass
            cls._sync_instance = None
            logger.info("Redis 同步客户端已关闭")

async def get_redis() -> async_redis.Redis:
    return RedisClient.get_client()

def get_sync_redis() -> sync_redis.Redis:
    return RedisClient.get_sync_client()
