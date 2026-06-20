"""数据播种与用户初始化逻辑 — Speed 档位制。

新用户创建时初始化 3 个系统预设 (fast_react / expert_search / research_pipeline)：
  - business: 5 个全局参数 (PRESET_PARAMS_SCHEMA 定义)
  - stages:   6 个阶段骨架 (asset_id=null, params 从 SPEED_PROFILES + NODE_DEFAULTS 派生)
"""
from __future__ import annotations
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.logging import logger
from backend.pipeline.constants import DEFAULT_PRESETS, SPEED_PROFILES, NODE_DEFAULTS
from backend.pipeline.constants import DEFAULT_STAGE_MODELS
from backend.db.crud import upsert_research_preset

MODE_STAGE_MAPPING = {
    "fast_react": ["fast_react"],
    "expert_search": ["expert_search"],
    "research_pipeline": ["understanding", "search", "verification", "report", "embedding"]
}

# ── 节点 → 阶段归属映射（确保参数被归类到正确的 Stage 内部）──────────
_NODE_TO_STAGE: dict[str, str] = {
    "intent_analyze":  "understanding",
    "keyword_expand":  "understanding",
    "multi_search":    "search",
    "filter_results":  "search",
    "cross_verify":    "verification",
    "generate_report": "report",
    # Agent 模式直接映射
    "agent_expert_search": "expert_search",
    "agent_fast_react": "fast_react"
}

def _build_stages_config(preset_name: str) -> dict[str, dict[str, Any]]:
    """构建 mode 专属的 stages 骨架结构。"""
    required_stages = MODE_STAGE_MAPPING.get(preset_name, [])
    stages: dict[str, dict[str, Any]] = {}
    
    for stage in required_stages:
        default_cfg = DEFAULT_STAGE_MODELS.get(stage, {})
        
        # 💡 从 NODE_DEFAULTS 预填充节点参数，否则 UI 读不到默认值
        stage_nodes_params = {}
        for node_type, defaults in NODE_DEFAULTS.items():
            # 兼容 Pipeline 子阶段映射与 Agent 模式直接阶段名映射
            if _NODE_TO_STAGE.get(node_type) == stage or node_type == stage:
                stage_nodes_params[node_type] = defaults

        stage_cfg: dict[str, Any] = {
            "asset_id": None,
            "params": stage_nodes_params
        }
        
        # 只有在非 embedding 阶段才设置 temperature 和 max_tokens
        if stage != "embedding":
            stage_cfg["temperature"] = default_cfg.get("temperature", 0.1)
            stage_cfg["max_tokens"] = default_cfg.get("max_tokens", 128000)
            
        stage_cfg["timeout"] = default_cfg.get("timeout", 60)
        
        stages[stage] = stage_cfg
    
    return stages


def _build_business_config(preset_name: str, template: dict[str, Any], speed_profile: dict[str, Any]) -> dict[str, Any]:
    """构建 business 层参数，完全遵循 SPEED_PROFILES 中的定义。"""
    config = {
        "speed": preset_name,
        "engines": template.get("engines", ["bocha"]),
    }
    
    # 动态将 profile 中的控制参数拉平到 business 中
    for key, val in speed_profile.items():
        if key not in ("label", "description"):
            config[key] = val
            
    return config


async def initialize_user_data(db: AsyncSession, user_id: str, tenant_id: str) -> None:
    """⚡ 为新用户初始化 3 个系统预设 (fast_react / expert_search / research_pipeline)"""
    logger.info(f"正在为用户 {user_id} 初始化系统预设...")

    descriptions = {
        "fast_react":        "极速快问 — 快速检索总结，跳过交叉验证，适合日常速查",
        "expert_search":     "专家搜索 — 深度检索与自主规划，适合方案解释与背景调研",
        "research_pipeline": "深度研报 — 体系化调研与多重验证，适合专业、严谨的研究场景",
    }

    for name, desc in descriptions.items():
        template = DEFAULT_PRESETS.get(name, DEFAULT_PRESETS["research_pipeline"])
        sp = SPEED_PROFILES.get(name, SPEED_PROFILES["research_pipeline"])

        nodes_config = {
            "business": _build_business_config(name, template, sp),
            "stages": _build_stages_config(name),
        }

        # 默认模式设为研报
        is_default = (name == "research_pipeline")

        await upsert_research_preset(
            db, tenant_id, user_id,
            name=name,
            description=desc,
            nodes_config=nodes_config,
            is_default=is_default,
            is_system_default=True,  # ✅ 系统预设不可删除
        )

    await db.flush()
    logger.info(f"用户 {user_id} 预设初始化完成 (fast_react/expert_search/research_pipeline)。")
