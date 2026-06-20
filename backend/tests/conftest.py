import os
import pytest
import pytest_asyncio
from typing import AsyncIterator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# 1. 强制环境变量隔离 (在导入 app 之前)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-123"
os.environ["REDIS_URL"] = "redis://localhost:6379/9" # 使用独立的测试 DB

from backend.api.app import app
from backend.db.models import Base
from backend.db.engine import get_db

# 2. 数据库 Fixtures
@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    Session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
        await session.rollback()

# 3. FastAPI Client Fixture
@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    # 覆盖依赖注入
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(
        transport=ASGITransport(app=app), 
        base_url="http://testserver"
    ) as ac:
        yield ac
    
    app.dependency_overrides.clear()

# 4. Mock 辅助 Fixtures
@pytest.fixture
def mock_llm():
    """Mock LangChain 聊天模型"""
    from unittest.mock import AsyncMock
    m = AsyncMock()
    m.ainvoke.return_value.content = "Mocked AI Response"
    return m

@pytest.fixture
def mock_redis():
    """Mock Redis 客户端"""
    from unittest.mock import AsyncMock
    m = AsyncMock()
    return m
