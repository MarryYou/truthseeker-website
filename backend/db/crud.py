"""业务数据 CRUD 操作封装 - ORM 3.0 简化版架构"""
from __future__ import annotations
from datetime import datetime, timezone
import uuid
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.models import Tenant, User, UserProvider, UserModelAsset, ResearchPreset, ResearchSession, ResearchTask
from backend.core.registry import VALID_LLM_PROVIDERS
from backend.core.security import encrypt_api_key, decrypt_api_key
from backend.core.logging import logger

def _generate_id() -> str:
    return str(uuid.uuid4())


# ============================================================
# 1. UserProvider (凭证层 CRUD)
# ============================================================

async def upsert_user_provider(
    db: AsyncSession, tenant_id: str, user_id: str, category: str, provider_name: str, plain_key: str, base_url: str | None = None
) -> UserProvider:
    """UPSERT 供应商凭证：入参明文，加密落盘"""
    encrypted_val = encrypt_api_key(plain_key)
    
    stmt = select(UserProvider).where(
        UserProvider.user_id == user_id,
        UserProvider.category == category,
        UserProvider.provider_name == provider_name
    )
    result = await db.execute(stmt)
    provider = result.scalar_one_or_none()
    
    if provider:
        provider.encrypted_key = encrypted_val
        provider.base_url = base_url
        provider.updated_at = datetime.now(timezone.utc)
    else:
        provider = UserProvider(
            id=_generate_id(),
            tenant_id=tenant_id,
            user_id=user_id,
            category=category,
            provider_name=provider_name,
            encrypted_key=encrypted_val,
            base_url=base_url
        )
        db.add(provider)
        
    await db.flush()
    await db.refresh(provider)
    return provider


async def get_decrypted_provider_key(
    db: AsyncSession, user_id: str, category: str, provider_name: str
) -> str | None:
    """获取解密后的供应商 API Key"""
    stmt = select(UserProvider).where(
        UserProvider.user_id == user_id,
        UserProvider.category == category,
        UserProvider.provider_name == provider_name
    )
    result = await db.execute(stmt)
    provider = result.scalar_one_or_none()
    if provider:
        return decrypt_api_key(provider.encrypted_key)
    return None


async def list_user_providers(db: AsyncSession, user_id: str) -> list[UserProvider]:
    stmt = select(UserProvider).where(UserProvider.user_id == user_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ============================================================
# 2. UserModelAsset (资产层 CRUD)
# ============================================================

async def upsert_model_asset(
    db: AsyncSession, tenant_id: str, user_id: str | None, provider_name: str, model_name: str, 
    provider_id: str | None = None, display_name: str | None = None, capabilities: list[str] | None = None,
    is_system_default: bool = False
) -> UserModelAsset:
    """注册模型资产"""
    stmt = select(UserModelAsset).where(
        UserModelAsset.user_id == user_id,
        UserModelAsset.provider_name == provider_name,
        UserModelAsset.model_name == model_name
    )
    result = await db.execute(stmt)
    asset = result.scalar_one_or_none()
    
    # 智能自愈：若没传功能标签或为空，且服务商属于大模型，默认分配 ["llm"]
    resolved_caps = capabilities
    if not resolved_caps and provider_name in VALID_LLM_PROVIDERS:
        resolved_caps = ["llm"]

    if asset:
        asset.provider_id = provider_id
        asset.display_name = display_name
        asset.capabilities = resolved_caps
        asset.is_system_default = is_system_default
    else:
        asset = UserModelAsset(
            id=_generate_id(),
            tenant_id=tenant_id,
            user_id=user_id,
            provider_id=provider_id,
            provider_name=provider_name,
            model_name=model_name,
            display_name=display_name,
            capabilities=resolved_caps,
            is_system_default=is_system_default
        )
        db.add(asset)
        
    await db.flush()
    await db.refresh(asset)
    return asset


async def list_model_assets(db: AsyncSession, user_id: str) -> list[UserModelAsset]:
    """列出可用资产：仅限用户私有资产 (包含老数据 capabilities 标签后台物理自愈)"""
    stmt = select(UserModelAsset).where(UserModelAsset.user_id == user_id)
    result = await db.execute(stmt)
    assets = list(result.scalars().all())
    
    # 后台静默自愈老数据：如果老 LLM 模型资产 capabilities 为空，自动升级为 ["llm"] 并更新数据库
    modified = False
    for a in assets:
        if not a.capabilities and a.provider_name in VALID_LLM_PROVIDERS:
            a.capabilities = ["llm"]
            modified = True
            
    if modified:
        await db.commit()
        
    return assets


# ============================================================
# 3. ResearchPreset (策略层 CRUD)
# ============================================================

async def upsert_research_preset(
    db: AsyncSession, tenant_id: str, user_id: str | None, name: str, 
    description: str | None = None, nodes_config: dict | None = None,
    is_system_default: bool = False, is_default: bool = False
) -> ResearchPreset:
    stmt = select(ResearchPreset).where(
        ResearchPreset.user_id == user_id,
        ResearchPreset.name == name
    )
    result = await db.execute(stmt)
    preset = result.scalar_one_or_none()
    
    if preset:
        preset.description = description
        preset.nodes_config = nodes_config
        preset.is_system_default = is_system_default
        preset.is_default = is_default
    else:
        preset = ResearchPreset(
            id=_generate_id(),
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            description=description,
            nodes_config=nodes_config,
            is_system_default=is_system_default,
            is_default=is_default
        )
        db.add(preset)
        
    await db.flush()
    await db.refresh(preset)
    return preset


async def get_research_preset(db: AsyncSession, preset_id: str) -> ResearchPreset | None:
    return await db.get(ResearchPreset, preset_id)


async def list_research_presets(db: AsyncSession, user_id: str) -> list[ResearchPreset]:
    """列出可用预设：仅限用户私有预设 (按创建时间升序排列以保证排序稳定)"""
    stmt = select(ResearchPreset).where(ResearchPreset.user_id == user_id).order_by(ResearchPreset.created_at.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ============================================================
# 4. User & Tenant (通用 CRUD)
# ============================================================

async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user(db: AsyncSession, user_id: str) -> User | None:
    return await db.get(User, user_id)


async def create_user(
    db: AsyncSession, email: str, hashed_password: str | None = None,
    external_id: str | None = None, tenant_id: str | None = None,
    full_name: str | None = None, avatar_url: str | None = None,
    role: str = "user"
) -> User:
    if not avatar_url or not avatar_url.strip():
        seed = email.split('@')[0] if email else str(uuid.uuid4())[:8]
        avatar_url = f"https://api.dicebear.com/7.x/identicon/svg?seed={seed}"

    user = User(
        id=_generate_id(),
        email=email,
        hashed_password=hashed_password,
        external_id=external_id,
        tenant_id=tenant_id,
        full_name=full_name,
        avatar_url=avatar_url,
        role=role
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    
    # ⚡ 自动初始化用户的预设框架 (Cloning)
    from backend.db.seed import initialize_user_data
    if tenant_id:
        await initialize_user_data(db, user.id, tenant_id)
        
    return user


async def get_or_create_tenant(
    db: AsyncSession, external_id: str, name: str | None = None
) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.external_id == external_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        tenant = Tenant(
            id=_generate_id(),
            external_id=external_id,
            name=name or external_id
        )
        db.add(tenant)
        await db.flush()
        await db.refresh(tenant)
    return tenant


# ============================================================
# 5. Research Session & Task (研究会话与任务 CRUD)
# ============================================================


async def create_research_session(
    db: AsyncSession, session_id: str, user_id: str, tenant_id: str,
    preset_id: str | None = None, title: str | None = None
) -> ResearchSession:
    """创建研究会话 (容器)"""
    session = ResearchSession(
        id=session_id,
        user_id=user_id,
        tenant_id=tenant_id,
        preset_id=preset_id,
        title=title,
        status="active"
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def get_research_session(db: AsyncSession, session_id: str, tenant_id: str, user_id: str) -> ResearchSession | None:
    """获取会话详情 (包含最新任务列表)"""
    stmt = select(ResearchSession).where(
        ResearchSession.id == session_id,
        ResearchSession.tenant_id == tenant_id,
        ResearchSession.user_id == user_id
    ).options(selectinload(ResearchSession.tasks))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_research_sessions(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    page_size: int = 10,
    keyword: str | None = None
) -> tuple[int, list[ResearchSession]]:
    """列表分页查询"""
    base_query = select(ResearchSession).where(ResearchSession.user_id == user_id)
    if keyword:
        base_query = base_query.where(ResearchSession.title.ilike(f"%{keyword}%"))
    
    count_query = select(func.count()).select_from(base_query.subquery())  # pylint: disable=not-callable
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    items_query = base_query.order_by(ResearchSession.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items_result = await db.execute(items_query)
    items = list(items_result.scalars().all())
    return total, items


async def create_research_task(
    db: AsyncSession, session_id: str, query: str,
    intent_type: str | None = None, task_id: str | None = None,
) -> ResearchTask:
    """为会话创建新任务 (Follow-up)"""
    # 1. 自动计算序号 (Ordinal)
    stmt = select(ResearchTask.ordinal).where(ResearchTask.session_id == session_id).order_by(ResearchTask.ordinal.desc()).limit(1)
    result = await db.execute(stmt)
    last_ordinal = result.scalar_one_or_none()
    new_ordinal = (last_ordinal + 1) if last_ordinal is not None else 0
    
    # 2. 获取预设快照
    snapshot = None
    session_stmt = select(ResearchSession.preset_id).where(ResearchSession.id == session_id)
    session_res = await db.execute(session_stmt)
    preset_id = session_res.scalar_one_or_none()
    if preset_id:
        preset = await db.get(ResearchPreset, preset_id)
        if preset:
            snapshot = preset.nodes_config

    # 3. 创建任务
    real_task_id = task_id or _generate_id()
    task = ResearchTask(
        id=real_task_id,
        session_id=session_id,
        ordinal=new_ordinal,
        query=query,
        intent_type=intent_type,
        run_config_snapshot=snapshot,
        status="running"
    )
    db.add(task)
    
    logger.info("DB Task Created | task_id={} session_id={} ordinal={} intent={}", real_task_id, session_id, new_ordinal, intent_type)

    # 若是第一个任务，同步更新 Session Title
    if new_ordinal == 0:
        await db.execute(update(ResearchSession).where(ResearchSession.id == session_id).values(title=query[:100], status="running"))
    else:
        await db.execute(update(ResearchSession).where(ResearchSession.id == session_id).values(status="running"))
        
    await db.flush()
    await db.refresh(task)
    return task


async def update_research_task(
    db: AsyncSession, task_id: str, **kwargs
) -> None:
    """更新任务产出、状态或步骤"""
    update_data = {**kwargs}
    if "status" in kwargs and kwargs["status"] == "completed":
        update_data["completed_at"] = datetime.now(timezone.utc)
    
    status_msg = f"status={kwargs['status']}" if "status" in kwargs else "metadata_update"
    logger.info("DB Task Update | task_id={} {}", task_id, status_msg)
    
    await db.execute(update(ResearchTask).where(ResearchTask.id == task_id).values(**update_data))
    await db.flush()


async def get_research_task(db: AsyncSession, task_id: str) -> ResearchTask | None:
    return await db.get(ResearchTask, task_id)


async def delete_research_session(
    db: AsyncSession, session_id: str, user_id: str
) -> bool:
    stmt = delete(ResearchSession).where(ResearchSession.id == session_id, ResearchSession.user_id == user_id)
    result = await db.execute(stmt)
    return result.rowcount > 0  # type: ignore

# 兼容性别名
async def get_research(db: AsyncSession, thread_id: str, tenant_id: str, user_id: str):
    return await get_research_session(db, thread_id, tenant_id, user_id)

async def update_research_status(db: AsyncSession, research_id: str, status: str):
    # 此处逻辑略显含糊，暂时映射到更新 Session 状态
    await db.execute(update(ResearchSession).where(ResearchSession.id == research_id).values(status=status))
    await db.flush()
