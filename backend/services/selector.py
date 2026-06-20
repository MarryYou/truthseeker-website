"""智能预设选择器 — Speed 档位制。

根据前端传入的 speed 档位 或 preset_name 直接查找对应预设。
严格遵循 v3.0 规范：fast_react / expert_search / research_pipeline。
"""
from __future__ import annotations
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.db.models import ResearchPreset


async def select_preset(
    db: AsyncSession,
    query: str,
    preset_name: str | None = None,
    user_id: str | None = None,
    tenant_id: str | None = None,
) -> Any:
    """Speed 档位预设选择器。
    
    1. 前端传入 speed 或 preset_name。
    2. 从数据库查找对应预设。
    3. 兜底返回 research_pipeline 预设。
    """
    resolved_name = preset_name or "research_pipeline"

    # ── 1. 精确匹配用户预设 (按名称) ───────────────────────────────────
    stmt = select(ResearchPreset).where(
        ResearchPreset.name == resolved_name,
        ResearchPreset.user_id == user_id,
    )
    res = await db.execute(stmt)
    preset = res.scalars().first()

    if not preset and preset_name:
        # 如果指定了名字但没找到，尝试按用户的默认预设查找
        stmt_fb = select(ResearchPreset).where(
            ResearchPreset.user_id == user_id
        ).order_by(ResearchPreset.is_default.desc())
        res_fb = await db.execute(stmt_fb)
        preset = res_fb.scalars().first()

    if not preset:
        # 最后的兜底：查找系统默认的 research_pipeline
        stmt_sys = select(ResearchPreset).where(
            ResearchPreset.name == "research_pipeline",
            ResearchPreset.user_id == user_id
        )
        res_sys = await db.execute(stmt_sys)
        preset = res_sys.scalars().first()

    return preset
