"""Service for managing LangGraph engine, session states, and research lifecycle."""
from __future__ import annotations
from typing import Any
from fastapi import Request
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from backend.pipeline.graph import compile_graph
from backend.core.logging import logger


class ResearchEngineService:
    """Service to handle LangGraph compilation and session management."""
    
    def __init__(self, request: Request, enable_hitl: bool = False):
        self.app_state = request.app.state
        self.store = getattr(self.app_state, "store", None)
        self.checkpointer = getattr(self.app_state, "checkpointer", None)
        self.graph = getattr(self.app_state, "graph_hitl" if enable_hitl else "graph_auto", None)
        
        if self.graph is None:
            logger.warning("ResearchEngineService: Falling back to in-memory LangGraph components.")
            self.store = InMemoryStore()
            self.checkpointer = MemorySaver()
            self.graph = compile_graph(checkpointer=self.checkpointer, store=self.store, enable_hitl=enable_hitl)

    def get_graph(self) -> Any:
        """Return the compiled graph instance."""
        return self.graph

    def get_run_config(self, research_id: str, tenant_id: str, user_id: str, preset_id: str | None, *, task_id: str | None = None) -> dict[str, Any]:
        """Generate the standard configuration for LangGraph operations.
        
        thread_id 使用 task_id (Task 级 Checkpointer 隔离)，fallback 到 research_id (兼容旧逻辑)。
        """
        effective_thread_id = task_id or research_id
        return {
            "configurable": {
                "thread_id": effective_thread_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "research_id": research_id,
                "task_id": task_id or "",
                "preset_id": preset_id,
                "store": self.store
            }
        }

    async def get_current_state(self, graph: Any, config: dict[str, Any]) -> Any:
        """Fetch the current execution state snapshot."""
        return await graph.aget_state(config)
