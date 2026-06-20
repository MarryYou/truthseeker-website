"""测试 seed.py (ORM 3.0 简化版)"""
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.db.engine import async_engine
from backend.db.models import Base, ResearchPreset, Tenant, User
from backend.db.seed import initialize_user_data
from backend.pipeline.constants import DEFAULT_PRESETS


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """测试前后重置表结构"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _session_factory():
    return sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_initialize_user_data():
    """测试新用户初始化逻辑"""
    Session = _session_factory()
    user_id = "test-user-123"
    tenant_id = "test-tenant-123"
    
    async with Session() as db:
        async with db.begin():
            # 需要先有租户和用户，满足外键
            tenant = Tenant(id=tenant_id, name="Test")
            user = User(id=user_id, email="test@example.com", tenant_id=tenant_id)
            db.add_all([tenant, user])
            
        # 执行初始化
        await initialize_user_data(db, user_id, tenant_id)
        await db.commit()

    async with Session() as db:
        # 验证是否创建了 3 个预设
        stmt = select(ResearchPreset).where(ResearchPreset.user_id == user_id)
        result = await db.execute(stmt)
        presets = result.scalars().all()
        
        assert len(presets) == len(DEFAULT_PRESETS)
        
        # 验证预设内容
        preset = next(p for p in presets if p.name == "research_pipeline")
        assert preset.nodes_config.get("business", {}).get("speed") == "research_pipeline"
        assert preset.is_default is True
