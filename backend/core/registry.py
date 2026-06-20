"""配置合法性注册表 — 合法值的单一事实来源。

所有枚举值和范围约束集中在此，供 settings.py 校验、前端下拉框渲染、前端表单校验复用。
开发者新增 stage / provider / 搜索引擎时只需在此处加一行。
"""
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════
#  管线阶段
# ═══════════════════════════════════════════════════════════════
VALID_STAGES: frozenset[str] = frozenset({
    "understanding",       # 意图分析
    "search",              # 搜索规划
    "verification",        # 交叉验证
    "report",              # 报告生成
    "embedding",           # 向量嵌入
})

# 节点类型 (用于 node:* 配置)
VALID_NODE_TYPES: frozenset[str] = frozenset({
    "intent_analyze",
    "keyword_expand",
    "multi_search",
    "filter_results",
    "cross_verify",
    "generate_report",
})

# 预设策略名 (Speed 档位制: 3 速度预设 + 1 自定义专家模)
VALID_PRESET_NAMES: frozenset[str] = frozenset({
    "fast_react",
    "expert_search",
    "research_pipeline",
    "custom",
})

# 速度档位 (仅供 speed 字段校验)
VALID_SPEED_LEVELS: frozenset[str] = frozenset({
    "fast_react",
    "expert_search",
    "research_pipeline",
})

# ═══════════════════════════════════════════════════════════════
#  模型提供商 (LLM provider)
# ═══════════════════════════════════════════════════════════════
VALID_LLM_PROVIDERS: frozenset[str] = frozenset({
    "deepseek",            # DeepSeek 官方 API
    "dashscope",           # 阿里云百炼 (通义千问)
    "openai",              # OpenAI 官方或兼容接口
})

PROVIDER_FALLBACK_MODELS: dict[str, str] = {
    "deepseek": "deepseek-v4-flash",
    "openai": "gpt-4o-mini",
    "dashscope": "qwen-turbo",
    "groq": "llama3-8b-8192",
    "anthropic": "claude-3-haiku-20240307",
}

LLM_PROVIDER_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "openai": "https://api.openai.com/v1",
}

# ═══════════════════════════════════════════════════════════════
#  搜索引擎插件 (仅含关键词检索引擎，不含 Reader 类)
# ═══════════════════════════════════════════════════════════════
VALID_SEARCH_ENGINES: frozenset[str] = frozenset({
    "tavily",
    "bocha",
    "zhihu",
})

# ═══════════════════════════════════════════════════════════════
#  密钥类别 & 合法 name
# ═══════════════════════════════════════════════════════════════
VALID_SECRET_CATEGORIES: frozenset[str] = frozenset({
    "llm",
    "search",
})

VALID_SECRET_NAMES: dict[str, frozenset[str]] = {
    "llm": frozenset({
        "deepseek",
        "dashscope",
        "openai",
    }),
    "search": frozenset({
        "tavily",
        "bocha",
        "zhihu",
    }),
}

# 验证强度档位
VALID_VERIFICATION_LEVELS: frozenset[str] = frozenset({
    "skip",
    "standard",
    "strict",
})

# ═══════════════════════════════════════════════════════════════
#  通用的数值范围约束
# ═══════════════════════════════════════════════════════════════
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0

MAX_TOKENS_MIN = 1
MAX_TOKENS_MAX = 2048000

# ═══════════════════════════════════════════════════════════════
#  节点参数 (node:*) 的 extra key 及值域约束
#  每个节点类型 → {合法 key → (类型, 最小值, 最大值)}
# ═══════════════════════════════════════════════════════════════
NODE_PARAMS_SCHEMA: dict[str, dict[str, dict]] = {
    "intent_analyze": {
        "intent_confidence_threshold": {"type": float, "min": 0.0, "max": 1.0},
    },
    "keyword_expand": {
        "max_total_keywords":         {"type": int, "min": 1, "max": 100},
    },
    "multi_search": {
        "max_concurrent_engines":  {"type": int, "min": 1, "max": 10},
    },
    "filter_results": {
        "min_relevance_score": {"type": float, "min": 0.0, "max": 1.0},
        "max_total_results":   {"type": int, "min": 1, "max": 200},
        "dedup_similarity":    {"type": float, "min": 0.0, "max": 1.0},
        "batch_concurrency":   {"type": int, "min": 1, "max": 20},
    },
    "cross_verify": {
        "min_evidence_per_claim":   {"type": int, "min": 1, "max": 10},
        "numeric_verify":           {"type": bool},
        "contradiction_detection":  {"type": bool},
    },
    "generate_report": {
        # 报告样式现已由 AI 动态决定
    },
}

# ═══════════════════════════════════════════════════════════════
#  预设策略 (preset:*) 的 extra key 及值域约束
#  仅包含实际被管线消费的全局 (business 层) 参数。
# ═══════════════════════════════════════════════════════════════
PRESET_PARAMS_SCHEMA: dict[str, dict] = {
    "speed":                {"type": "str", "enum": "speed_levels"},
    "engines":              {"type": "list", "item_enum": "search_engines"},
    "max_results_per_query": {"type": dict, "description": "单次搜索结果范围"},
    "max_search_rounds":     {"type": dict, "description": "最大搜索轮数范围"},
    "intent_max_dimensions": {"type": dict, "description": "维度上限范围"},
    "keywords_per_dimension": {"type": dict, "description": "每维度词数范围"},
    "bilingual":            {"type": bool},
    "include_year":         {"type": bool},
    "allow_ai_override":    {"type": bool},
    "verification_level":   {"type": "str", "enum": "verification_levels"},
}
