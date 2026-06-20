from __future__ import annotations
from typing import cast
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.embedding import embed_documents
from backend.core.llm import _get_full_model_config
from backend.core.logging import logger
from sqlalchemy import select
from backend.db.models import ResearchPreset

async def get_embedding_config(
    db: AsyncSession,
    user_id: str | None,
    preset_id: str | None = None
) -> tuple[dict, str | None]:
    """从数据库加载 embedding 配置并获取解密的 API Key"""
    if not user_id:
        user_id = "default"

    if not preset_id and user_id:
        try:
            stmt = select(ResearchPreset).where(ResearchPreset.user_id == user_id).limit(1)
            res = await db.execute(stmt)
            preset = res.scalar_one_or_none()
            if preset:
                preset_id = cast(str, preset.id)
        except Exception as db_err:
            logger.warning("从数据库自动加载 embedding 预设失败，降级为默认配置 | error={}", db_err)

    try:
        cfg = await _get_full_model_config(db, "embedding", user_id, preset_id=preset_id)
        decrypted_api_key = cfg.get("api_key")
        return cfg, decrypted_api_key
    except Exception as db_err:
        raise RuntimeError(f"未配置向量化服务，请检查设置。详情: {db_err}") from db_err

async def embed_documents_with_preset(
    db: AsyncSession,
    texts: list[str],
    user_id: str | None,
    preset_id: str | None = None
) -> list[list[float]]:
    """业务层封装：从数据库 Preset 加载配置并执行向量化"""
    cfg, decrypted_api_key = await get_embedding_config(db, user_id, preset_id)
    return await embed_documents(texts, cfg=cfg, decrypted_api_key=decrypted_api_key)
