from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.db.engine import get_db
from backend.db import crud
from backend.api.auth import get_current_user
from backend.api.schemas.config import (
    ProviderUpsert, ModelAssetUpsert, ResearchPresetUpsert,
    PresetCreate, ConnectionTest
)
from backend.services import settings_service
from backend.core.registry import (
    NODE_PARAMS_SCHEMA, PRESET_PARAMS_SCHEMA,
    VALID_LLM_PROVIDERS, VALID_SEARCH_ENGINES,
    VALID_SECRET_CATEGORIES, VALID_SECRET_NAMES,
    VALID_SPEED_LEVELS,
    VALID_VERIFICATION_LEVELS,
)
from backend.pipeline.constants import SPEED_PROFILES

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

# ── 1. 配置 Schema 导出 (保持不变) ─────────────────────
@router.get("/schema")
async def get_settings_schema():
    def serialize_schema(schema_dict):
        result = {}
        for key, config in schema_dict.items():
            serialized = config.copy()
            t = serialized.get("type")
            if t is int:
                serialized["type"] = "int"
            elif t is float:
                serialized["type"] = "float"
            elif t is bool:
                serialized["type"] = "bool"
            elif t is str:
                serialized["type"] = "str"
            elif t is dict:
                serialized["type"] = "dict"
            elif t is list:
                serialized["type"] = "list"
            elif t == "list":
                pass
            elif t == "str":
                pass

            if "item_type" in serialized:
                it = serialized["item_type"]
                if it is str:
                    serialized["item_type"] = "str"
                elif it is int:
                    serialized["item_type"] = "int"
            result[key] = serialized
        return result

    speed_profiles_metadata = {
        k: {
            "label": v.get("label", k),
            "description": v.get("description", "")
        }
        for k, v in SPEED_PROFILES.items()
    }

    return {
        "node_params": {k: serialize_schema(v) for k, v in NODE_PARAMS_SCHEMA.items()},
        "preset_params": serialize_schema(PRESET_PARAMS_SCHEMA),
        "enums": {
            "llm_providers": list(VALID_LLM_PROVIDERS),
            "search_engines": list(VALID_SEARCH_ENGINES),
            "secret_categories": list(VALID_SECRET_CATEGORIES),
            "secret_names": {k: list(v) for k, v in VALID_SECRET_NAMES.items()},
            "speed_levels": list(VALID_SPEED_LEVELS),
            "verification_levels": list(VALID_VERIFICATION_LEVELS),
        },
        "speed_profiles": speed_profiles_metadata
    }

# ── 2. 凭证层 (Secrets) ───────────────────────────────────────────

@router.get("/secrets")
async def list_secrets(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await settings_service.list_secrets_logic(db, current_user["user_id"])


@router.put("/secrets")
async def upsert_secret(
    data: ProviderUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await settings_service.upsert_secret_logic(
        db, current_user["tenant_id"], current_user["user_id"], data
    )


@router.post("/test-connection")
async def test_secret_connection(
    data: ConnectionTest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await settings_service.test_secret_connection_logic(
        db, current_user["user_id"], data
    )

# ── 3. 资产层 (Assets) ──────────────────────────────────────────────

@router.get("/assets")
async def list_assets(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await crud.list_model_assets(db, current_user["user_id"])

@router.put("/assets")
async def register_asset(
    data: ModelAssetUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await settings_service.register_asset_logic(
        db, current_user["tenant_id"], current_user["user_id"], data
    )


@router.delete("/assets/{asset_id}")
async def delete_asset(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await settings_service.delete_asset_logic(
        db, current_user["user_id"], asset_id
    )

# ── 4. 策略层 (Presets) ─────────────────────────────────────────────

@router.get("/presets")
async def list_presets(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await crud.list_research_presets(db, current_user["user_id"])

@router.put("/presets")
async def upsert_preset(
    data: ResearchPresetUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await settings_service.upsert_preset_logic(
        db, current_user["tenant_id"], current_user["user_id"], data
    )


@router.post("/presets")
async def create_preset(
    data: PresetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await settings_service.create_preset_logic(
        db, current_user["tenant_id"], current_user["user_id"], data
    )


@router.delete("/presets/{preset_id}")
async def delete_preset(
    preset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await settings_service.delete_preset_logic(
        db, current_user["user_id"], preset_id
    )


# ── 5. 交互增强 (Fetch Models) ──────────────────────────────────────

class FetchModelsRequest(BaseModel):
    plain_key: str | None = None
    base_url: str | None = None

@router.post("/providers/{provider_name}/fetch-models")
async def proxy_fetch_models(
    provider_name: str,
    data: FetchModelsRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    plain_key = data.plain_key if data else None
    base_url = data.base_url if data else None
    return await settings_service.proxy_fetch_models_logic(
        db, current_user["user_id"], provider_name, plain_key, base_url
    )
