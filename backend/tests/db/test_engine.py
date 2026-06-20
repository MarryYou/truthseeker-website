import os
# 注入临时测试的 SQLite 内存数据库 URL 替换真实的 Postgres URL
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-123"

import pytest
from sqlalchemy import text
from backend.db import engine


@pytest.mark.asyncio
async def test_db_engine_connection():
    """测试数据库引擎是否能够正常初始化并执行基础的异步 SQL"""
    # 验证 async_engine 实例已存在
    assert engine.async_engine is not None
    
    # 尝试建立连接并执行一次极简查询
    async with engine.async_engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        val = result.scalar()
        assert val == 1


@pytest.mark.asyncio
async def test_async_session_maker():
    """测试 async_sessionmaker 能否成功创建并管理事务"""
    assert engine.async_session is not None
    
    # 开启一个事务
    async with engine.async_session() as session:
        result = await session.execute(text("SELECT 2"))
        assert result.scalar() == 2
        # 会话在此处离开 with 后应能自动释放


@pytest.mark.asyncio
async def test_get_db_generator():
    """测试 get_db 异步依赖注入生成器的生命周期"""
    db_generator = engine.get_db()
    
    # 手动迭代生成器获取 session
    session = await anext(db_generator)
    
    # 验证 session 能够正常执行 SQL
    result = await session.execute(text("SELECT 3"))
    assert result.scalar() == 3
    
    # 关闭生成器，这会触发 get_db 内 with 块的退出，从而关闭 session
    try:
        await anext(db_generator)
    except StopAsyncIteration:
        pass
    
    # 验证 session 已经被关闭（对于 SQLAlchemy，在 async with 退出后，会话不再处于活动事务中）
    assert session.in_transaction() is False

