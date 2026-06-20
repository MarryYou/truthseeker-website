"""pipeline/graph.py — LangGraph 状态机图定义"""
from __future__ import annotations
import time
from typing import Any, AsyncIterator, cast
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.callbacks import CallbackManager
from backend.pipeline.types import ResearchState
from backend.pipeline.constants import SPEED_PROFILES
from backend.pipeline.nodes.intent import intent_node
from backend.pipeline.nodes.filter import coarse_filter_node, llm_filter_node
from backend.pipeline.nodes.report import report_node
from backend.pipeline.subgraphs.verify import verify_subgraph
from backend.pipeline.nodes.strategy import strategy_planner_node
from backend.pipeline.nodes.summary import summary_node
from backend.pipeline.subgraphs.agent.graph import build_agent
from backend.pipeline.subgraphs.search_react.graph import build_search_agent
from backend.db.store import get_store_from_config
from backend.core.llm import get_llm_for_stage
from backend.core.logging import logger
from backend.utils.llm_utils import extract_llm_content
from backend.services.sse.parser import suppress_model_stream


def _resolve_max_rounds(strategy_overrides: dict) -> int:
    val = strategy_overrides.get("max_search_rounds", 3)
    if isinstance(val, dict):
        return int(val.get("max", 3))
    return int(val)


def _resolve_flag(strategy_overrides: dict, key: str, default: bool = False) -> bool:
    val = strategy_overrides.get(key, default)
    return bool(val)


def _resolve_verification_level(state: ResearchState) -> str:
    overrides = state["runtime"]["pipeline"].get("strategy_overrides") or {}
    if "verification_level" in overrides:
        return str(overrides["verification_level"])
    speed = state["control"].get("speed", "research_pipeline")
    from backend.pipeline.constants import SPEED_PROFILES
    default_vl = SPEED_PROFILES.get(speed, SPEED_PROFILES["research_pipeline"])["verification_level"]
    dedup_intensity = state["runtime"]["pipeline"].get("dedup_intensity")
    if dedup_intensity == "relaxed":
        return "strict" if default_vl != "skip" else "skip"
    elif dedup_intensity == "strict":
        return "skip"
    return default_vl


async def agent_wrapper_node(state: ResearchState, config: RunnableConfig) -> AsyncIterator[dict[str, Any]]:
    """Agent 包装器 — 逐步流式输出 thought steps"""

    query = state["runtime"]["shared"].get("query", "")
    execution_mode = state["control"].get("speed", "research_pipeline")
    user_id = cast(str, state["context"].get("user_id", "default"))
    preset_id = state["context"].get("preset_id")
    tenant_id = cast(str, state["context"].get("tenant_id", "default"))
    research_id = state["context"].get("research_id", "")
    task_id = state["context"].get("task_id", "")
    raw_store = config.get("configurable", {}).get("store")
    suggested_engines = state["runtime"]["shared"].get("_suggested_engines", [])
    strategy_overrides = state["runtime"]["pipeline"].get("strategy_overrides", {})

    max_results = 5
    res_range = strategy_overrides.get("max_results_per_query")
    if isinstance(res_range, dict):
        max_results = res_range.get("max", 5)
    elif isinstance(res_range, int):
        max_results = res_range

    max_rounds = strategy_overrides.get("max_search_rounds", {})
    max_r = max_rounds.get("max", 3) if isinstance(max_rounds, dict) else (max_rounds or 3)

    llm = await get_llm_for_stage(execution_mode, user_id=user_id, preset_id=preset_id)
    agent = build_agent(
        llm=llm, raw_store=raw_store, tenant_id=tenant_id,
        user_id=user_id, research_id=research_id, task_id=task_id,
        preset_id=preset_id, execution_mode=execution_mode,
        query=query, suggested_engines=suggested_engines,
        max_results_per_query=max_results, rate_limit_delay=0.5,
        max_rounds=max_r,
    )

    yield {"output": {"diagnostics": {"thought_steps": [{"id": "agent_node", "label": "搜索与分析", "status": "running"}]}}}

    last_msgs = []
    async for update in agent.astream(cast(Any, {"messages": state["memory"].get("messages", [])}), stream_mode="updates"):
        for node_name, node_data in update.items():
            msgs = node_data.get("messages", [])
            if not msgs:
                continue
            new_msg = msgs[-1]
            if node_name in ("model", "tools"):
                last_msgs = msgs
            if isinstance(new_msg, AIMessage) and new_msg.tool_calls:
                yield {"output": {"diagnostics": {"thought_steps": [{"id": "agent_node", "new_sub_step": {"message": "🔍 正在搜索相关信息…", "type": "tool_call", "ts": time.time()}}]}}}
            elif isinstance(new_msg, ToolMessage) and len(str(new_msg.content)) > 20:
                tool_name = getattr(new_msg, "name", "")
                if tool_name == "fetch_full_content":
                    yield {"output": {"diagnostics": {"thought_steps": [{"id": "agent_node", "new_sub_step": {"message": "📄 正在获取相关资料…", "type": "info", "ts": time.time()}}]}}}
                else:
                    yield {"output": {"diagnostics": {"thought_steps": [{"id": "agent_node", "new_sub_step": {"message": "📄 已获取到相关资料", "type": "info", "ts": time.time()}}]}}}

    report_prompt = ""
    for msg in reversed(last_msgs if last_msgs else []):
        if isinstance(msg, AIMessage) and str(msg.content).strip() and not msg.tool_calls:
            report_prompt = extract_llm_content(msg)
            break
    yield {"output": {"diagnostics": {"thought_steps": [{"id": "agent_node", "new_sub_step": {"message": "📝 正在生成研究报告…", "type": "info", "ts": time.time()}}]}}}
    if report_prompt:
        rs = get_store_from_config(config)
        await rs.save_report("final", report_prompt)
    yield {"output": {"agent": {"report_prompt": report_prompt or ""}, "diagnostics": {"thought_steps": [{"id": "agent_node", "status": "completed", "new_sub_step": {"message": "✅ 报告生成完毕", "type": "success", "ts": time.time()}}]}}}


async def cross_verify_wrapper_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    vl = _resolve_verification_level(state)
    overrides = state["runtime"]["pipeline"].get("strategy_overrides") or {}
    rs = get_store_from_config(config)
    filtered_key = state["output"]["diagnostics"].get("store_refs", {}).get("filtered", "final")
    try:
        filtered_items = await rs.load_filtered_results(filtered_key)
        if not filtered_items:
            filtered_items = await rs.load_all_search_results()
    except Exception as e:
        logger.warning("cross_verify_wrapper_node 加载网页信源失败 | error={}", e)
        filtered_items = []
    verify_input = {
        "query": state["runtime"]["shared"].get("query", ""),
        "intent_type": state["runtime"]["shared"].get("intent_type", ""),
        "dimensions": state["runtime"]["pipeline"].get("dimensions", []),
        "tenant_id": state["context"].get("tenant_id", "default"),
        "user_id": state["context"].get("user_id", "default"),
        "preset_id": state["context"].get("preset_id", ""),
        "verification_level": vl,
        "strategy_overrides": overrides,
        "store_refs": state["output"]["diagnostics"].get("store_refs", {}),
        "thought_steps": state["output"]["diagnostics"].get("thought_steps", []),
        "_filtered_items": filtered_items or [],
    }
    verify_output = await verify_subgraph.ainvoke(verify_input, config)
    return {
        "memory": {"proven_facts": verify_output.get("proven_facts", [])},
        "runtime": {"pipeline": {
            "conflict_dimensions": verify_output.get("conflict_dimensions", []),
            "insufficient_dimensions": verify_output.get("insufficient_dimensions", []),
        }},
        "output": {"diagnostics": {
            "warnings": verify_output.get("warnings", []),
            "error_log": verify_output.get("error_log", []),
            "thought_steps": verify_output.get("thought_steps", []),
        }, "pipeline": {"overall_confidence": verify_output.get("overall_confidence", 0.0)}}
    }


async def search_react_wrapper_node(state: ResearchState, config: RunnableConfig) -> AsyncIterator[dict[str, Any]]:
    """搜索 Agent — astream 实时思考链 + response_format 结构化输出"""

    query = state["runtime"]["shared"].get("query", "")
    dimensions = state["runtime"]["pipeline"].get("dimensions", [])
    user_id = cast(str, state["context"].get("user_id", "default"))
    preset_id = state["context"].get("preset_id")
    tenant_id = cast(str, state["context"].get("tenant_id", "default"))
    research_id = state["context"].get("research_id", "")
    task_id = state["context"].get("task_id", "")
    raw_store = config.get("configurable", {}).get("store")
    overrides = state["runtime"]["pipeline"].get("strategy_overrides", {})
    suggested_engines = state["runtime"]["shared"].get("_suggested_engines", [])

    max_results = 5
    res_range = overrides.get("max_results_per_query")
    if isinstance(res_range, dict):
        max_results = res_range.get("max", 5)
    elif isinstance(res_range, int):
        max_results = res_range

    max_rounds = _resolve_max_rounds(overrides)
    
    kw_per_dim = overrides.get("keywords_per_dimension", 3)
    if isinstance(kw_per_dim, dict):
        kw_per_dim = kw_per_dim.get("max", 3)
    kw_per_dim = int(kw_per_dim)

    bilingual = _resolve_flag(overrides, "bilingual")
    include_year = _resolve_flag(overrides, "include_year")

    llm = await get_llm_for_stage("search", user_id=user_id, preset_id=preset_id)
    agent = build_search_agent(llm=llm, raw_store=raw_store, tenant_id=tenant_id, user_id=user_id,
                               research_id=research_id, task_id=task_id, preset_id=preset_id,
                               suggested_engines=suggested_engines, max_results=max_results,
                               dimensions=[d for d in dimensions if d], max_rounds=max_rounds,
                               keywords_per_dim=kw_per_dim, bilingual=bilingual,
                               include_year=include_year)

    prompt = f"搜索以下维度的信息：{', '.join(dimensions)}\n\n原始问题：{query}" if dimensions else query
    current_round = state["runtime"]["pipeline"].get("search_round", 0)
    search_step_id = f"search_react_{current_round}"
    search_step_label = f"搜索第{current_round + 1}轮"
    yield {"output": {"diagnostics": {"thought_steps": [{"id": search_step_id, "label": search_step_label, "status": "running"}]}}}

    last_msgs = []
    final_state = None
    token_suppress = suppress_model_stream.set(True)
    
    # 隔离 Callback，防止 astream_events 的回调穿透到内部 LLM 导致 SSE 泛滥
    isolated_config = cast(RunnableConfig, {**config, "callbacks": CallbackManager([])})
    
    try:
        async for agent_state in agent.astream({"messages": [{"role": "user", "content": prompt}]}, stream_mode="values", config=isolated_config):
            final_state = agent_state
            msgs = agent_state.get("messages", [])
            if len(msgs) > len(last_msgs):
                new_msg = msgs[-1]
                if isinstance(new_msg, AIMessage) and new_msg.tool_calls:
                    yield {"output": {"diagnostics": {"thought_steps": [{"id": search_step_id, "new_sub_step": {"message": "🔍 正在搜索…", "type": "tool_call", "ts": time.time()}}]}}}
                elif isinstance(new_msg, ToolMessage) and len(str(new_msg.content)) > 20:
                    yield {"output": {"diagnostics": {"thought_steps": [{"id": search_step_id, "new_sub_step": {"message": "📄 获取到搜索结果", "type": "info", "ts": time.time()}}]}}}
            last_msgs = msgs

        # 从最终 AI 消息中解析结构化输出
        sr = _parse_search_output(final_state) if final_state else {}

        yield {"output": {"diagnostics": {"thought_steps": [{"id": search_step_id, "status": "completed"}]}}}
        yield {
            "runtime": {"pipeline": {
                "searched_keywords_history": sr.get("keywords", []),
                "search_round": current_round + 1,
                "needs_more_search": sr.get("needs_more_search", False),
                "search_strategy": sr.get("next_strategy", "done"),
                "valuable_urls": sr.get("urls", []),
            }},
        }
    finally:
        suppress_model_stream.reset(token_suppress)


def _parse_search_output(final_state: dict) -> dict:
    """从最终 AI 消息中解析 key: value 格式的评估结果"""
    msgs = final_state.get("messages", [])
    for msg in reversed(msgs):
        if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
            text = str(msg.content)
            result = {}
            for line in text.strip().split("\n"):
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key = key.strip().lower()
                val = val.strip()
                if key == "needs_more_search":
                    result[key] = val.lower() == "true"
                elif key == "keywords":
                    result[key] = [k.strip() for k in val.split(",") if k.strip()]
                elif key == "urls":
                    result[key] = [u.strip() for u in val.split(",") if u.strip()]
                elif key == "dimensions_covered":
                    result[key] = [d.strip() for d in val.split(",") if d.strip()]
                elif key in ("next_strategy", "reason", "suggested_focus", "summary"):
                    result[key] = val
            if result.get("next_strategy"):
                return result
    return {}


def build_graph() -> StateGraph:
    g = StateGraph(cast(Any, ResearchState))
    g.add_node("strategy_planner", strategy_planner_node)
    g.add_node("agent_node", agent_wrapper_node)
    g.add_node("intent_analyze", intent_node)
    g.add_node("search_react", search_react_wrapper_node)
    g.add_node("coarse_filter", coarse_filter_node)
    g.add_node("llm_filter", llm_filter_node)
    g.add_node("cross_verify", cross_verify_wrapper_node)
    g.add_node("generate_report_prompt", report_node)
    g.add_node("summary_node", summary_node)

    g.set_entry_point("strategy_planner")
    g.add_conditional_edges("strategy_planner", _route_after_strategy, {
        "agent": "agent_node", "intent": "intent_analyze",
    })
    g.add_conditional_edges("intent_analyze", _route_after_intent, {
        "agent": "agent_node", "pipeline": "search_react",
    })
    g.add_edge("search_react", "coarse_filter")
    g.add_edge("coarse_filter", "llm_filter")
    g.add_edge("llm_filter", "cross_verify")
    g.add_conditional_edges("cross_verify", _route_after_verify, {
        "search_more": "search_react", "report": "generate_report_prompt",
    })
    g.add_edge("agent_node", "summary_node")
    g.add_edge("generate_report_prompt", "summary_node")
    g.add_edge("summary_node", END)
    return g


def _route_after_strategy(state: ResearchState) -> str:
    speed = state["control"].get("speed", "research_pipeline")
    if speed in ("fast_react", "expert_search"):
        return "agent"
    return "intent"


def _route_after_intent(state: ResearchState) -> str:
    return "pipeline"


def _route_after_verify(state: ResearchState) -> str:
    conflict_dims = state["runtime"]["pipeline"].get("conflict_dimensions", [])
    if not conflict_dims:
        return "report"
    overrides = state["runtime"]["pipeline"].get("strategy_overrides") or {}
    max_rounds = overrides.get("max_search_rounds")
    if max_rounds is None:
        speed = state["control"].get("speed", "research_pipeline")
        max_rounds = SPEED_PROFILES.get(speed, SPEED_PROFILES["research_pipeline"])["max_search_rounds"]
    if isinstance(max_rounds, dict):
        max_rounds = max_rounds.get("max", 3)
    current_round = state["runtime"]["pipeline"].get("search_round", 0)
    if conflict_dims and current_round < max_rounds:
        return "search_more"
    return "report"


def compile_graph(checkpointer: Any = None, store: Any = None, enable_hitl: bool = True):
    g = build_graph()
    compile_kwargs = {}
    if checkpointer:
        compile_kwargs["checkpointer"] = checkpointer
    if store:
        compile_kwargs["store"] = store
    if enable_hitl:
        compile_kwargs["interrupt_before"] = ["search_react"]
    return g.compile(**compile_kwargs)
