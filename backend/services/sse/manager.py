"""SSE Producer — Worker 端执行 LangGraph 图并将事件发布到 Redis。

职责：
  1. 执行 graph.astream_events()（实际研究管线）
  2. 通过 parse_graph_events() 解析原始 LangGraph 事件为 SSE 格式
  3. 将 SSE 事件同时发布到 Redis PubSub（实时）和 Redis Stream（历史缓冲）
  4. 监听取消信号，支持 Worker 端的任务取消
  5. 执行完毕后归档结果到数据库

拆分自原 manager.py：
  - 流式推送部分 → consumer.py（API 端）
  - 图执行 + 事件发布部分保留在此（Worker 端）
"""
from __future__ import annotations
import asyncio
import json
import time
from typing import Any, cast

from backend.core.logging import logger, trace_id_var, task_id_var, mode_var
from backend.db.engine import async_session
from backend.db.store import ResearchStore
from backend.pipeline.types import ThoughtStep, merge_thought_steps
from backend.utils.redis import get_redis
from backend.db.models import ResearchTask
from backend.services.research_lifecycle import map_claims_to_frontend, _extract_research_conclusion, save_research_result
from backend.utils.llm_utils import clean_null_bytes
from sqlalchemy.ext.asyncio import AsyncSession

from .parser import parse_graph_events, safe_json_dumps

# SSE 事件缓存 Stream 最大长度
STREAM_MAXLEN = 500
# 分布式锁过期时间（秒）
LOCK_EXPIRE = 900


async def start_cancellation_listener() -> None:
    """启动 Redis Pub/Sub 广播订阅，监听来自 API 或其他副本的任务取消信号。"""
    logger.info("Worker 取消监听器启动成功，订阅频道: truthseeker:cancellations")
    retry_delay = 5.0
    consecutive_failures = 0
    while True:
        pubsub = None
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe("truthseeker:cancellations")

            if consecutive_failures > 0:
                logger.info("Worker 取消监听器已成功恢复连接。")
                consecutive_failures = 0
                retry_delay = 5.0

            while True:
                # 使用超时轮询而非阻塞 listen，防止连接被 Redis 服务端关闭后僵死
                message = await pubsub.get_message(timeout=5.0, ignore_subscribe_messages=True)
                if message is not None and message.get("type") == "message":
                    try:
                        payload_data = message.get("data")
                        if payload_data is None:
                            continue
                        if isinstance(payload_data, bytes):
                            payload_text = payload_data.decode("utf-8")
                        elif isinstance(payload_data, str):
                            payload_text = payload_data
                        else:
                            payload_text = str(payload_data)
                        payload = json.loads(payload_text)
                        research_id = payload.get("research_id")
                        logger.info("Worker 收到取消信号 | research_id={}", research_id)
                        # 取消当前正在执行的协程
                        current = asyncio.current_task()
                        if current and not current.done():
                            current.cancel()
                    except Exception as ex:
                        logger.error("解析取消广播消息失败 | error={}", ex)
        except asyncio.CancelledError:
            logger.info("Worker 取消监听器已正常取消。")
            break
        except Exception as e:
            consecutive_failures += 1
            logger.warning("Worker 取消监听器连接异常 (第{}次)，{}秒后重试 | error={}", consecutive_failures, int(retry_delay), e)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 1.5, 60.0)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.close()
                except Exception:
                    pass


async def execute_and_publish(
    graph: Any,
    input_data: Any,
    config: Any,
    tenant_id: str,
    user_id: str,
    research_id: str,
    task_id: str,
    raw_store: Any,
    start_time: float,
    db_bind: Any = None,
    existing_steps: list[dict] | None = None,
) -> str:
    """Worker 端核心函数：执行 LangGraph 图并实时发布 SSE 事件到 Redis。

    替代原 create_sse_handler 的 graph 执行部分。
    返回最终状态：completed / failed / paused / suspended。
    """
    redis = await get_redis()
    channel_name = f"sse:{task_id}"
    stream_name = f"sse_stream:{task_id}"

    trace_id_var.set(research_id)
    task_id_var.set(task_id)
    mode_var.set("")

    # ── 1. 同步已有 thought_steps ──────────────────────────────
    thought_steps: list[ThoughtStep] = cast(list[ThoughtStep], list(existing_steps or []))
    try:
        session_factory = AsyncSession(db_bind, expire_on_commit=False) if db_bind else async_session()
        async with session_factory as db:
            refreshed = await db.get(ResearchTask, task_id)
            if refreshed and refreshed.thought_steps:
                thought_steps = cast(list[ThoughtStep], refreshed.thought_steps)
    except Exception as e:
        logger.warning("Failed to refresh thought steps | error={}", e)

    # 同步 checkpointer 状态
    snapshot = None
    try:
        snapshot = await graph.aget_state(config)
        if snapshot and snapshot.values and "thought_steps" in snapshot.values:
            thought_steps = merge_thought_steps(thought_steps, snapshot.values["thought_steps"])
            sync_data = safe_json_dumps({"thought_steps": thought_steps, "task_id": task_id})
            await _publish_event(redis, channel_name, stream_name, f"event: sync\ndata: {sync_data}\n\n")
            logger.info("SSE 初始同步成功 | research_id={} task_id={} steps_count={}", research_id, task_id, len(thought_steps))
    except Exception as e:
        logger.warning("Initial snapshot sync failed | error={}", e)

    # ── 2. 获取分布式锁 ────────────────────────────────────────
    lock_key = f"lock:research:{research_id}"
    acquired = await redis.set(lock_key, task_id, nx=True, ex=LOCK_EXPIRE)
    if not acquired:
        existing_owner = await redis.get(lock_key)
        if existing_owner != task_id:
            logger.warning("分布式锁被占用 | key={} owner={}", lock_key, existing_owner)
            err_data = safe_json_dumps({"message": "该研究会话正在另一个任务中执行。"})
            await _publish_event(redis, channel_name, stream_name, f"event: error\ndata: {err_data}\n\n")
            return "failed"
        else:
            await redis.expire(lock_key, LOCK_EXPIRE)

    # ── 3. 执行图并发布事件 ────────────────────────────────────
    research_status = "running"
    is_breakpoint = False
    bp_type: str | None = None
    final_state: dict[str, Any] = {}

    try:
        had_error = False
        try:
            if input_data is None:
                if not snapshot or not snapshot.next:
                    err_data = safe_json_dumps({"message": "无法恢复研究任务：检查点已丢失。请重新发起。"})
                    await _publish_event(redis, channel_name, stream_name, f"event: error\ndata: {err_data}\n\n")
                    return "failed"

            logger.info("Worker 启动图执行 | research_id={} task_id={}", research_id, task_id)
            stream = graph.astream_events(input_data, config, version="v2")

            async for sse_line in parse_graph_events(stream, thought_steps_collector=cast(Any, thought_steps)):
                if "event: error" in sse_line:
                    had_error = True
                    research_status = "failed"
                # 续锁：每分钟续一次
                if time.time() % 60 < 1:
                    try:
                        await redis.expire(lock_key, LOCK_EXPIRE)
                    except Exception:
                        pass
                await _publish_event(redis, channel_name, stream_name, sse_line)

        except GeneratorExit:
            research_status = "paused"
            had_error = True

        # ── 4. 检查最终状态 ────────────────────────────────────
        snapshot = None
        if not had_error:
            snapshot = await graph.aget_state(config)
            if snapshot and snapshot.values:
                final_state = snapshot.values
                logger.info("图执行完成 | next_nodes={}", snapshot.next)

                interrupt_nodes = snapshot.next or []
                if any(n in interrupt_nodes for n in ["agent_node", "search_react"]):
                    is_breakpoint = True
                    research_status = "suspended"
                    bp_type = "dimensions"
                    payload = final_state.get("dimensions", [])

                    bp_data = {
                        "type": bp_type, "payload": payload,
                        "research_id": research_id, "task_id": task_id,
                    }
                    await _publish_event(redis, channel_name, stream_name,
                                         f"event: breakpoint\ndata: {safe_json_dumps(bp_data)}\n\n")
                    logger.warning("触发物理断点 | type={} research_id={}", bp_type, research_id)

                if not is_breakpoint and not snapshot.next:
                    # 🚨 升级：检查是否存在导致任务必须失败的严重错误记录
                    critical_errors = [err for err in final_state.get("error_log", []) if isinstance(err, dict) or hasattr(err, "message")]
                    if critical_errors:
                        research_status = "failed"
                        logger.warning("管线因严重错误被判定为 failed | research_id={}", research_id)
                    else:
                        research_status = "completed"
                        logger.info("管线执行完成 | research_id={}", research_id)

                    final_mapped_claims = []
                    raw_claims = []
                    execution_mode = final_state.get("execution_mode", "research_pipeline")
                    try:
                        rs = ResearchStore(raw_store, tenant_id=tenant_id, research_id=research_id, task_id=task_id)
                        raw_claims = await rs.load_claims("final")
                        if raw_claims and execution_mode == "research_pipeline":
                            final_mapped_claims = map_claims_to_frontend(raw_claims)
                    except Exception as e:
                        logger.error("加载结论面板失败 | error={}", e)

                    report = (final_state.get("output") or {}).get("agent", {}).get("report_prompt", "") or \
                             (final_state.get("output") or {}).get("pipeline", {}).get("report_prompt", "") or \
                             final_state.get("report_prompt", "") or final_state.get("report", "")
                    research_conclusion = None
                    if report:
                        try:
                            research_conclusion = _extract_research_conclusion(
                                report=report, dimensions=final_state.get("dimensions", []),
                                claims=raw_claims or [],
                                overall_confidence=final_state.get("overall_confidence", 0.0),
                                history_summary=final_state.get("history_summary"),
                            )
                        except Exception:
                            pass

                    serialized_errors = [vars(err) if hasattr(err, "__dict__") else err
                                         for err in final_state.get("error_log", [])]
                    complete_data = {
                        "research_id": research_id, "task_id": task_id,
                        "claims": final_mapped_claims,
                        "warnings": final_state.get("warnings", []),
                        "error_log": serialized_errors,
                        "confidence": final_state.get("overall_confidence", 0.0),
                        "conflict_dimensions": final_state.get("conflict_dimensions", []),
                        "duration_seconds": int(time.time() - start_time),
                        "report": report,
                        "research_conclusion": research_conclusion,
                        "message": "Research complete. All data has been archived.",
                    }
                    await _publish_event(redis, channel_name, stream_name,
                                         f"event: complete\ndata: {safe_json_dumps(complete_data)}\n\n")
                elif not is_breakpoint and snapshot.next:
                    research_status = "running"

    except GeneratorExit:
        research_status = "paused"
        logger.info("Worker 任务被暂停 | research_id={}", research_id)
    except asyncio.CancelledError:
        research_status = "failed"
        logger.info("Worker 任务被取消 | research_id={}", research_id)
    except Exception as e:
        research_status = "failed"
        logger.exception("Worker 图执行异常 | id={} error={}", research_id, e)
        err_data = safe_json_dumps({"message": f"Execution error: {str(e)}"})
        await _publish_event(redis, channel_name, stream_name, f"event: error\ndata: {err_data}\n\n")
    finally:
        # 释放锁
        try:
            await redis.delete(lock_key)
        except Exception:
            pass

        # 归档结果到数据库
        await _do_archive(
            db_bind=db_bind,
            tenant_id=tenant_id,
            research_id=research_id,
            task_id=task_id,
            final_state=final_state,
            raw_store=raw_store,
            start_time=start_time,
            status=research_status,
            thought_steps=thought_steps,
            is_breakpoint=is_breakpoint,
            bp_type=bp_type,
        )

        logger.info("Worker 任务归档完毕 | research_id={} status={}", research_id, research_status)

    return research_status


async def _publish_event(redis, channel: str, stream: str, sse_line: str) -> None:
    """同时发布 SSE 事件到 Redis PubSub（实时）和 Redis Stream（历史缓冲）。"""
    try:
        await redis.publish(channel, sse_line)
        await redis.xadd(stream, {"data": sse_line}, maxlen=STREAM_MAXLEN)
    except Exception as e:
        logger.warning("发布 SSE 事件失败 | channel={} error={}", channel, e)


async def _do_archive(
    db_bind: Any,
    tenant_id: str,
    research_id: str,
    task_id: str,
    final_state: dict[str, Any],
    raw_store: Any,
    start_time: float,
    status: str,
    thought_steps: list[ThoughtStep],
    is_breakpoint: bool,
    bp_type: str | None,
) -> None:
    """归档研究结果到数据库。"""
    try:
        safe_final_state = clean_null_bytes(final_state)
        safe_thought_steps = clean_null_bytes(cast(Any, thought_steps))

        db_session = AsyncSession(db_bind, expire_on_commit=False) if db_bind else async_session()
        async with db_session as db:
            try:
                await save_research_result(
                    db=db, tenant_id=tenant_id, research_id=research_id,
                    task_id=task_id, final_state=safe_final_state,
                    raw_store=raw_store, start_time=start_time,
                    status=status, thought_steps=safe_thought_steps,
                    pending_approval=is_breakpoint, breakpoint_type=bp_type,
                )
                await db.commit()
            except Exception as e:
                logger.error("归档失败 | id={} task_id={} error={}", research_id, task_id, e)
    except Exception as e:
        logger.error("归档流程异常 | error={}", e)
