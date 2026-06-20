"""Pydantic V2 校验模型 — ORM 3.0 分层配置架构校验。
确保凭证、资产、策略和编排层的数据入参合法。
"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.core.registry import (
    VALID_SECRET_CATEGORIES,
    VALID_SECRET_NAMES,
    NODE_PARAMS_SCHEMA,
)

# ═══════════════════════════════════════════════════════════════
#  1. 凭证层 (Provider)
# ═══════════════════════════════════════════════════════════════

class ProviderUpsert(BaseModel):
    """供应商凭证写入校验"""
    category: str = Field(..., description="llm / search")
    provider_name: str = Field(..., description="供应商标识, e.g. openai")
    plain_key: str | None = Field(default=None, max_length=500)
    base_url: str | None = Field(None, max_length=500)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_SECRET_CATEGORIES:
            raise ValueError(f"不合法的分类 '{v}', 合法值: {list(VALID_SECRET_CATEGORIES)}")
        return v

    @model_validator(mode="after")
    def validate_name_for_category(self) -> "ProviderUpsert":
        valid_names = VALID_SECRET_NAMES.get(self.category, frozenset())
        if self.provider_name not in valid_names:
            raise ValueError(f"不合法的供应商 '{self.provider_name}' (category={self.category})")
        return self

# ═══════════════════════════════════════════════════════════════
#  2. 资产层 (Asset)
# ═══════════════════════════════════════════════════════════════

class ModelAssetUpsert(BaseModel):
    """模型资产注册校验"""
    provider_name: str = Field(...)
    model_name: str = Field(..., min_length=1, max_length=100)
    display_name: str | None = Field(None, max_length=255)
    capabilities: list[str] | None = Field(default_factory=list)
    is_system_default: bool = False

# ═══════════════════════════════════════════════════════════════
#  3. 策略层 (Preset)
# ═══════════════════════════════════════════════════════════════

class ResearchPresetUpsert(BaseModel):
    """研究策略预设校验 (ORM 3.0 简化版)"""
    name: str = Field(..., min_length=1, max_length=50)
    description: str | None = None
    # 包含 stages 和 business 配置
    nodes_config: dict[str, Any] | None = None
    is_system_default: bool = False
    is_default: bool = False
    is_active: bool = True


class PresetCreate(BaseModel):
    """新建用户预设"""
    name: str = Field(..., min_length=1, max_length=50)
    description: str | None = None

# ═══════════════════════════════════════════════════════════════
#  连接性测试
# ═══════════════════════════════════════════════════════════════

class ConnectionTest(BaseModel):
    """连接性测试校验"""
    provider_name: str = Field(...)
    model_name: str = Field(default="ping")
    base_url: str | None = None
    plain_key: str = Field(default="", max_length=500)
    temperature: float = 0.1
    max_tokens: int = 1024
    timeout: int = 30

# ═══════════════════════════════════════════════════════════════
#  深度校验辅助函数 (保持不变或微调)
# ═══════════════════════════════════════════════════════════════

def validate_node_extra(node_type: str, extra: dict[str, Any]) -> list[str]:
    """校验节点参数 extra dict，返回错误消息列表。"""
    errors: list[str] = []
    # 兼容旧的映射名
    mapping = {
        "understanding": "intent_analyze",
        "search": "multi_search",
        "verification": "cross_verify",
        "report": "generate_report",
    }
    mapped_type = mapping.get(node_type, node_type)
    schema = NODE_PARAMS_SCHEMA.get(mapped_type)
    if not schema:
        return errors # 允许未知节点无校验通过

    for key, value in extra.items():
        spec = schema.get(key)
        if spec is None:
            continue

        expected_type = spec["type"]
        if expected_type is int and not isinstance(value, int):
            errors.append(f"'{key}' 应为整数")
        elif expected_type is float and not isinstance(value, (int, float)):
            errors.append(f"'{key}' 应为浮点数")
        elif expected_type is bool and not isinstance(value, bool):
            errors.append(f"'{key}' 应为布尔值")
        
        if isinstance(value, (int, float)) and "min" in spec and "max" in spec:
            if not (spec["min"] <= value <= spec["max"]):
                errors.append(f"'{key}' 超出范围 [{spec['min']}, {spec['max']}]")

    return errors
