from __future__ import annotations
import json
import asyncio
from contextvars import ContextVar
from typing import AsyncIterator, Any, cast
import backend.core.logging as logging_module
from backend.core.logging import mode_var
from backend.pipeline.types import merge_thought_steps


from .processor import ThinkingTagProcessor


# 搜索 Agent / 子图内部的模型流式事件是否被抑制（如 search_react 的内部思考不推送给前端）
suppress_model_stream: ContextVar[bool] = ContextVar("suppress_model_stream", default=False)


def safe_json_dumps(obj: Any) -> str:
    """安全的 JSON 序列化，防止因 emoji 等特殊 Unicode 字符导致的编码崩溃"""
    try:
        raw = json.dumps(obj, ensure_ascii=False)
        return raw.encode('utf-8', 'surrogatepass').decode('utf-8')
    except (ValueError, UnicodeDecodeError, UnicodeEncodeError):
        return json.dumps(obj, ensure_ascii=True)


async def parse_graph_events(
    event_stream: AsyncIterator[dict[str, Any]],
    thought_steps_collector: list[dict] | None = None,
) -> AsyncIterator[str]:
    """
    Parses LangGraph astream_events and transforms them into SSE format.
    """
    async def iterate_with_heartbeat(iterator: AsyncIterator[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        next_item_task = None
        try:
            while True:
                if next_item_task is None:
                    next_item_task = asyncio.create_task(cast(Any, anext(iterator)))

                done, _ = await asyncio.wait([next_item_task], timeout=15.0)

                if next_item_task in done:
                    try:
                        event = next_item_task.result()
                        next_item_task = None
                        yield event
                    except StopAsyncIteration:
                        break
                else:
                    yield {"event": "heartbeat"}
        finally:
            if next_item_task and not next_item_task.done():
                next_item_task.cancel()
                try:
                    await next_item_task
                except (asyncio.CancelledError, StopAsyncIteration):
                    pass

    processor = ThinkingTagProcessor()

    try:
        async for event in iterate_with_heartbeat(event_stream):
            event_type = event.get("event")

            if event_type == "heartbeat":
                yield ": heartbeat\n\n"
                continue

            if event_type == "on_chain_stream":
                chunk = event.get("data", {}).get("chunk", {})
                if isinstance(chunk, dict):
                    if "thought_steps" not in chunk:
                        nested_ts = chunk.get("output", {}).get("diagnostics", {}).get("thought_steps")
                        if nested_ts is not None:
                            chunk["thought_steps"] = nested_ts

                    if "thought_steps" in chunk:
                        updates = chunk["thought_steps"]

                        if thought_steps_collector is not None:
                            new_steps = merge_thought_steps(cast(Any, thought_steps_collector), updates)
                            thought_steps_collector[:] = cast(Any, new_steps)

                        primary = cast(dict, updates[0] if updates else {})
                        sub_msg = primary.get("new_sub_step", {}).get("message", "")

                        compat_data = {
                            "thought_steps": thought_steps_collector,
                            "step": primary.get("id"),
                            "key": primary.get("id"),
                            "status": primary.get("status", "running"),
                            "message": sub_msg or primary.get("label", "Processing..."),
                        }
                        yield f"event: progress\ndata: {safe_json_dumps(compat_data)}\n\n"

                # Agent 报告伪造流式：agent_report_node 切块 yield 的内容 → token 事件
                if isinstance(chunk, dict):
                    report_chunk = chunk.get("output", {}).get("agent", {}).get("report_chunk")
                    if report_chunk:
                        yield f"event: token\ndata: {safe_json_dumps({'text': report_chunk})}\n\n"

                if isinstance(chunk, dict):
                    meta_updates = {}
                    if "strategy_overrides" in chunk:
                        meta_updates["strategy_overrides"] = chunk["strategy_overrides"]
                    if "execution_mode" in chunk:
                        meta_updates["execution_mode"] = chunk["execution_mode"]
                        mode_var.set(chunk["execution_mode"])

                    if meta_updates:
                        yield f"event: metadata\ndata: {safe_json_dumps(meta_updates)}\n\n"

            elif event_type == "on_chat_model_stream":
                chunk_obj = event.get("data", {}).get("chunk")
                if not chunk_obj or not hasattr(chunk_obj, "content") or not chunk_obj.content:
                    continue

                metadata = cast(dict[str, Any], event.get("metadata", {}))
                node_name = metadata.get("langgraph_node", "")
                has_tool_call = hasattr(chunk_obj, "tool_call_chunks") and chunk_obj.tool_call_chunks

                # 1. 模型原生 reasoning_content（如 deepseek-reasoner）→ 独立 agent_think 事件
                metadata = chunk_obj.response_metadata or {}
                reasoning = metadata.get("reasoning_content") or chunk_obj.additional_kwargs.get("reasoning_content")
                if reasoning:
                    if not suppress_model_stream.get():
                        yield f"event: agent_think\ndata: {safe_json_dumps({'text': reasoning})}\n\n"

                # 2. create_agent（model）+ 主图节点流式内容（抑制的节点不输出 token）
                if (node_name in {"model"} or node_name.startswith("agent_node/")) and not suppress_model_stream.get():
                    if not has_tool_call:
                        text = processor.process(str(chunk_obj.content))
                        if text:
                            yield f"event: token\ndata: {safe_json_dumps({'text': text})}\n\n"
                # 3. 报告生成节点 → token
                elif node_name in {"generate_report_prompt"}:
                    text = processor.process(str(chunk_obj.content))
                    if text:
                        yield f"event: token\ndata: {safe_json_dumps({'text': text})}\n\n"
    except Exception as e:
        logging_module.logger.exception("parse_graph_events encountered an error: {}", e)
        yield f"event: error\ndata: {safe_json_dumps({'message': str(e)})}\n\n"
