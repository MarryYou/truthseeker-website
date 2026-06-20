"""verify 子图图定义 — 编排 4 个节点：atomize → profile → tripartite → arbitrate"""
from __future__ import annotations
from typing import Any, cast
from langgraph.graph import StateGraph, END

from backend.pipeline.subgraphs.verify.state import VerifyState
from backend.pipeline.subgraphs.verify.atomize import atomize_node
from backend.pipeline.subgraphs.verify.profile import profile_node
from backend.pipeline.subgraphs.verify.tripartite import tripartite_node
from backend.pipeline.subgraphs.verify.arbitrate import arbitrate_node


def _route_verify_start(state: VerifyState) -> str:
    """核验子图入口路由：在 standard 和 strict 模式下都运行 atomize 提取声明"""
    vl = state.get("verification_level", "standard")
    if vl in ("standard", "strict"):
        return "atomize"
    return "profile"


def _route_after_profile(state: VerifyState) -> str:
    """信源画像后路由：在 standard 和 strict 模式下都运行 tripartite 跨源校验"""
    vl = state.get("verification_level", "standard")
    if vl in ("standard", "strict"):
        return "tripartite"
    return "arbitrate"


def build_verify_subgraph() -> StateGraph:
    """构建 verify 子图（未编译），供测试复用。"""
    g = StateGraph(cast(Any, VerifyState))

    g.add_node("atomize", atomize_node)
    g.add_node("profile", profile_node)
    g.add_node("tripartite", tripartite_node)
    g.add_node("arbitrate", arbitrate_node)

    g.set_conditional_entry_point(
        _route_verify_start,
        {
            "atomize": "atomize",
            "profile": "profile"
        }
    )
    g.add_edge("atomize", "profile")
    g.add_conditional_edges(
        "profile",
        _route_after_profile,
        {
            "tripartite": "tripartite",
            "arbitrate": "arbitrate"
        }
    )
    g.add_edge("tripartite", "arbitrate")
    g.add_edge("arbitrate", END)

    return g


# 编译好的子图实例，供主图直接挂载为节点
verify_subgraph = build_verify_subgraph().compile()
