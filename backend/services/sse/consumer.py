"""SSE Consumer — API 端从 Redis 消费研究任务事件并转发到前端。

拆分自 manager.py 的 SSE 流式转发部分：
  - 订阅 Redis PubSub 频道 sse:{task_id} 接收实时事件
  - 断线重连时先从 Redis Stream 回放历史事件
  - API 侧独立生成心跳（不依赖 Worker 进度）
  - 客户端断开时广播取消信号通知 Worker 停止
"""
from __future__ import annotations
import asyncio
import json
import time
from typing import AsyncIterator

from backend.core.logging import logger
from backend.utils.redis import get_redis


async def sse_from_redis(
    task_id: str,
    research_id: str,
) -> AsyncIterator[str]:
    """从 Redis 消费 SSE 事件并转发到客户端。

    工作流程：
      1. 先读取 Redis Stream 中保留的历史事件（断线重连）
      2. 订阅 Redis PubSub 接收实时事件
      3. 同时以 15 秒间隔发送心跳保活
      4. 客户端断开时发送取消广播通知 Worker
    """
    redis = await get_redis()
    pubsub = redis.pubsub()
    channel_name = f"sse:{task_id}"

    # ── 1. 发送连接成功信号 ───────────────────────────────────
    yield ": connected\n\n"

    # ── 2. 回放历史事件（断线重连） ────────────────────────────
    stream_name = f"sse_stream:{task_id}"
    try:
        # 读取最近 500 条历史事件
        history = await redis.xrevrange(stream_name, count=500)
        for _, fields in reversed(history or []):
            if fields is None:
                continue
            data = fields.get(b"data", fields.get("data", b""))
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if data:
                yield data
    except Exception as e:
        logger.warning("SSE 历史事件回放失败 | stream={} error={}", stream_name, e)

    # ── 3. 订阅实时频道 ────────────────────────────────────────
    await pubsub.subscribe(channel_name)

    # ── 4. 轮询模式：每 5 秒检查一次 PubSub + 每 15 秒心跳 ──
    heartbeat_interval = 15.0
    last_heartbeat = time.time()
    cancelled = False

    try:
        while not cancelled:
            # 拉取一条 PubSub 消息（5 秒超时）
            try:
                message = await pubsub.get_message(timeout=5.0, ignore_subscribe_messages=True)
            except asyncio.TimeoutError:
                message = None

            if message is not None and message.get("type") == "message":
                raw = message.get("data", "")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                if raw:
                    yield raw
                    if "event: complete" in raw or "event: error" in raw:
                        cancelled = True
                        return

            # 心跳
            now = time.time()
            if now - last_heartbeat >= heartbeat_interval:
                yield ": heartbeat\n\n"
                last_heartbeat = now

    except GeneratorExit:
        # 客户端主动断开 → 广播取消信号给 Worker
        logger.info("SSE 客户端断开连接 | task_id={}", task_id)
        cancelled = True
        await _publish_cancellation(redis, research_id)
    except asyncio.CancelledError:
        logger.info("SSE 消费者被取消 | task_id={}", task_id)
    except Exception as e:
        logger.exception("SSE 消费异常 | task_id={} error={}", task_id, e)
    finally:
        cancelled = True
        try:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()
        except Exception:
            pass


async def _publish_cancellation(redis, research_id: str) -> None:
    """发送取消信号给所有 Worker。"""
    import uuid
    payload = json.dumps({
        "research_id": research_id,
        "exclude_run_uuid": str(uuid.uuid4()),
    })
    try:
        await redis.publish("truthseeker:cancellations", payload)
    except Exception as e:
        logger.warning("发送取消广播失败 | research_id={} error={}", research_id, e)
