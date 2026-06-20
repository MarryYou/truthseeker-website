"""FastAPI Dependencies for research validation and shared logic."""
from __future__ import annotations
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_db
from backend.db.models import ResearchSession, ResearchPreset, UserModelAsset, UserProvider
from backend.api.auth import get_current_user
from backend.pipeline.constants import DEFAULT_ACTIVE_ENGINES




async def get_research_record(
    research_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, str] = Depends(get_current_user),
) -> ResearchSession:
    """Fetch and validate access to a research record."""
    user_id = current_user["user_id"]
    tenant_id = current_user["tenant_id"]
    
    stmt = select(ResearchSession).where(
        ResearchSession.id == research_id,
        ResearchSession.tenant_id == tenant_id,
        ResearchSession.user_id == user_id
    )
    record = (await db.execute(stmt)).scalar_one_or_none()
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research record not found or access denied."
        )
    return record


class ResearchConfigValidator:
    """Validator for research presets and associated credentials."""
    
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id

    async def validate(self, preset: ResearchPreset) -> bool:
        """Perform full validation of a preset's assets and API keys."""
        if not preset or not preset.nodes_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Research preset configuration is missing or invalid."
            )

        stages_config = preset.nodes_config.get("stages", {})
        core_stages = ["understanding", "search", "verification", "report"]
        
        # 1. Validate LLM Assets and Credentials
        base_tier = preset.nodes_config.get("business", {}).get("speed", "research_pipeline")

        # 需要验证的阶段：4 个核心子阶段 + 当前基准模式阶段
        validation_stages = list(core_stages)
        if base_tier not in validation_stages:
            validation_stages.append(base_tier)

        for stage in validation_stages:
            # 降级逻辑：子阶段 -> 基准 Tier -> research_pipeline
            node_cfg = stages_config.get(stage)
            if not node_cfg or not node_cfg.get("asset_id"):
                # 如果是子阶段，尝试降级
                if stage in core_stages:
                    node_cfg = stages_config.get(base_tier)
                    if not node_cfg or not node_cfg.get("asset_id"):
                        node_cfg = stages_config.get("research_pipeline")
                else:
                    # base_tier（如 "research_pipeline"）是速度档位名，不是独立 stage，跳过
                    # 其子阶段已在 core_stages 中验证
                    continue
            
            if not node_cfg or not node_cfg.get("asset_id"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"研究预设配置不完整：阶段 '{stage}' 未直接绑定且未配置有效模式降级模型。请前往设置页完成配置。"
                )

            
            asset_id = node_cfg["asset_id"]
            asset = await self.db.get(UserModelAsset, asset_id)
            if not asset:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"阶段 '{stage}' 引用的模型资产 (ID: {asset_id}) 已被删除或不存在。"
                )
            
            stmt = select(UserProvider).where(
                UserProvider.user_id == self.user_id,
                UserProvider.category == "llm",
                UserProvider.provider_name == asset.provider_name
            )
            provider = (await self.db.execute(stmt)).scalar_one_or_none()
            if not provider or not provider.encrypted_key:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"缺少模型供应商 '{asset.provider_name.upper()}' 的 API Key，请在设置页检查凭证。"
                )

        # 2. Validate Search Engine Credentials
        # 兼容性处理：如果 search 阶段没参数，取默认引擎
        search_node_cfg = stages_config.get("search") or stages_config.get("research_pipeline") or {}
        search_params = search_node_cfg.get("params", {})
        active_engines = search_params.get("active_engines", DEFAULT_ACTIVE_ENGINES)
        for engine in active_engines:
            stmt = select(UserProvider).where(
                UserProvider.user_id == self.user_id,
                UserProvider.category == "search",
                UserProvider.provider_name == engine
            )
            provider = (await self.db.execute(stmt)).scalar_one_or_none()
            if not provider or not provider.encrypted_key:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"API Key for search engine '{engine.upper()}' is missing."
                )
        return True


async def get_config_validator(
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, str] = Depends(get_current_user),
) -> ResearchConfigValidator:
    """FastAPI dependency to provide a ResearchConfigValidator."""
    return ResearchConfigValidator(db, current_user["user_id"])
