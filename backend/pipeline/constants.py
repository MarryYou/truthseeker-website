"""pipeline/constants.py — 管线所有常量、安全边界与默认配置的唯一事实来源。

按职责分区：
  §A  速度档位 (Speed Profiles)
  §B  AI 策略覆盖 (Strategy Override 安全边界)
  §C  节点级默认参数
  §D  搜索引擎 & Reader 默认值
  §E  LLM/Token 安全边界
  §F  Embedding & 去重阈值
  §G  Reader / Filter 节点常量
  §H  路由条件常量
  §I  节点名称注册表 (与 graph.py 对应)

所有节点文件 **只从本文件导入常量**，禁止在节点内硬编码魔法数字。
"""
from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════
#  §A  速度档位 (Speed Profiles)
# ═══════════════════════════════════════════════════════════════

DEFAULT_SPEED = "research_pipeline"
DEFAULT_VERIFICATION = "standard"

SPEED_PROFILES: dict[str, dict[str, Any]] = {
    "fast_react": {
        "label": "极速快问",
        "description": "快速检索总结，减少验证深度，适合日常速查",
        "intent_max_dimensions": 2,
        "max_search_rounds": 1,
        "max_results_per_query": 3,
        "verification_level": "skip",
    },
    "expert_search": {
        "label": "专家搜索",
        "description": "标准深度检索与自主规划，适合方案解释与背景调研",
        "intent_max_dimensions": 3,
        "max_search_rounds": 2,
        "max_results_per_query": 5,
        "verification_level": "standard",

    },
    "research_pipeline": {
        "label": "深度研报",
        "description": "最大化检索覆盖与交叉验证深度，适合专业、严谨的研究场景",
        "allow_ai_override": True,
        "intent_max_dimensions": {"min": 3, "max": 6},
        "keywords_per_dimension": {"min": 2, "max": 4},
        "max_search_rounds": {"min": 1, "max": 3},
        "max_results_per_query": {"min": 4, "max": 8},
        "max_total_results": 40,
        "bilingual": True,
        "include_year": True,
        "verification_level": "strict",

    },
}

DEFAULT_PRESETS: dict[str, dict[str, Any]] = {
    "fast_react": {"speed": "fast_react", "engines": ["bocha"]},
    "expert_search": {"speed": "expert_search", "engines": ["bocha", "tavily"]},
    "research_pipeline": {"speed": "research_pipeline", "engines": ["bocha", "tavily"]},
}


# ═══════════════════════════════════════════════════════════════
#  §B  AI 策略覆盖 (Strategy Override) 安全边界
# ═══════════════════════════════════════════════════════════════
# intent_node 解析 AI 返回的 strategy_params 时使用的 clamp 范围。

STRATEGY_INT_CLAMP_RANGES: dict[str, tuple[int, int]] = {
    "max_dimensions": (1, 6),
    "max_search_rounds": (1, 4),
    "keywords_per_dimension": (1, 5),
    "max_total_results": (5, 60),
}

VALID_VERIFICATION_LEVELS: frozenset[str] = frozenset({"skip", "standard", "strict"})



# ═══════════════════════════════════════════════════════════════
#  §C  节点级默认参数
# ═══════════════════════════════════════════════════════════════
# 全部可被 Preset(DB) 覆盖。

NODE_DEFAULTS: dict[str, dict[str, Any]] = {
    "intent_analyze": {
        "intent_confidence_threshold": 0.60,
    },
    "multi_search": {
        "max_concurrent_engines": 3,
        "max_concurrent_queries": 4,
    },
    "filter_results": {
        "min_relevance_score": 0.35,
        "max_total_results": 50,
        "dedup_similarity": 0.92,
        "batch_concurrency": 10,
    },
    "cross_verify": {
        "min_evidence_per_claim": 2,
        "numeric_verify": True,
        "marketing_detection": True,
        "contradiction_detection": True,
    },
    "generate_report": {
        # 报告样式现已由 AI 动态决定，此处仅作为结构参考
    },
}


# ═══════════════════════════════════════════════════════════════
#  §D  搜索引擎 & Reader 默认值
# ═══════════════════════════════════════════════════════════════

# ── 节点并发控制 ──────────────────────────────────────────────────
MAX_CONCURRENT_QUERIES: int = 8      # 搜索引擎关键词并发
STAGGERED_SEARCH_DELAY: float = 0.1  # 关键词发起的梯次延迟
BATCH_FILTER_CONCURRENCY: int = 10   # 网页筛选批次并发

# ── 语义去重阈值 ──────────────────────────────────────────────────
EMBEDDING_DEDUP_THRESHOLD: float = 0.85   # 网页去重阈值
DIMENSION_DEDUP_SIMILARITY: float = 0.75  # 维度拆解去重阈值
DIMENSION_DEDUP_THRESHOLDS: dict[str, float] = {
    "strict": 0.68,    # 严格去重 (稍微相似就过滤，要求维度具有极显著的独立差异)
    "standard": 0.75,  # 标准去重
    "relaxed": 0.80,   # 宽松去重 (允许高度接近但有细微差异的专业方向并存)
}
VERIFY_CLAIM_SIMILARITY: float = 0.70     # 证据匹配相似度阈值

# ── 动态 Token 预算管理 (针对 128k 环境优化) ────────────────────────
MODEL_CONTEXT_WINDOW_DEFAULT: int = 128000   # 默认模型上下文窗口 (tokens)
CONTEXT_UTILIZATION_RATIO: float = 0.6       # 目标窗口利用率 (保守建议 0.6)
CHARS_PER_TOKEN_ESTIMATE: float = 2.5        # 中英混合环境下 1 token 约等于的字符数

# 筛选分级阈值与窗口
FILTER_HIGH_SCORE_THRESHOLD: float = 0.8
FILTER_MID_SCORE_THRESHOLD: float = 0.5
FILTER_HIGH_SCORE_WINDOW: int = 8000         # 高分信源保留字符
FILTER_MID_SCORE_WINDOW: int = 2000          # 中分信源保留字符
FILTER_SUMMARY_FALLBACK: int = 400           # 低分信源摘要截断

# 核验阶段参数
VERIFY_EVIDENCE_WINDOW: int = 1500           # 交叉验证时的单条证据字符
VERIFY_BATCH_CLAIMS_MAX: int = 10            # 单个批次核验的声明上限
VERIFY_MAX_EVIDENCE_PER_CLAIM: int = 8       # 每条声明参考的信源上限

# 报告生成参数
REPORT_CORE_SOURCES_COUNT: int = 12          # 报告中作为“核心信源”完整展示的数量
REPORT_SUMMARY_LENGTH: int = 500             # 报告引用的摘要降级长度

DEFAULT_ACTIVE_ENGINES: list[str] = ["bocha"]
GLOBAL_SEARCH_RATE_LIMIT: float = 0.5 # 搜索引擎全局限流等待时间 (秒)



# ═══════════════════════════════════════════════════════════════
#  §E  LLM / Token 安全边界 (防 Token 溢出)
# ═══════════════════════════════════════════════════════════════
DEFAULT_MAX_TOKENS = 128000  # 128k
DEFAULT_LLM_TIMEOUT = 60

# atomize 节点：单次 LLM 调用最大传入信源数
ATOMIZE_MAX_SOURCES: int = 8
# atomize 节点：每维度最大提取声明数
ATOMIZE_MAX_CLAIMS_PER_DIM: int = 12

# report 节点：传给 LLM 的最大声明数 / 最大来源数
REPORT_MAX_CLAIMS: int = 30
REPORT_MAX_SOURCES: int = 15


# ═══════════════════════════════════════════════════════════════
#  §F  Embedding & 去重阈值
# ═══════════════════════════════════════════════════════════════

EMBEDDING_BATCH_SIZE: int = 10


# ═══════════════════════════════════════════════════════════════
#  §G  Reader / Filter 节点常量
# ═══════════════════════════════════════════════════════════════

# reader 节点
FULL_TEXT_FIELD: str = "full_text"
MAX_FULL_TEXT_FOR_SUMMARY: int = 1500
MIN_FULL_TEXT_QUALITY: int = 600
READER_MAX_CONCURRENCY: int = 5

# filter 节点
FILTER_MAX_CONTENT_LENGTH: int = 1500
FILTER_LLM_BODY_TRUNCATE: int = 2000
FILTER_TARGET_CHARS: int = 6000
FILTER_BATCH_MIN: int = 2
FILTER_BATCH_MAX: int = 15

# atomize 节点
ATOMIZE_BATCH_MAX_DIM_SOURCE_PRODUCT: int = 20


# ═══════════════════════════════════════════════════════════════
#  §H  路由条件默认值
# ═══════════════════════════════════════════════════════════════

DEFAULT_MAX_SEARCH_ROUNDS: int = 2


# ═══════════════════════════════════════════════════════════════
#  §J  持久化与显示约束
# ═══════════════════════════════════════════════════════════════
FRONTEND_VERDICT_MAP: dict[str, str] = {
    "consistent": "verified",
    "mostly_consistent": "likely_true",
    "contradictory": "disputed",
    "single_source": "likely_true",
    "unverifiable": "unverifiable"
}

MAX_CORE_ANSWER_LENGTH: int = 300
MAX_PREVIOUS_DIMENSIONS: int = 8
MAX_UNRESOLVED_QUESTIONS: int = 5
MAX_HISTORY_TURNS: int = 10
# ═══════════════════════════════════════════════════════════════
# 可被数据库中 ModelConfig (stage=preset:*) 覆盖。

DEFAULT_STAGE_MODELS: dict[str, dict] = {
    "understanding": {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "temperature": 0.1,
        "timeout": 60,
        "params": {"base_url": "https://api.deepseek.com/v1"},
    },
    "search": {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "temperature": 0.2,
        "timeout": 60,
        "params": {"base_url": "https://api.deepseek.com/v1"},
    },
    "verification": {
        "provider": "dashscope",
        "model": "qwen3.6-flash",
        "temperature": 0.2,
        "timeout": 60,
        "params": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    },
    "report": {
        "provider": "dashscope",
        "model": "qwen3.6-flash",
        "temperature": 0.5,
        "timeout": 60,
        "params": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    },
    "fast_react": {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "temperature": 0.2,
        "timeout": 60,
        "params": {"base_url": "https://api.deepseek.com/v1"},
    },
    "expert_search": {
        "provider": "dashscope",
        "model": "qwen3.6-flash",
        "temperature": 0.3,
        "timeout": 60,
        "params": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    },
    "embedding": {
        "provider": "dashscope",
        "model": "tongyi-embedding-vision-flash-2026-03-06",
        "timeout": 30,
        "params": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    },
}

# ── verify_subgraph 内部常量 ───────────────────────────────────────────
DOMAIN_TRUST_THRESHOLD: float = 0.75
BATCH_TOKEN_BUDGET: int = 2000
PROFILE_MAX_CONCURRENCY: int = 5
