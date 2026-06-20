import pytest
from uuid import uuid4
from sqlalchemy import select
from backend.db.engine import async_engine
from backend.db.models import Base, Tenant, User, ResearchPreset
from backend.db.crud import (
    upsert_user_provider, 
    get_decrypted_provider_key, 
    upsert_research_preset,
    create_user,
    get_or_create_tenant
)


import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """测试前后重置表结构"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_user_provider_encryption_flow():
    """测试 UserProvider 在 CRUD 层写入时加密，读取时解密的完整闭环"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    tenant_id = str(uuid4())
    user_id = str(uuid4())
    plain_api_key = "sk-openai-test-123"
    
    async with async_session() as session:
        async with session.begin():
            tenant = Tenant(id=tenant_id, name="Security Test Tenant")
            user = User(id=user_id, email="test@example.com", tenant_id=tenant_id)
            session.add_all([tenant, user])
            
    # 1. 调用 CRUD 写入明文 API Key
    async with async_session() as session:
        async with session.begin():
            provider = await upsert_user_provider(
                db=session,
                tenant_id=tenant_id,
                user_id=user_id,
                category="llm",
                provider_name="openai",
                plain_key=plain_api_key
            )
            assert provider.encrypted_key != plain_api_key
            
    # 2. 调用解密查询接口，确认能正确还原为明文
    async with async_session() as session:
        decrypted_key = await get_decrypted_provider_key(
            db=session,
            user_id=user_id,
            category="llm",
            provider_name="openai"
        )
        assert decrypted_key == plain_api_key


@pytest.mark.asyncio
async def test_research_preset_upsert():
    """测试 ResearchPreset 的 Upsert 逻辑"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    tenant_id = str(uuid4())
    user_id = str(uuid4())
    
    async with async_session() as session:
        async with session.begin():
            tenant = Tenant(id=tenant_id, name="Preset Tenant")
            user = User(id=user_id, email="preset@example.com", tenant_id=tenant_id)
            session.add_all([tenant, user])

    async with async_session() as session:
        async with session.begin():
            # 第一次写入
            preset = await upsert_research_preset(
                session, tenant_id, user_id, "我的预设", 
                nodes_config={"test": 1}
            )
            assert preset.nodes_config == {"test": 1}
            
            # 覆盖更新
            preset_updated = await upsert_research_preset(
                session, tenant_id, user_id, "我的预设", 
                nodes_config={"test": 2}
            )
            assert preset_updated.id == preset.id
            assert preset_updated.nodes_config == {"test": 2}


@pytest.mark.asyncio
async def test_user_creation_initialization():
    """测试用户创建时是否自动触发了预设初始化 (Cloning 逻辑)"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 1. 准备租户
        tenant = await get_or_create_tenant(session, "cloning-tenant")
        
        # 2. 创建用户
        user = await create_user(session, "clone@example.com", tenant_id=tenant.id)
        await session.commit()
        
        # 3. 验证是否自动创建了预设 (fast_react/expert_search/research_pipeline)
        stmt = select(ResearchPreset).where(ResearchPreset.user_id == user.id)
        res = await session.execute(stmt)
        presets = res.scalars().all()
        assert len(presets) == 3

        assert any(p.name == "expert_search" for p in presets)
