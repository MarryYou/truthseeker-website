from __future__ import annotations
import re
from typing import Any, AsyncIterator
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage

from backend.pipeline.state import StateHelper
from backend.pipeline.types import ResearchState, PipelineAbortError
from backend.pipeline.constants import SPEED_PROFILES, DEFAULT_PRESETS
from backend.pipeline.prompts import STRATEGY_PLANNER_SYSTEM, STRATEGY_PLANNER_HUMAN
from backend.core.llm import get_llm_for_stage
from backend.utils.llm_utils import extract_llm_content, parse_llm_json
from backend.core.logging import logger
from backend.db.engine import async_session
from backend.db.models import ResearchPreset

# 社交辞令硬性拦截词表
SOCIAL_WORDS = frozenset({
    "你好", "谢谢", "再见", "嗨", "hello", "hi", "thanks", "thank", "bye", "早上好", "下午好", "晚上好"
})

async def _load_preset_business(preset_id: str | None) -> dict[str, Any]:
    """从 DB 加载 Preset business 层参数。"""
    if not preset_id:
        return {}
    try:
        async with async_session() as db:
            preset = await db.get(ResearchPreset, preset_id)
            if preset and preset.nodes_config:
                return preset.nodes_config.get("business", {})
    except Exception as e:
        logger.warning("加载 Preset business 配置失败 | error={}", e)
    return {}


def _friendly_mode(mode: str) -> str:
    """将内部模式名转为用户友好的中文名称。"""
    p = SPEED_PROFILES.get(mode, {})
    return p.get("label", mode)

def _build_preset_profile(mode: str, business: dict[str, Any]) -> dict[str, Any]:
    """为不需要大模型调优的模式直接从 Preset / 静态基准加载配置参数。"""
    profile = SPEED_PROFILES.get(mode, {})
    overrides = {}

    def _to_val(v: Any) -> Any:
        """dict 范围值原样保留，具体值转 int。"""
        return v if isinstance(v, dict) else int(v) if v is not None else v

    # 1. 维度上限
    max_dims = business.get("max_dimensions") or business.get("intent_max_dimensions") or profile.get("intent_max_dimensions")
    if max_dims is not None:
        overrides["max_dimensions"] = _to_val(max_dims)

    # 2. 搜索轮数上限
    max_rounds = business.get("max_search_rounds") or business.get("max_rounds") or profile.get("max_search_rounds")
    if max_rounds is not None:
        overrides["max_search_rounds"] = _to_val(max_rounds)

    # 3. 每维度关键词数
    kw_per_dim = business.get("keywords_per_dimension") or profile.get("keywords_per_dimension")
    if kw_per_dim is not None:
        overrides["keywords_per_dimension"] = _to_val(kw_per_dim)

    # 4. 最大总结果数
    max_total = business.get("max_total_results") or profile.get("max_total_results")
    if max_total is not None:
        overrides["max_total_results"] = _to_val(max_total)

    # 5. 验证级别
    verif = business.get("verification_level") or profile.get("verification_level")
    if verif is not None:
        overrides["verification_level"] = verif

    # 6. 单次查询最大结果数
    max_res_per_q = business.get("max_results_per_query") or profile.get("max_results_per_query")
    if max_res_per_q is not None:
        overrides["max_results_per_query"] = _to_val(max_res_per_q)
        
    # 7. 双语搜索 & 包含年份
    for flag in ["bilingual", "include_year"]:
        val = business.get(flag)
        if val is not None:
            overrides[flag] = bool(val)
        elif flag in profile:
            overrides[flag] = bool(profile[flag])

    return {
        "strategy_overrides": overrides,
        "thought_steps": [{
            "id": "strategy_planner",
            "label": "准备研究方案",
            "status": "completed",
            "new_sub_step": {"message": f"准备就绪，采用「{_friendly_mode(mode)}」模式开始分析", "type": "success"}
        }]
    }


async def strategy_planner_node(state: ResearchState, config: RunnableConfig) -> AsyncIterator[dict[str, Any]]:
    """策略规划节点：决定响应层级 (Response Tier) 并静态加载对应参数"""
    h = StateHelper(state)
    query = h.query.strip()
    context_mode = state["context"].get("context_mode", "new_research")
    user_id = h.user_id
    preset_id = state["context"].get("preset_id")
    
    # UI/Preset 显式指定的具体模式策略分流 (跳过 LLM 自动选择以节约开销)
    current_mode = state["control"].get("execution_mode")
    speed = h.speed
    if current_mode in ("fast_react", "expert_search", "research_pipeline"):
        speed = current_mode
    business = await _load_preset_business(preset_id)
    
    def _resolve_engines(mode: str) -> list[str]:
        """从 Preset business 或 DEFAULT_PRESETS 确定引擎列表。"""
        eng = business.get("engines")
        if eng:
            return list(eng) if isinstance(eng, list) else [eng]
        return list(DEFAULT_PRESETS.get(mode, {}).get("engines", ["bocha"]))

    # 1. 硬性拦截：针对极短 query 或社交词直接进入极速模式
    if len(query) <= 3 or any(w in query.lower() for w in SOCIAL_WORDS):
        logger.info("触发硬性拦截 | query='{}' -> fast_react", query)
        preset_profile = _build_preset_profile("fast_react", business)
        yield {
            "control": {"execution_mode": "fast_react"},
            "runtime": {
                "shared": {"_suggested_engines": _resolve_engines("fast_react")},
                "pipeline": {"strategy_overrides": preset_profile["strategy_overrides"]}
            },
            **h.update_thought_step(
                "strategy_planner", 
                "检测到简单社交辞令或短语，已自动切换至极速响应模式。", 
                type="success", 
                status="completed", 
                label="准备研究方案"
            )
        }
        return

    # 2. 静态直通：非自动路由模式下，直接使用指定速度档位并直通
    if current_mode != "auto":
        logger.info("已指定模式，直通模式 | mode={}", speed)

        preset_profile = _build_preset_profile(speed, business)

        # 针对极速模式下的复杂追问提出建议 (不强行切换)
        suggestion_msg = f"准备就绪，采用「{_friendly_mode(speed)}」模式开始分析"
        suggestion_type = "success"
        if speed == "fast_react" and context_mode == "follow_up" and len(query) > 15:
            suggestion_msg = "💡 提示：您当前处于「极速快问」模式。如果需要更深度的对比或论证，建议在左侧边栏切换至「深度研报」模式后重新提问。"
            suggestion_type = "info"

        yield {
            "control": {"execution_mode": speed},
            "runtime": {
                "shared": {"_suggested_engines": _resolve_engines(speed)},
                "pipeline": {"strategy_overrides": preset_profile["strategy_overrides"]}
            },
            **h.update_thought_step(
                "strategy_planner", 
                suggestion_msg, 
                type=suggestion_type, 
                status="completed", 
                label="准备研究方案"
            )
        }
        return

    # 3. AI 决策路径分流 (current_mode == "auto")
    step_id = "strategy_planner"
    yield h.update_thought_step(step_id, "", status="running", label="准备研究方案")

    try:
        messages = [
            SystemMessage(content=STRATEGY_PLANNER_SYSTEM),
            HumanMessage(content=STRATEGY_PLANNER_HUMAN.format(
                query=query,
                original_query=state["runtime"]["shared"].get("original_query") or query,
                history_summary=state["memory"].get("history_summary") or "无",
                covered_dimensions="、".join(state["runtime"]["shared"].get("last_research_dimensions", [])) or "无",
                unresolved="\n".join(f"- {u}" for u in state["runtime"]["shared"].get("last_unresolved", [])) or "无"
            ))
        ]

        llm = await get_llm_for_stage("understanding", user_id=user_id, preset_id=preset_id)
        resp = await llm.ainvoke(messages)
        raw = extract_llm_content(resp)
        
        # XML 结构化解析
        json_match = re.search(r"<json>(.*?)</json>", raw, re.DOTALL)
        parsed = parse_llm_json(json_match.group(1) if json_match else raw)

        execution_mode = parsed.get("execution_mode", "research_pipeline")
        if execution_mode not in ("fast_react", "expert_search", "research_pipeline"):
            execution_mode = "research_pipeline"
        # follow_up 上下文强制降级
        if context_mode == "follow_up" and execution_mode == "research_pipeline":
            execution_mode = "expert_search"
            logger.info("AI追问自动降级: research_pipeline → expert_search")


        # 无论决策出什么模式，其 strategy_overrides 完全由静态的 preset profile 产生
        preset_profile = _build_preset_profile(execution_mode, business)
        overrides = preset_profile["strategy_overrides"]

        # 构建友好的用户提示信息
        mode_map = {
            "fast_react": "⚡ 极速快问",
            "expert_search": "🔍 专家搜索",
            "research_pipeline": "📊 深度研报"
        }
        
        detail_msg = f"🤖 AI 已根据问题复杂度接管策略 (已选择: {mode_map.get(execution_mode, execution_mode)})。"
        
        yield {
            "control": {"execution_mode": execution_mode},
            "runtime": {
                "shared": {"_suggested_engines": _resolve_engines(execution_mode)},
                "pipeline": {"strategy_overrides": overrides}
            },
            **h.update_thought_step(step_id, detail_msg, type="success", status="completed")
        }

    except Exception as e:
        logger.error("策略规划失败 | error={}", e)
        yield h.update_thought_step(step_id, f"策略生成异常，无法继续研究: {str(e)}", type="error", status="error")
        yield h.add_error(step_id, "策略规划失败", str(e))
        raise PipelineAbortError(f"策略规划节点异常，任务终止: {str(e)}") from e
