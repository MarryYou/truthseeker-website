import pytest
from uuid import uuid4
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from backend.db.engine import async_engine
# 导入 ORM 3.0 模型
from backend.db.models import Base, Tenant, User, UserProvider, UserModelAsset, ResearchPreset, ResearchSession


import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """每个测试运行前自动创建所有表，运行后自动销毁，确保测试隔离"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_tenant_and_user_creation():
    """测试 Tenant 和 User 模型的基础插入及外键级联"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    
    tenant_id = str(uuid4())
    user_id = str(uuid4())
    
    async with async_session() as session:
        async with session.begin():
            # 1. 创建租户
            tenant = Tenant(id=tenant_id, name="Test Tenant", external_id="ext-tenant-1")
            # 2. 创建用户并关联租户
            user = User(
                id=user_id,
                email="test@example.com",
                hashed_password="pbkdf2:sha256:...",
                tenant_id=tenant_id
            )
            session.add_all([tenant, user])
            
    # 验证数据是否持久化并可以关联查询
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        db_user = result.scalar_one()
        assert db_user.email == "test@example.com"
        assert db_user.tenant_id == tenant_id
        
        # 验证反向关系 (此时默认是 lazyload)
        result_tenant = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        db_tenant = result_tenant.scalar_one()
        assert db_tenant.name == "Test Tenant"


@pytest.mark.asyncio
async def test_user_provider_crud_and_unique_constraint():
    """测试 UserProvider 凭证存储及唯一性约束"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    
    tenant_id = str(uuid4())
    user_id = str(uuid4())
    provider_id1 = str(uuid4())
    provider_id2 = str(uuid4())
    encrypted_data = "encrypted-aes-api-key-string"
    
    async with async_session() as session:
        async with session.begin():
            tenant = Tenant(id=tenant_id, name="Provider Tenant")
            user = User(id=user_id, email="provider@example.com", tenant_id=tenant_id)
            provider = UserProvider(
                id=provider_id1,
                tenant_id=tenant_id,
                user_id=user_id,
                category="llm",
                provider_name="openai",
                encrypted_key=encrypted_data
            )
            session.add_all([tenant, user, provider])
            
    async with async_session() as session:
        result = await session.execute(
            select(UserProvider).where(UserProvider.id == provider_id1)
        )
        db_provider = result.scalar_one()
        assert db_provider.category == "llm"
        assert db_provider.provider_name == "openai"
        assert db_provider.encrypted_key == encrypted_data
        assert isinstance(db_provider.created_at, datetime)
        
    # 唯一索引约束校验: 同一用户、同一分类、同一提供商名
    async with async_session() as session:
        provider_dup = UserProvider(
            id=provider_id2,
            tenant_id=tenant_id,
            user_id=user_id,
            category="llm",
            provider_name="openai",
            encrypted_key="another-key"
        )
        session.add(provider_dup)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_user_model_asset_creation():
    """测试 UserModelAsset 资产层模型"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    
    tenant_id = str(uuid4())
    user_id = str(uuid4())
    asset_id = str(uuid4())
    
    async with async_session() as session:
        async with session.begin():
            tenant = Tenant(id=tenant_id, name="Asset Tenant")
            user = User(id=user_id, email="asset@example.com", tenant_id=tenant_id)
            asset = UserModelAsset(
                id=asset_id,
                tenant_id=tenant_id,
                user_id=user_id,
                provider_name="deepseek",
                model_name="deepseek-chat",
                display_name="DeepSeek V3",
                capabilities=["vision"]
            )
            session.add_all([tenant, user, asset])

    async with async_session() as session:
        result = await session.execute(select(UserModelAsset).where(UserModelAsset.id == asset_id))
        db_asset = result.scalar_one()
        assert db_asset.provider_name == "deepseek"
        assert db_asset.model_name == "deepseek-chat"
        assert "vision" in db_asset.capabilities


@pytest.mark.asyncio
async def test_research_preset_nodes_config():
    """测试 ResearchPreset 的 nodes_config JSON 字段存储"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    
    preset_id = str(uuid4())
    config_data = {
        "stages": {
            "search": {"asset_id": "some-asset-uuid", "params": {"max_rounds": 3}}
        },
        "business": {"report_format": "markdown"}
    }
    
    async with async_session() as session:
        async with session.begin():
            preset = ResearchPreset(
                id=preset_id,
                name="Test Preset",
                nodes_config=config_data
            )
            session.add(preset)
            
    async with async_session() as session:
        result = await session.execute(select(ResearchPreset).where(ResearchPreset.id == preset_id))
        db_preset = result.scalar_one()
        assert db_preset.nodes_config["business"]["report_format"] == "markdown"
        assert db_preset.nodes_config["stages"]["search"]["params"]["max_rounds"] == 3


@pytest.mark.asyncio
async def test_research_cascade_delete():
    """测试 Research 级联删除，删除用户时同步删除研究任务"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    
    tenant_id = str(uuid4())
    user_id = str(uuid4())
    research_id = str(uuid4())
    
    async with async_session() as session:
        async with session.begin():
            tenant = Tenant(id=tenant_id, name="Cascade Tenant")
            user = User(id=user_id, email="cascade@example.com", tenant_id=tenant_id)
            research = ResearchSession(
                id=research_id,
                user_id=user_id,
                tenant_id=tenant_id,
                status="running"
            )

            session.add_all([tenant, user, research])
            
    # 删除用户
    async with async_session() as session:
        async with session.begin():
            result = await session.execute(select(User).where(User.id == user_id))
            user_to_delete = result.scalar_one()
            await session.delete(user_to_delete)
            
    # 验证 Research 已被级联删除
    async with async_session() as session:
        result_research = await session.execute(select(ResearchSession).where(ResearchSession.id == research_id))
        assert result_research.scalar_one_or_none() is None

