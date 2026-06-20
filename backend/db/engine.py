from __future__ import annotations
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.core.config import DATABASE_URL
from backend.core.logging import logger

# 1. 区分测试数据库（sqlite）与生产数据库（postgresql），配置差异化连接池参数
engine_kwargs = {}
if DATABASE_URL.startswith("postgresql"):
    engine_kwargs.update({
        "pool_size": 10,           # 增加连接池大小，应对多并发流式请求
        "max_overflow": 20,        # 允许最大溢出连接数
        "pool_recycle": 3600,      # 一小时回收连接，防范连接失效
        "pool_pre_ping": True,     # 🚀 关键：在从池中取出连接前先测试其连通性，自动剔除断开的连接
    })

# 2. 实例化异步引擎与 Session 制造器
async_engine = create_async_engine(DATABASE_URL, **engine_kwargs)
# expire_on_commit=False 保证离开事务后，ORM 对象的属性依然可以被读取而不会抛出过期异常
async_session = async_sessionmaker(async_engine, expire_on_commit=False)


# 3. 异步 Session 依赖注入生成器
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """生成异步数据库 Session，在请求结束时自动关闭释放连接"""
    async with async_session() as session:
        logger.debug("DB Session Created")
        try:
            yield session
        finally:
            logger.debug("DB Session Released")
