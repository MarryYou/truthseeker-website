from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from backend.db import crud
from backend.core.llm import invalidate_llm_cache, publish_llm_cache_invalidation
from backend.services.provider_service import test_provider_connection, format_connection_error, fetch_provider_models
from backend.db.models import UserProvider, UserModelAsset, ResearchPreset, ResearchSession
from backend.api.schemas.config import ProviderUpsert, ModelAssetUpsert, ResearchPresetUpsert, PresetCreate, ConnectionTest
from backend.core.registry import VALID_SECRET_NAMES, VALID_LLM_PROVIDERS, LLM_PROVIDER_BASE_URLS

async def list_secrets_logic(db: AsyncSession, user_id: str) -> list[dict]:
    """获取所有已配置或支持的供应商状态"""
    user_providers = await crud.list_user_providers(db, user_id)
    res = []
    configured_map = { (p.category, p.provider_name): p for p in user_providers }
    for cat, names in VALID_SECRET_NAMES.items():
        for name in names:
            p = configured_map.get((cat, name))
            res.append({
                "category": cat,
                "provider_name": name,
                "is_active": p.is_active if p else False,
                "is_configured": p is not None,
                "base_url": p.base_url if p else None,
                "updated_at": p.updated_at.isoformat() if p else None
            })
    return res

async def upsert_secret_logic(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    data: ProviderUpsert
) -> dict[str, str]:
    stmt = select(UserProvider).where(
        UserProvider.user_id == user_id,
        UserProvider.category == data.category,
        UserProvider.provider_name == data.provider_name
    )
    res = await db.execute(stmt)
    provider = res.scalar_one_or_none()

    if data.plain_key is None:
        if not provider:
            raise HTTPException(400, detail=f"未配置该供应商的有效密钥: {data.provider_name}")
        provider.base_url = data.base_url
        provider.updated_at = datetime.now(timezone.utc)
    
    elif data.plain_key == "":
        stmt_assets = select(UserModelAsset.id).where(
            UserModelAsset.provider_name == data.provider_name,
            UserModelAsset.user_id == user_id
        )
        res_assets = await db.execute(stmt_assets)
        asset_ids = list(res_assets.scalars().all())
        
        stmt_presets = select(ResearchPreset).where(
            ResearchPreset.user_id == user_id
        )
        res_presets = await db.execute(stmt_presets)
        presets = list(res_presets.scalars().all())
        
        for p in presets:
            if p.nodes_config:
                stages = p.nodes_config.get("stages", {})
                for stage_name, stage_cfg in stages.items():
                    if stage_cfg.get("asset_id") in asset_ids:
                        raise HTTPException(
                            400,
                            detail=f"无法注销服务连接：关联的模型资产目前正被预设【{p.name}】的【{stage_name}】阶段绑定。请先在管线编排中解绑相关模型。"
                        )
        if provider:
            await db.delete(provider)
            
    else:
        try:
            connected = await test_provider_connection(
                data.category, data.provider_name, data.plain_key, data.base_url
            )
            if not connected:
                raise ValueError("连接测试未通过")
        except Exception as e:
            friendly_msg = format_connection_error(e, data.provider_name)
            raise HTTPException(400, detail=friendly_msg) from e
        
        await crud.upsert_user_provider(
            db, tenant_id, user_id, data.category, data.provider_name, data.plain_key, data.base_url
        )
        
    if data.category == "llm":
        invalidate_llm_cache(tenant_id=tenant_id, user_id=user_id)
        await publish_llm_cache_invalidation(user_id)
        
    await db.commit()
    return {"message": "供应商凭证更新成功"}

async def test_secret_connection_logic(
    db: AsyncSession,
    user_id: str,
    data: ConnectionTest
) -> dict[str, Any]:
    category = "search" if data.provider_name in ("tavily", "bocha", "zhihu") else "llm"
    
    final_key = data.plain_key
    if not final_key or final_key == "••••••••••••••••":
        final_key = await crud.get_decrypted_provider_key(db, user_id, category, data.provider_name)
        if not final_key:
            raise HTTPException(400, detail=f"无法测试连接：未提供新密钥，且数据库中未找到供应商【{data.provider_name.upper()}】的有效配置。")

    start = time.time()
    try:
        connected = await test_provider_connection(
            category, 
            data.provider_name, 
            final_key, 
            data.base_url, 
            model_name=data.model_name,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            timeout=data.timeout
        )
        latency = int((time.time() - start) * 1000)
        return {"connected": connected, "latency": latency}
    except Exception as e:
        friendly_msg = format_connection_error(e, data.provider_name)
        raise HTTPException(400, detail=friendly_msg) from e

async def register_asset_logic(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    data: ModelAssetUpsert
) -> dict[str, str]:
    if data.provider_name not in VALID_LLM_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"不合法的模型注册：供应商【{data.provider_name}】非有效的大语言模型 (LLM) 提供商。搜索引擎直接调用，无需在此注册资产。"
        )

    providers = await crud.list_user_providers(db, user_id)
    target_p = next((p for p in providers if p.provider_name == data.provider_name), None)
    
    await crud.upsert_model_asset(
        db, tenant_id, user_id, 
        data.provider_name, data.model_name, 
        provider_id=target_p.id if target_p else None,
        display_name=data.display_name,
        capabilities=data.capabilities,
        is_system_default=data.is_system_default
    )
    await db.commit()
    invalidate_llm_cache(user_id)
    await publish_llm_cache_invalidation(user_id)
    return {"message": "模型资产注册成功"}

async def delete_asset_logic(
    db: AsyncSession,
    user_id: str,
    asset_id: str
) -> dict[str, str]:
    asset = await db.get(UserModelAsset, asset_id)
    if not asset or asset.user_id != user_id:
        raise HTTPException(404, detail="未找到指定的模型资产，或您无权访问")
        
    stmt_presets = select(ResearchPreset).where(
        ResearchPreset.user_id == user_id
    )
    res_presets = await db.execute(stmt_presets)
    presets = list(res_presets.scalars().all())
    
    for p in presets:
        if p.nodes_config:
            stages = p.nodes_config.get("stages", {})
            for stage_name, stage_cfg in stages.items():
                if stage_cfg.get("asset_id") == asset_id:
                    raise HTTPException(
                        400,
                        detail=f"无法注销该模型资产：该模型目前已被预设【{p.name}】的【{stage_name}】阶段绑定。请先在管线编排中解绑相关模型。"
                    )
                    
    await db.delete(asset)
    await db.commit()
    invalidate_llm_cache(user_id)
    await publish_llm_cache_invalidation(user_id)
    return {"message": "模型资产注销成功"}

async def upsert_preset_logic(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    data: ResearchPresetUpsert
) -> dict[str, str]:
    await crud.upsert_research_preset(
        db, tenant_id, user_id,
        data.name, data.description, data.nodes_config,
        is_system_default=data.is_system_default,
        is_default=data.is_default,
    )
    await db.commit()
    invalidate_llm_cache(user_id)
    await publish_llm_cache_invalidation(user_id)
    return {"message": "预设策略保存成功"}

async def create_preset_logic(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    data: PresetCreate
) -> dict[str, Any]:
    stmt = select(ResearchPreset).where(
        ResearchPreset.user_id == user_id,
        ResearchPreset.name == data.name
    )
    existing = await db.execute(stmt)
    if existing.scalar_one_or_none():
        raise HTTPException(400, detail=f"已存在同名预设【{data.name}】，请更换名称")

    preset = ResearchPreset(
        id=crud._generate_id(),
        tenant_id=tenant_id,
        user_id=user_id,
        name=data.name,
        description=data.description,
        nodes_config={"business": {"allow_ai_override": False}, "stages": {}},
        is_system_default=False,
        is_default=False,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return {
        "id": preset.id,
        "name": preset.name,
        "description": preset.description,
        "nodes_config": preset.nodes_config,
        "is_system_default": preset.is_system_default,
        "is_default": preset.is_default,
    }

async def delete_preset_logic(
    db: AsyncSession,
    user_id: str,
    preset_id: str
) -> dict[str, str]:
    preset = await db.get(ResearchPreset, preset_id)
    if not preset or preset.user_id != user_id:
        raise HTTPException(404, detail="未找到指定的预设，或您无权访问")

    if preset.is_system_default:
        raise HTTPException(403, detail="系统内置预设不可删除")

    stmt_sessions = select(ResearchSession).where(ResearchSession.preset_id == preset_id)
    res = await db.execute(stmt_sessions)
    if res.scalars().first():
        raise HTTPException(400, detail="该预设已被研究会话引用，无法删除。请先删除相关会话。")

    await db.delete(preset)
    await db.commit()
    return {"message": "预设删除成功"}

async def proxy_fetch_models_logic(
    db: AsyncSession,
    user_id: str,
    provider_name: str,
    plain_key: str | None = None,
    base_url: str | None = None
) -> list[Any]:
    key = plain_key
    if not key or key == "••••••••••••••••":
        key = await crud.get_decrypted_provider_key(db, user_id, "llm", provider_name)
    
    if not key:
        raise HTTPException(400, detail="未提供有效的 API 密钥，且数据库中未找到配置。")

    if not base_url:
        user_providers = await crud.list_user_providers(db, user_id)
        provider = next((p for p in user_providers if p.provider_name == provider_name), None)
        base_url = provider.base_url if provider and provider.base_url else LLM_PROVIDER_BASE_URLS.get(provider_name, "https://api.openai.com/v1")

    try:
        return await fetch_provider_models(provider_name, key, base_url)
    except Exception as e:
        raise HTTPException(400, detail=f"拉取模型失败: {str(e)}") from e
