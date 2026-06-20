import pytest
from sqlalchemy import text
from backend.db.engine import async_engine
from backend.db.migrate import init_db


@pytest.mark.asyncio
async def test_init_db_creates_all_tables():
    """测试 init_db 能够正确创建所有 5 张业务表"""
    # 1. 首先删除所有表，确认为干净的测试环境
    from backend.db.models import Base
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        
    # 2. 执行数据库初始化
    await init_db(async_engine)
    
    # 3. 验证这 5 张表是否均已存在
    async with async_engine.connect() as conn:
        # 执行 SQLite 系统查询验证表存在
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        tables = {row[0] for row in result.fetchall()}
        
        expected_tables = {"tenants", "users", "user_providers", "user_model_assets", "research_presets", "research_sessions", "research_tasks"}

        # 验证这些核心业务表被包含在内
        assert expected_tables.issubset(tables)
