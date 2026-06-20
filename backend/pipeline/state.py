"""pipeline/state.py — ResearchState 入口（从 types.py 透明重导出）。

⚠️ 本文件仅做向后兼容桥接。所有类型定义已迁移至 pipeline/types.py。
⚠️ 所有新代码应直接从 pipeline.types 或 pipeline.constants 导入。

外部消费者（保持向后兼容）：
  - create_initial_state     → api/chat.py, tests/*
  - merge_thought_steps      → api/events.py
  - serialize_state          → worker.py (Redis 入队序列化)
  - deserialize_state        → worker.py (Redis 出队反序列化)
"""
from __future__ import annotations
import json
import time
from dataclasses import asdict
from typing import Any, Literal
from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict
from backend.pipeline.types import ResearchState, ErrorEntry


class StateHelper:
    """ResearchState 的便捷访问代理和操作助手。
    职责：
      1. 屏蔽深层嵌套字典的访问细节 (state["runtime"]["pipeline"].get(...))。
      2. 提供语义化的状态读取属性。
      3. 提供标准化的状态更新构造方法。
    """
    def __init__(self, state: ResearchState):
        self._state = state

    # ── 基础信息 (Context & Control) ──
    @property
    def query(self) -> str:
        return self._state["runtime"]["shared"].get("query", "")

    @property
    def research_id(self) -> str:
        return self._state["context"].get("research_id", "")

    @property
    def user_id(self) -> str:
        return self._state["context"].get("user_id", "default")

    @property
    def speed(self) -> str:
        return self._state["control"].get("speed", "research_pipeline")

    # ── 业务状态 (Runtime) ──
    @property
    def dimensions(self) -> list[str]:
        return self._state["runtime"]["pipeline"].get("dimensions", [])

    @property
    def intent_type(self) -> str:
        return self._state["runtime"]["shared"].get("intent_type", "explore")

    @property
    def search_round(self) -> int:
        return self._state["runtime"]["pipeline"].get("search_round", 0)

    @property
    def strategy_overrides(self) -> dict[str, Any]:
        return self._state["runtime"]["pipeline"].get("strategy_overrides", {})

    # ── 辅助方法：构造更新 ──
    @staticmethod
    def update_thought_step(step_id: str, message: str, type: str = "info", status: str = "running", label: str | None = None) -> dict:
        """快速构造一个思考链更新字典"""
        step_data: dict[str, Any] = {"id": step_id, "status": status}
        if label:
            step_data["label"] = label
        if message:
            step_data["new_sub_step"] = {"message": message, "type": type, "ts": time.time()}
        
        return {"output": {"diagnostics": {"thought_steps": [step_data]}}}

    @staticmethod
    def add_error(node: str, message: str, detail: str | None = None) -> dict:
        """快速构造一个错误日志更新字典"""
        return {
            "output": {
                "diagnostics": {
                    "error_log": [ErrorEntry(node=node, message=message, detail=detail)]
                }
            }
        }

    @staticmethod
    def add_warning(warning: str) -> dict:
        """快速构造一个警告更新字典"""
        return {"output": {"diagnostics": {"warnings": [warning]}}}


def create_initial_state(
    query: str,
    research_id: str,
    tenant_id: str,
    user_id: str = "default",
    *,
    task_id: str | None = None,
    preset_id: str | None = None,
    context_mode: str = "new_research",
    speed: Literal["fast_react", "expert_search", "research_pipeline"] = "research_pipeline",
    execution_mode: Literal["auto", "preset"] = "auto",
    enable_hitl: bool = False,
    messages: list[Any] | None = None,
    last_research_summary: str = "",
    last_research_dimensions: list[str] | None = None,
    last_unresolved: list[str] | None = None,
    follow_up_history: list[dict] | None = None,
    media_inputs: list[dict] | None = None,
    original_query: str | None = None,
    history_summary: str = "",
    proven_facts: list[dict] | None = None,
) -> ResearchState:
    """初始化嵌套的 ResearchState 实例"""
    state_dict = ResearchState(
        context={
            "research_id": research_id,
            "task_id": task_id or "",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "preset_id": preset_id,
            "context_mode": context_mode,
        },
        control={
            "execution_mode": execution_mode,
            "speed": speed,
            "enable_hitl": enable_hitl,
        },
        interaction={
            "breakpoint_type": "none",
            "dimensions_approved": False,
            "sources_approved": False,
            "approved_dimensions": [],
            "approved_sources": [],
            "force_summarize": False,
        },
        memory={
            "messages": messages or [],
            "follow_up_history": follow_up_history or [],
            "history_summary": history_summary,
            "proven_facts": proven_facts or [],
            "short_term_memory": "",
        },
        runtime={
            "shared": {
                "query": query,
                "original_query": original_query or query,
                "intent_type": "",
                "_suggested_engines": [],
                "last_research_summary": last_research_summary,
                "last_research_dimensions": last_research_dimensions or [],
                "last_unresolved": last_unresolved or [],
                "media_inputs": media_inputs or [],
                "manual_injections": [],
                "rejected_urls": [],
            },
            "pipeline": {
                "search_plan": "",
                "search_keywords": [],
                "display_keywords": [],
                "dimensions": [],
                "search_tasks": [],
                "search_round": 0,
                "search_iteration": 0,
                "needs_more_search": False,
                "searched_keywords_history": [],
                "insufficient_dimensions": [],
                "conflict_dimensions": [],
                "strategy_overrides": {},
                "search_strategy": "broad",
                "valuable_urls": [],
            },
            "agent": {
                "iteration_count": 0,
                "max_results_per_query": None,
            },
        },
        output={
            "diagnostics": {
                "thought_steps": [],
                "warnings": [],
                "error_log": [],
                "store_refs": {},
            },
            "pipeline": {
                "report_prompt": "",
                "report_instruction": "",
                "overall_confidence": 0.0,
            },
            "agent": {
                "report_prompt": "",
            },
        },
    )

    return state_dict


# ═══════════════════════════════════════════════════════════════
#  ResearchState 序列化工具（Worker 跨进程传递）
# ═══════════════════════════════════════════════════════════════

def _serialize_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """将 list[BaseMessage] 转为 JSON 可序列化的 list[dict]"""
    return [message_to_dict(m) for m in messages]


def _deserialize_messages(messages: list[dict[str, Any]]) -> list[BaseMessage]:
    """将 JSON 反序列化的 dict 恢复为 list[BaseMessage]"""
    return messages_from_dict(messages)


def _serialize_error_log(error_log: list[ErrorEntry]) -> list[dict[str, Any]]:
    """将 list[ErrorEntry] 转为普通 dict"""
    return [asdict(e) for e in error_log]


def _deserialize_error_log(error_log: list[dict[str, Any]]) -> list[ErrorEntry]:
    """将 dict 恢复为 list[ErrorEntry]"""
    return [ErrorEntry(**e) for e in error_log]


def serialize_state(state: dict[str, Any]) -> dict[str, Any]:
    """将 ResearchState 转为 JSON 可序列化的纯 dict。

    处理：
      - memory.messages:  BaseMessage → dict
      - output.diagnostics.error_log: ErrorEntry → dict
    """
    result = _deep_copy(state)

    # 序列化 messages
    messages = result.get("memory", {}).get("messages")
    if messages and isinstance(messages, list) and messages and hasattr(messages[0], "type"):
        result["memory"]["messages"] = _serialize_messages(messages)

    # 序列化 error_log
    error_log = result.get("output", {}).get("diagnostics", {}).get("error_log")
    if error_log and isinstance(error_log, list) and error_log and isinstance(error_log[0], ErrorEntry):
        result["output"]["diagnostics"]["error_log"] = _serialize_error_log(error_log)

    return result


def deserialize_state(state: dict[str, Any]) -> dict[str, Any]:
    """将 Redis 反序列化的纯 dict 恢复为 ResearchState 兼容结构。"""
    result = _deep_copy(state)

    # 反序列化 messages
    messages = result.get("memory", {}).get("messages")
    if messages and isinstance(messages, list) and messages and isinstance(messages[0], dict):
        result["memory"]["messages"] = _deserialize_messages(messages)

    # 反序列化 error_log
    error_log = result.get("output", {}).get("diagnostics", {}).get("error_log")
    if error_log and isinstance(error_log, list) and error_log and isinstance(error_log[0], dict):
        result["output"]["diagnostics"]["error_log"] = _deserialize_error_log(error_log)

    return result


def _deep_copy(obj: Any) -> Any:
    """简易深拷贝：JSON round-trip 用于纯 dict/list 结构。

    ResearchState 序列化后应不包含复杂对象，故 JSON round-trip 安全。
    """
    return json.loads(json.dumps(obj, default=str))
