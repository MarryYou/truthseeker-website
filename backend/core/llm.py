from __future__ import annotations
import asyncio
import time
from typing import Any, cast
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cachetools import TTLCache
from backend.pipeline.constants import DEFAULT_MAX_TOKENS, DEFAULT_LLM_TIMEOUT
from backend.core.registry import LLM_PROVIDER_BASE_URLS
from backend.db.models import ResearchPreset, UserModelAsset, UserProvider
from backend.db.crud import get_decrypted_provider_key
from backend.db.engine import async_session
from backend.utils.redis import get_redis
from backend.core.logging import logger

# 缓存容器，格式："{user_id}:{preset_id}:{stage}" -> BaseChatModel实例
# 限制最多缓存 100 个 LLM 实例，有效期 10 分钟 (600秒)
_llm_cache: TTLCache = TTLCache(maxsize=100, ttl=600)


class _TimedLLMWrapper:
    """全局 LLM 调用耗时日志包装器。

    包裹 BaseChatModel 实例，拦截所有 ainvoke 调用并记录耗时。
    不影响原生 LLM 接口——所有未拦截的属性/方法自动委托给底层实例。
    """

    def __init__(self, llm: BaseChatModel, stage: str, model_name: str) -> None:
        self._llm = llm
        self._stage = stage
        self._model_name = model_name

    async def ainvoke(self, messages: list, **kwargs: Any) -> Any:
        start = time.time()
        try:
            result = await self._llm.ainvoke(messages, **kwargs)
            elapsed = round(time.time() - start, 2)
            logger.info("LLM ainvoke | stage={} model={} duration={}s",
                        self._stage, self._model_name, elapsed)
            return result
        except Exception:
            elapsed = round(time.time() - start, 2)
            logger.warning("LLM ainvoke 失败 | stage={} model={} duration={}s",
                           self._stage, self._model_name, elapsed)
            raise

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)

async def _get_full_model_config(
    db: AsyncSession, stage: str, user_id: str, preset_id: str | None = None
) -> dict:
    """
    【严格寻址模式】从新的 Preset.nodes_config 结构加载配置。
    结构：{"stages": {"understanding": {"asset_id": "...", "temperature": 0.1, "params": {...}}, ...}}
    """
    if not preset_id:
        raise ValueError("未指定研究预设 (Preset ID)，无法确定执行配置")
    
    preset = await db.get(ResearchPreset, preset_id)
    if not preset or not preset.nodes_config:
        raise ValueError(f"指定的预设不存在或配置为空: {preset_id}")

    # 1. 严格寻址 (不再使用任何 Fallback)
    stages = preset.nodes_config.get("stages", {})
    node_cfg = stages.get(stage)

    if not node_cfg or not node_cfg.get("asset_id"):
        raise RuntimeError(
            f"预设 '{preset.name}' 的 [{stage}] 阶段未绑定模型资产。"
            f"请在「设置 → 研究工作流」中为该阶段选择一个已注册的模型。"
        )

    asset_id = node_cfg["asset_id"]

    # 2. 检查资产与凭证
    asset = await db.get(UserModelAsset, asset_id)
    if not asset:
        raise RuntimeError(f"预设引用的模型资产 (ID: {asset_id}) 已被删除或不存在")

    decrypted_key = await get_decrypted_provider_key(db, user_id, "llm", asset.provider_name)
    if not decrypted_key:
        raise RuntimeError(f"供应商 {asset.provider_name} 的 API Key 未配置或已失效，请在设置页检查凭证")

    # 3. 获取 Base URL
    stmt_prov = select(UserProvider).where(
        UserProvider.user_id == user_id,
        UserProvider.category == "llm",
        UserProvider.provider_name == asset.provider_name
    )
    res_prov = await db.execute(stmt_prov)
    provider = res_prov.scalar_one_or_none()
    base_url = provider.base_url if provider else None

    return {
        "provider": asset.provider_name,
        "model": asset.model_name,
        "api_key": decrypted_key,
        "base_url": base_url,
        "temperature": node_cfg.get("temperature", 0.1),
        "max_tokens": node_cfg.get("max_tokens", DEFAULT_MAX_TOKENS),
        "timeout": node_cfg.get("timeout", DEFAULT_LLM_TIMEOUT),
        "params": node_cfg.get("params", {}),
    }

def _create_llm_from_resolved_config(cfg: dict) -> BaseChatModel:
    provider = cfg["provider"]
    model = cfg["model"]
    api_key = cfg["api_key"]
    base_url = cfg["base_url"]
    
    model_provider = "openai" if provider in ("deepseek", "dashscope") else provider
    
    if not base_url:
        base_url = LLM_PROVIDER_BASE_URLS.get(provider, "https://api.openai.com/v1")

    kwargs: dict[str, Any] = {
        "model": model,
        "model_provider": model_provider,
        "api_key": api_key,
        "base_url": base_url,
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
        "timeout": cfg.get("timeout", DEFAULT_LLM_TIMEOUT),
    }
    
    return init_chat_model(**kwargs)

async def get_llm_for_stage(
    stage: str, user_id: str, preset_id: str | None = None, **kwargs
) -> BaseChatModel:
    """获取指定阶段的 LLM 实例 (严格模式)，自动包裹全局耗时日志。"""
    cache_key = f"{user_id}:{preset_id}:{stage}"

    cached = _llm_cache.get(cache_key)
    if cached is not None:
        return cached

    async with async_session() as db:
        config = await _get_full_model_config(db, stage, user_id, preset_id)

    llm_instance = _create_llm_from_resolved_config(config)
    model_name = config.get("model", "unknown")
    wrapper = _TimedLLMWrapper(llm_instance, stage, model_name)

    _llm_cache[cache_key] = wrapper
    return wrapper


def invalidate_llm_cache(
    user_id: str,
    preset_id: str | None = None,
    tenant_id: str | None = None,
    stage: str | None = None,
) -> None:
    """清除指定用户的 LLM 缓存实例 (支持多维度细粒度过滤)"""
    prefix = f"{user_id}:"
    keys_to_remove: list[str] = []
    
    for k in list(_llm_cache.keys()):
        if not k.startswith(prefix):
            continue
            
        parts = k.split(":")
        if len(parts) < 3:
            continue
            
        cached_preset_id = parts[1]
        cached_stage = parts[2]
        
        # 1. 过滤 preset_id (在 cache key 中以 "None" 字符串存在时判定为 None)
        if preset_id is not None and cached_preset_id != str(preset_id):
            continue
            
        # 2. 过滤 stage
        if stage is not None and cached_stage != stage:
            continue
            
        keys_to_remove.append(k)
        
    for k in keys_to_remove:
        _llm_cache.pop(k, None)


# ============================================================
# 4. 核心 API: 测试大模型可用性
# ============================================================

async def test_llm_connection(cfg: dict, plain_key: str) -> bool:
    """测试连接可用性 (cfg 格式兼容 ProviderUpsert 数据)"""
    temp_cfg = {
        "provider": cfg["provider"],
        "model": cfg.get("model") or "ping",
        "api_key": plain_key,
        "base_url": cfg.get("params", {}).get("base_url") or cfg.get("base_url"),
        "temperature": 0.1,
        "max_tokens": 10  # 测试连接只需极少量 Token
    }
    client = _create_llm_from_resolved_config(temp_cfg)
    await client.ainvoke([HumanMessage(content="ping")], config=cast(Any, {"timeout": 10}))
    return True


# ============================================================
# 5. 缓存主动失效
# ============================================================


async def publish_llm_cache_invalidation(user_id: str) -> None:
    """发布 LLM 缓存失效广播到 Redis，通知所有 Worker 清理缓存。"""
    try:
        redis = await get_redis()
        await redis.publish("ts:config:invalidate", user_id)
    except Exception:
        logger.warning("Failed to publish cache invalidation to Redis | user_id={}", user_id)


async def start_llm_cache_invalidation_listener() -> None:
    """启动 Redis PubSub 监听，订阅 LLM 缓存失效广播。

    供 Worker 进程在启动时调用，当用户在 API 端修改模型配置后，
    自动清理本进程的 LLM 缓存。
    """
    logger.info("LLM 缓存失效监听器启动成功，订阅频道: ts:config:invalidate")
    while True:
        pubsub = None
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe("ts:config:invalidate")

            while True:
                message = await pubsub.get_message(timeout=10.0, ignore_subscribe_messages=True)
                if message is not None and message.get("type") == "message":
                    raw_data = message.get("data")
                    if raw_data is None:
                        continue
                    if isinstance(raw_data, bytes):
                        raw = raw_data.decode("utf-8")
                    elif isinstance(raw_data, str):
                        raw = raw_data
                    else:
                        raw = str(raw_data)
                    invalidate_llm_cache(user_id=raw)
                    logger.debug("LLM 缓存已失效 | user_id={}", raw)
        except asyncio.CancelledError:
            logger.info("LLM 缓存失效监听器已正常取消。")
            break
        except asyncio.TimeoutError:
            logger.warning("LLM 缓存失效监听器连接超时，5 秒后重试")
            await asyncio.sleep(5.0)
        except Exception as e:
            logger.warning("LLM 缓存失效监听器异常，5 秒后重试 | error={}", e)
            await asyncio.sleep(5.0)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.close()
                except Exception:
                    pass