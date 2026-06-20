"""utils/retry.py — 异步操作重试装饰器"""
from __future__ import annotations
import asyncio
import functools
from backend.core.logging import logger


def retry(max_retries: int = 2, base_delay: float = 0.5):
    """一个简单的异步方法重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        logger.error("方法 {} 达到最大重试次数 {}，仍然失败: {}", func.__name__, max_retries, e)
                        raise
                    logger.warning("方法 {} 执行失败，将在 {:.2f}s 后进行第 {}/{} 次重试. 错误: {}", 
                                   func.__name__, delay, attempt + 1, max_retries, e)
                    await asyncio.sleep(delay)
                    delay *= 2  # 指数退避
        return wrapper
    return decorator
