"""LLM 工具函数：JSON 解析、配置读取"""
from __future__ import annotations
import json
import re
from typing import Any
from langchain_core.runnables import RunnableConfig
from backend.pipeline.constants import NODE_DEFAULTS
from backend.db.models import ResearchPreset
from backend.db.engine import async_session

_CODE_BLOCK_RE = re.compile(r"```[a-zA-Z]*\s*\n?(.*?)```", re.DOTALL)
_THINK_TAG_RE = re.compile(r"<think[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)

# ── LLM 废话过滤正则 ──────────────────────────────────────────────
# 匹配常见的开场白：如”好的”、”收到”、”好的，根据您的要求...”、”这就为您...”
_CHITCHAT_PREFIX_RE = re.compile(
    r'^\s*(?:好的|收到|好的[，,].*?|遵命|没问题|以下是.*?|为您生成.*?|为您撰写.*?)[：:\n\s]*',
    re.DOTALL | re.IGNORECASE
)

def clean_null_bytes(val: Any) -> Any:
    """递归清除数据中所有的 NUL (\x00) 字节以防止 PostgreSQL JSONB 写入报错"""
    if isinstance(val, str):
        return val.replace("\u0000", "").replace("\x00", "")
    elif isinstance(val, dict):
        return {k: clean_null_bytes(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [clean_null_bytes(v) for v in val]
    return val


def parse_llm_json(raw: str) -> Any:
    """从 LLM 输出中解析 JSON。处理 <think/> 标签、```json 代码块、{{ }} 转义。"""
    text = raw.strip()
    text = _THINK_TAG_RE.sub("", text).strip()

    if text.startswith("```"):
        m = _CODE_BLOCK_RE.search(text)
        if m:
            text = m.group(1).strip()

    try:
        return clean_null_bytes(json.loads(text))
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        start = text.find("{{")
    if start == -1:
        raise json.JSONDecodeError("未找到 JSON 对象", text, 0)

    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                extracted = text[start : i + 1]
                if "{{" in extracted or "}}" in extracted:
                    extracted = extracted.replace("{{", "{").replace("}}", "}")
                return clean_null_bytes(json.loads(extracted))

    raise json.JSONDecodeError("未找到完整 JSON 对象", text, start)


def extract_llm_content(response: Any) -> str:
    """从 LLM 响应中提取纯净文本内容：
    1. 剥离 <think> 标签内容
    2. 剥离模型开场白（好的/收到等）
    3. 清理多余空行
    """
    if hasattr(response, "content"):
        content = response.content
    else:
        content = response
        
    if not isinstance(content, str):
        if isinstance(content, list):
            content = json.dumps(content, ensure_ascii=False)
        else:
            content = str(content)

    # 1. 移除思考过程（think 标签）
    text = _THINK_TAG_RE.sub("", content).strip()

    # 2. 移除 markdown 代码块包裹 (智能分析)
    m = _CODE_BLOCK_RE.search(text)
    if m:
        block_content = m.group(1).strip()
        # 检查除代码块外其余内容的长度，防止在长文 Markdown 报告中误杀
        remaining = text.replace(m.group(0), "").strip()
        remaining_clean = _CHITCHAT_PREFIX_RE.sub("", remaining).strip()
        # 去除标点杂质
        remaining_clean = re.sub(r"[，。！、；：：\s\-\*]+", "", remaining_clean)
        
        # 如果剩余的有用文本长度极短（说明只是客套废话或引导词），或者本来就是整篇全包裹
        if len(remaining_clean) < 15 or (text.startswith("```") and text.endswith("```")):
            text = block_content
    else:
        # 兼容处理: 如果以 ``` 开头并结尾，但内部格式稍微不规范
        if text.startswith("```") and text.endswith("```"):
            lines = text.split("\n")
            if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1]).strip()

    # 3. 移除开场废话（循环移除，防止多句堆叠）
    prev_text = ""
    while text != prev_text:
        prev_text = text
        text = _CHITCHAT_PREFIX_RE.sub("", text).strip()
        
    return text


async def get_node_config(config: RunnableConfig | None, node_type: str) -> dict[str, Any]:
    """从数据库或默认值中提取指定节点的合并配置。
    寻址优先级：Preset (DB) > NODE_DEFAULTS
    """
    node_defaults = NODE_DEFAULTS.get(node_type, {})
    
    # 1. 尝试从 configurable 获取 preset_id
    configurable = config.get("configurable", {}) if config else {}
    preset_id = configurable.get("preset_id")
    db_session = configurable.get("db")

    if preset_id:
        # 如果有 db session，直接用；否则创建临时 session
        if db_session:
            preset = await db_session.get(ResearchPreset, preset_id)
            return _extract_params_from_preset(preset, node_type, node_defaults)
        else:
            async with async_session() as db:
                preset = await db.get(ResearchPreset, preset_id)
                return _extract_params_from_preset(preset, node_type, node_defaults)

    return node_defaults


def _extract_params_from_preset(preset: Any, node_type: str, defaults: dict) -> dict:
    """内部辅助：从 Preset 对象中解析出特定节点类型的参数。"""
    if not preset or not preset.nodes_config:
        return defaults

    stages = preset.nodes_config.get("stages", {})
    business = preset.nodes_config.get("business", {})

    # node_type → stage 名映射
    NODE_TO_STAGE: dict[str, str] = {
        "intent_analyze":   "understanding",
        "keyword_expand":   "understanding",
        "multi_search":     "search",
        "filter_results":   "search",
        "cross_verify":     "verification",
        "generate_report":  "report",
    }
    stage_name = NODE_TO_STAGE.get(node_type, node_type)
    speed = business.get("speed", "research_pipeline")

    # 1. 尝试从具体 stage 找 params
    stage_cfg = stages.get(stage_name)
    
    # 2. 如果没找到，且当前是 Agent 模式，尝试从 Agent 模型节点找
    if not stage_cfg and speed in ["fast_react", "expert_search"]:
        stage_cfg = stages.get(speed)

    if not stage_cfg:
        return defaults

    stage_params = stage_cfg.get("params", {})
    if isinstance(stage_params, dict):
        # 优先尝试 params[node_type] 子键 (新结构)
        node_params = stage_params.get(node_type)
        if isinstance(node_params, dict):
            return {**defaults, **node_params}
        
        # 兼容处理: 检查是否是扁平参数
        return {**defaults, **stage_params}

    return defaults
