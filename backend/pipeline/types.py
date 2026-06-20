"""pipeline/types.py — 管线所有 TypedDict / dataclass / Literal 类型定义的唯一事实来源。

按职责分区：
  §A  速度档位 / 验证深度 / 搜索策略 / 上下文模式 (Literal 类型)
  §B  StrategyOverrides (AI 策略覆盖 TypedDict)
  §C  思考链 (ThoughtStep / SubStep)
  §D  ErrorEntry (错误条目)
  §E  ResearchState (主管线状态)
  §F  VerifyState (验证子图状态)
  §G  Reducer 函数 (state 合并逻辑)

所有节点 / 子图 / 服务文件 **只从本文件导入类型定义**。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Annotated, Any, Literal, TypedDict, cast
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ═══════════════════════════════════════════════════════════════
#  §A  Literal 类型定义
# ═══════════════════════════════════════════════════════════════

SpeedLevel = Literal["fast_react", "expert_search", "research_pipeline", "custom"]

VerificationLevel = Literal["skip", "standard", "strict"]

SearchStrategy = Literal["broad", "deep", "targeted", "done"]

SearchDepth = Literal["basic", "advanced"]

ContextMode = Literal["new_research", "follow_up"]


ExecutionMode = Literal["fast_react", "expert_search", "research_pipeline"]


# ═══════════════════════════════════════════════════════════════
#  §B  StrategyOverrides (AI 策略覆盖 TypedDict)
# ═══════════════════════════════════════════════════════════════
# intent_node 解析 AI 返回的 strategy_params，写入 state.strategy_overrides

class StrategyOverrides(TypedDict, total=False):
    """AI intent 节点的策略覆盖参数，专家模式下始终为空。"""
    execution_mode: str                     # 显式覆盖执行模式
    max_dimensions: int
    max_search_rounds: int
    keywords_per_dimension: int
    bilingual: bool
    include_year: bool
    verification_level: str
    max_total_results: int
    engines: list[str]
    temperature: float


# ═══════════════════════════════════════════════════════════════
#  §C  思考链类型 (ThoughtStep / SubStep)
# ═══════════════════════════════════════════════════════════════

SubStepType = Literal["info", "success", "warning", "error", "tool_call"]
StepStatus = Literal["pending", "running", "completed", "error"]


class SubStep(TypedDict):
    """思考链中的原子子步骤（日志）"""
    message: str
    type: SubStepType
    ts: float
    data: dict[str, Any] | None


class ThoughtStep(TypedDict):
    """思考链中的核心步骤（对应一个 Node 或一个阶段）"""
    id: str
    label: str
    status: StepStatus
    sub_steps: list[SubStep]


# ═══════════════════════════════════════════════════════════════
#  §D  ErrorEntry (错误条目)
# ═══════════════════════════════════════════════════════════════

@dataclass
class ErrorEntry:
    """管线错误日志条目"""
    node: str
    message: str
    detail: str | None = None


# ═══════════════════════════════════════════════════════════════
#  §E  ResearchState (主管线状态)
# ═══════════════════════════════════════════════════════════════

class SessionContext(TypedDict, total=False):
    research_id: str
    task_id: str
    tenant_id: str | None
    user_id: str
    preset_id: str | None
    context_mode: str                       # ContextMode

class ControlConfig(TypedDict, total=False):
    execution_mode: Literal["auto", "preset"]
    enable_hitl: bool
    speed: Literal["fast_react", "expert_search", "research_pipeline"]
    runtime_overrides: dict[str, Any]

class InteractionState(TypedDict, total=False):
    breakpoint_type: Literal["none", "dimensions", "sources"]
    dimensions_approved: bool
    sources_approved: bool
    approved_dimensions: list[str]
    approved_sources: list[str]
    force_summarize: bool

class MemoryState(TypedDict, total=False):
    messages: list[BaseMessage]
    follow_up_history: list[dict]
    history_summary: str
    proven_facts: list[dict]
    short_term_memory: str

class SharedRuntime(TypedDict, total=False):
    query: str
    original_query: str
    intent_type: str
    _suggested_engines: list[str]
    last_research_summary: str
    last_research_dimensions: list[str]
    last_unresolved: list[str]
    media_inputs: list[dict]
    manual_injections: list[str]
    rejected_urls: list[str]

class PipelineRuntime(TypedDict, total=False):
    search_plan: str
    search_keywords: list[str]
    display_keywords: list[str]
    dimensions: list[str]
    search_tasks: list[tuple[str, str | None]]
    search_round: int
    search_iteration: int
    needs_more_search: bool
    searched_keywords_history: list[str]
    insufficient_dimensions: list[str]
    conflict_dimensions: list[str]
    strategy_overrides: dict[str, Any]
    search_strategy: str
    valuable_urls: list[str]
    dedup_intensity: str

class AgentRuntime(TypedDict, total=False):
    iteration_count: int
    max_results_per_query: int | None

class RuntimeState(TypedDict):
    shared: SharedRuntime
    pipeline: PipelineRuntime
    agent: AgentRuntime

class SharedDiagnostics(TypedDict, total=False):
    thought_steps: list[ThoughtStep]
    warnings: list[str]
    error_log: list[ErrorEntry]
    store_refs: dict[str, str]

class PipelineOutput(TypedDict, total=False):
    report_prompt: str
    report_instruction: str
    overall_confidence: float

class AgentOutput(TypedDict, total=False):
    report_prompt: str

class OutputDiagnostics(TypedDict):
    diagnostics: SharedDiagnostics
    pipeline: PipelineOutput
    agent: AgentOutput


# ── 合并器 Reducer 定义 ──

def merge_error_log(existing: list[ErrorEntry], new: list[ErrorEntry]) -> list[ErrorEntry]:
    """Reducer：在管线运行中自动累加错误日志，而不是覆盖"""
    return (existing or []) + list(new or [])


def merge_proven_facts(existing: list[dict], new: list[dict]) -> list[dict]:
    """Reducer：合并已验证事实，基于内容进行简单去重 (v3.0)"""
    if not existing:
        return list(new or [])
    if not new:
        return list(existing)
    
    # 使用 claim 或 content 字段作为去重 Key
    seen_claims = {f.get("claim", f.get("content", "")) for f in existing}
    
    final_facts = list(existing)
    for fact in new:
        claim = fact.get("claim", fact.get("content", ""))
        if claim and claim not in seen_claims:
            final_facts.append(fact)
            seen_claims.add(claim)
            
    return final_facts


def merge_warnings(existing: list[str], new: list[str]) -> list[str]:
    """Reducer：在管线运行中自动累加警告日志，而不是覆盖"""
    return (existing or []) + list(new or [])


def merge_store_refs(existing: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    """Reducer：在管线运行中自动合并 Store Refs 字典"""
    return {**(existing or {}), **(new or {})}


def merge_thought_steps(
    existing: list[ThoughtStep] | None,
    updates: list[dict[str, Any]],
) -> list[ThoughtStep]:
    """智能 Reducer：支持对 ThoughtStep 的局部更新和 sub_steps 的原子追加。"""
    current_steps = list(existing) if existing else []
    steps_dict = {s["id"]: s.copy() for s in current_steps}

    for upd in updates:
        sid = upd.get("id")
        if not sid:
            continue

        if sid not in steps_dict:
            steps_dict[sid] = {
                "id": sid,
                "label": upd.get("label", "正在处理..."),
                "status": upd.get("status", "running"),
                "sub_steps": [],
            }

        target = steps_dict[sid]

        if "label" in upd:
            target["label"] = upd["label"]
        if "status" in upd:
            target["status"] = upd["status"]

        # 情况 A: 追加单个子步骤
        if "new_sub_step" in upd:
            sub = upd["new_sub_step"]
            new_sub = SubStep(
                message=sub["message"],
                type=sub.get("type", "info"),
                ts=sub.get("ts", time.time()),
                data=sub.get("data"),
            )
            if not target["sub_steps"] or target["sub_steps"][-1]["message"] != new_sub["message"]:
                target["sub_steps"].append(new_sub)

        # 情况 B: 合并全量子步骤列表
        elif "sub_steps" in upd:
            existing_messages = {ss["message"] for ss in target["sub_steps"]}
            for ss in upd["sub_steps"]:
                if ss["message"] not in existing_messages:
                    target["sub_steps"].append(ss)

    return list(steps_dict.values())


def merge_memory_state(existing: MemoryState | None, new: MemoryState | None) -> MemoryState:
    """组件合并器：深层合并 Memory 状态，解构并调用对应的 Reducer。"""
    existing_val = existing or {}
    new_val = new or {}
    
    merged: MemoryState = dict(existing_val) # type: ignore
    for k, v in new_val.items():
        if v is None:
            continue
        if k == "messages":
            merged["messages"] = add_messages(existing_val.get("messages") or [], v) # type: ignore
        elif k == "proven_facts":
            merged["proven_facts"] = merge_proven_facts(existing_val.get("proven_facts") or [], v) # type: ignore
        elif k == "follow_up_history":
            merged["follow_up_history"] = (existing_val.get("follow_up_history") or []) + list(v) # type: ignore
        else:
            merged[k] = v # type: ignore
    return merged


def merge_output_state(existing: OutputDiagnostics | None, new: OutputDiagnostics | None) -> OutputDiagnostics:
    """组件合并器：深层合并 Output & Diagnostics 状态。"""
    existing_val = existing or {}
    new_val = new or {}
    
    merged: OutputDiagnostics = {
        "diagnostics": cast(SharedDiagnostics, {**(existing_val.get("diagnostics") or {})}),
        "pipeline": cast(PipelineOutput, {**(existing_val.get("pipeline") or {})}),
        "agent": cast(AgentOutput, {**(existing_val.get("agent") or {})})
    }
    
    new_diag = new_val.get("diagnostics") or {}
    for k, v in new_diag.items():
        if v is None:
            continue
        if k == "thought_steps":
            merged["diagnostics"]["thought_steps"] = merge_thought_steps(
                merged["diagnostics"].get("thought_steps"), v # type: ignore
            )
        elif k == "warnings":
            merged["diagnostics"]["warnings"] = merge_warnings(
                merged["diagnostics"].get("warnings") or [], v # type: ignore
            )
        elif k == "error_log":
            merged["diagnostics"]["error_log"] = merge_error_log(
                merged["diagnostics"].get("error_log") or [], v # type: ignore
            )
        elif k == "store_refs":
            merged["diagnostics"]["store_refs"] = merge_store_refs(
                merged["diagnostics"].get("store_refs") or {}, v # type: ignore
            )
        else:
            merged["diagnostics"][k] = v # type: ignore
            
    new_pipe = new_val.get("pipeline") or {}
    for k, v in new_pipe.items():
        if v is not None:
            merged["pipeline"][k] = v # type: ignore
            
    new_agent = new_val.get("agent") or {}
    for k, v in new_agent.items():
        if v is not None:
            merged["agent"][k] = v # type: ignore
            
    return merged


def merge_context_state(existing: SessionContext | None, new: SessionContext | None) -> SessionContext:
    """组件合并器：浅合并 SessionContext。"""
    existing_val = existing or {}
    new_val = new or {}
    return {**existing_val, **new_val} # type: ignore


def merge_control_state(existing: ControlConfig | None, new: ControlConfig | None) -> ControlConfig:
    """组件合并器：浅合并 ControlConfig。"""
    existing_val = existing or {}
    new_val = new or {}
    return {**existing_val, **new_val} # type: ignore


def merge_interaction_state(existing: InteractionState | None, new: InteractionState | None) -> InteractionState:
    """组件合并器：浅合并 InteractionState。"""
    existing_val = existing or {}
    new_val = new or {}
    return {**existing_val, **new_val} # type: ignore


def merge_runtime_state(existing: RuntimeState | None, new: RuntimeState | None) -> RuntimeState:
    """组件合并器：二级深层合并 RuntimeState。"""
    existing_val = existing or {}
    new_val = new or {}
    
    merged: RuntimeState = {
        "shared": cast(SharedRuntime, {**(existing_val.get("shared") or {})}),
        "pipeline": cast(PipelineRuntime, {**(existing_val.get("pipeline") or {})}),
        "agent": cast(AgentRuntime, {**(existing_val.get("agent") or {})})
    }
    
    new_shared = new_val.get("shared") or {}
    for k, v in new_shared.items():
        if v is not None:
            merged["shared"][k] = v # type: ignore
            
    new_pipe = new_val.get("pipeline") or {}
    for k, v in new_pipe.items():
        if v is not None:
            merged["pipeline"][k] = v # type: ignore
            
    new_agent = new_val.get("agent") or {}
    for k, v in new_agent.items():
        if v is not None:
            merged["agent"][k] = v # type: ignore
            
    return merged


# ── 主主管线状态定义 ──

class ResearchState(TypedDict):
    context: Annotated[SessionContext, merge_context_state]
    control: Annotated[ControlConfig, merge_control_state]
    interaction: Annotated[InteractionState, merge_interaction_state]
    memory: Annotated[MemoryState, merge_memory_state]
    runtime: Annotated[RuntimeState, merge_runtime_state]
    output: Annotated[OutputDiagnostics, merge_output_state]


# ═══════════════════════════════════════════════════════════════
#  §F  VerifyState (验证子图状态)
# ═══════════════════════════════════════════════════════════════

class VerifyState(TypedDict, total=False):
    # ── 从 ResearchState 自动透传的输入字段 ──
    query: str
    intent_type: str
    dimensions: list[str]
    tenant_id: str
    user_id: str
    preset_id: str
    research_config: dict
    strategy_overrides: dict            # 策略覆盖参数，用于 LLM 调用配置
    verification_level: str                 # VerificationLevel
    store_refs: Annotated[dict[str, str], merge_store_refs]

    # ── 子图内部工作字段 ──
    _filtered_items: list[dict]
    claims: list[dict]
    source_profiles: dict[str, dict]

    # ── 思考链 (与 ResearchState 共享) ──
    thought_steps: Annotated[list[ThoughtStep], merge_thought_steps]

    # ── 输出字段（写回 ResearchState）──
    conflict_dimensions: list[str]
    insufficient_dimensions: list[str]
    overall_confidence: float
    warnings: Annotated[list[str], merge_warnings]
    error_log: Annotated[list[ErrorEntry], merge_error_log]
    proven_facts: list[dict]


# ═══════════════════════════════════════════════════════════════
#  §H  全局异常定义
# ═══════════════════════════════════════════════════════════════

class PipelineAbortError(Exception):
    """管线强制阻断异常：当遇到无法继续执行的致命错误（如全网均无搜索结果、信源全被过滤）时抛出，
    直接向上穿透以中止图流转，并触发前端渲染 error 事件。
    """
    pass
