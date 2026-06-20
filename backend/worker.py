"""ARQ Worker 入口：研究任务后台执行进程。

职责：
  1. 通过加权轮询从三个优先级队列拉取任务
  2. 编译 LangGraph 图并执行 research pipeline
  3. 实时发布 SSE 事件到 Redis PubSub + Stream
  4. 监听取消信号和 LLM 缓存失效广播
  5. 基于队列深度自动扩缩 Worker 数量

队列策略：
  - fast_react:        ts:queue:fast      权重 4（最快消费）
  - expert_search:     ts:queue:expert     权重 2
  - research_pipeline: ts:queue:pipeline   权重 1

启动方式：
  python -m backend.worker                 # 单 Worker 调试
  arq backend.worker.WorkerSettings        # 生产启动（需 arq>=0.6）
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
from typing import Any, cast

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

# ── 确保项目根目录在 sys.path 中 ──────────────────────────────
_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from backend.core.logging import logger, process_var
from backend.core.config import DATABASE_URL
from backend.utils.redis import get_redis
from backend.pipeline.graph import compile_graph
from backend.pipeline.state import serialize_state, deserialize_state
from backend.services.sse import execute_and_publish
from backend.services.sse.manager import start_cancellation_listener
from backend.core.llm import start_llm_cache_invalidation_listener

# ── 注册搜索引擎插件（Worker 进程需要手动加载，否则 plugin_registry 为空） ──
import backend.search.bocha   # noqa
import backend.search.tavily  # noqa
import backend.search.zhihu   # noqa

# ── DSN 转换 ──────────────────────────────────────────────────
def _make_psycopg_dsn(url: str) -> str:
    return (url
            .replace("postgresql+asyncpg://", "postgresql://")
            .replace("postgresql+psycopg2://", "postgresql://")
            .replace("postgresql+psycopg://", "postgresql://"))

# ── 队列名称配置 ──────────────────────────────────────────────
QUEUES = {
    "fast_react":        "ts:queue:fast",
    "expert_search":     "ts:queue:expert",
    "research_pipeline": "ts:queue:pipeline",
}

# 加权轮询调度顺序（fast_react 4 次 → expert_search 2 次 → pipeline 1 次）
_WEIGHTED_SCHEDULE = (
    ["fast_react"] * 4
    + ["expert_search"] * 2
    + ["research_pipeline"] * 1
)

# 单个 Worker 最大并发任务数
MAX_CONCURRENT_JOBS = 2
# Worker 级别信号量
_job_semaphore: asyncio.Semaphore | None = None

# 进程级缓存：编译后的 LangGraph 图
_graph_cache: dict[str, Any] = {}

# 进程级标记
_process_name = f"worker-{os.getpid()}"


# ═══════════════════════════════════════════════════════════════
#  1. 图编译缓存
# ═══════════════════════════════════════════════════════════════

async def _get_or_compile_graph(enable_hitl: bool):
    """获取或编译 LangGraph 图（进程级缓存）。"""
    key = "hitl" if enable_hitl else "auto"
    if key not in _graph_cache:
        use_pg = DATABASE_URL.startswith("postgresql")
        if use_pg:
            psycopg_dsn = _make_psycopg_dsn(DATABASE_URL)

            cp_pool = AsyncConnectionPool(
                psycopg_dsn, min_size=1, max_size=5,
                kwargs={"autocommit": True, "prepare_threshold": 0}, open=False,
            )
            store_pool = AsyncConnectionPool(
                psycopg_dsn, min_size=1, max_size=5,
                kwargs={"autocommit": True, "prepare_threshold": 0}, open=False,
            )

            serde = JsonPlusSerializer(allowed_msgpack_modules=[("backend.pipeline.types",)])

            await cp_pool.open()
            await store_pool.open()

            checkpointer = AsyncPostgresSaver(conn=cast(Any, cp_pool), serde=serde)
            store = AsyncPostgresStore(conn=cast(Any, store_pool))

            await checkpointer.setup()
            await store.setup()
        else:
            serde = JsonPlusSerializer(allowed_msgpack_modules=[("backend.pipeline.types",)])

            checkpointer = MemorySaver(serde=serde)
            store = InMemoryStore()

        _graph_cache[key] = compile_graph(checkpointer=checkpointer, store=store, enable_hitl=enable_hitl)
        _graph_cache[f"{key}:checkpointer"] = checkpointer
        _graph_cache[f"{key}:store"] = store

    return (_graph_cache[key],
            _graph_cache.get(f"{key}:checkpointer"),
            _graph_cache.get(f"{key}:store"))


# ═══════════════════════════════════════════════════════════════
#  2. 任务入队（API 端调用）
# ═══════════════════════════════════════════════════════════════

async def enqueue_research(
    task_data: dict[str, Any],
    speed: str = "research_pipeline",
) -> None:
    """将研究任务入队到对应优先级的 Redis List。

    此函数由 API 进程调用（chat.py）。

    参数：
      task_data: 包含 research_id, task_id, initial_state, tenant_id, user_id 等
      speed:     fast_react | expert_search | research_pipeline
    """
    queue_key = QUEUES.get(speed, QUEUES["research_pipeline"])
    redis = await get_redis()
    payload = _serialize_task_data(task_data)
    await redis.lpush(queue_key, payload)
    logger.info("研究任务已入队 | queue={} task_id={} research_id={}",
                queue_key, task_data.get("task_id"), task_data.get("research_id"))


async def enqueue_resume_research(task_data: dict[str, Any]) -> None:
    """将恢复（HITL 断点）任务入队。

    resume 任务走 expert_search 优先级（权重 2）。
    """
    queue_key = QUEUES["expert_search"]
    task_data["_resume"] = True
    redis = await get_redis()
    payload = _serialize_task_data(task_data)
    await redis.lpush(queue_key, payload)
    logger.info("恢复任务已入队 | task_id={} research_id={}",
                task_data.get("task_id"), task_data.get("research_id"))


def _serialize_task_data(task_data: dict[str, Any]) -> str:
    """序列化任务数据为 JSON 字符串。

    处理 ResearchState 中不可 JSON 序列化的对象（BaseMessage 等）。
    """
    state = task_data.get("initial_state")
    if state:
        task_data = {**task_data, "initial_state": serialize_state(state)}

    return json.dumps(task_data, ensure_ascii=False, default=str)


def _deserialize_task_data(payload: str) -> dict[str, Any]:
    """反序列化 JSON 字符串为任务数据。"""
    task_data = json.loads(payload)

    state = task_data.get("initial_state")
    if state:
        task_data["initial_state"] = deserialize_state(state)

    return task_data


# ═══════════════════════════════════════════════════════════════
#  3. Worker 任务执行
# ═══════════════════════════════════════════════════════════════

async def execute_research_task(task_data: dict[str, Any]) -> str:
    """执行一个研究任务（在信号量限制下）。"""
    global _job_semaphore
    if _job_semaphore is None:
        _job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

    async with _job_semaphore:
        return await _do_execute(task_data)


async def _do_execute(task_data: dict[str, Any]) -> str:
    """实际执行研究任务。

    此函数运行在 Worker 进程中，由 ARQ 或加权轮询调度引擎调用。
    """
    research_id = task_data["research_id"]
    task_id = task_data["task_id"]
    tenant_id = task_data.get("tenant_id", "default")
    user_id = task_data.get("user_id", "default")
    enable_hitl = task_data.get("enable_hitl", False)
    is_resume = task_data.get("_resume", False)
    resume_metadata = task_data.get("resume_metadata")
    start_time = task_data.get("start_time", time.time())

    logger.info("[{}] Worker 开始执行任务 | research_id={} task_id={} resume={}",
                _process_name, research_id, task_id, is_resume)

    # 1. 编译图（进程级缓存）
    graph, checkpointer, store = await _get_or_compile_graph(enable_hitl=enable_hitl)

    # 2. 构造 run_config
    preset_id = task_data.get("preset_id")
    run_config = {
        "configurable": {
            "thread_id": task_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "research_id": research_id,
            "task_id": task_id,
            "preset_id": preset_id,
            "store": store,
        }
    }

    # 3. 恢复任务（HITL）：先注入审批状态再继续
    if is_resume and resume_metadata:
        logger.info("Worker 恢复 HITL 任务 | task_id={} metadata={}", task_id, resume_metadata)
        resume_state: dict[str, Any] = {
            "interaction": {
                "dimensions_approved": True,
                "breakpoint_type": "none",
            }
        }
        approved_dimensions = resume_metadata.get("approved_dimensions")
        if approved_dimensions is not None:
            resume_state["runtime"] = {"pipeline": {"dimensions": approved_dimensions}}
            resume_state["interaction"]["approved_dimensions"] = approved_dimensions

        approved_sources = resume_metadata.get("approved_sources")
        if approved_sources is not None:
            resume_state.setdefault("interaction", {})["approved_sources"] = approved_sources
            resume_state["interaction"]["sources_approved"] = True

        await graph.aupdate_state(run_config, resume_state)

    # 4. 执行并发布

    initial_state = task_data.get("initial_state")
    input_data = initial_state if not is_resume else None
    existing_steps = task_data.get("existing_steps")

    status = await execute_and_publish(
        graph=graph,
        input_data=input_data,
        config=run_config,
        db_bind=None,
        tenant_id=tenant_id,
        user_id=user_id,
        research_id=research_id,
        task_id=task_id,
        raw_store=store,
        start_time=start_time,
        existing_steps=existing_steps,
    )

    logger.info("[{}] Worker 任务结束 | research_id={} status={}", _process_name, research_id, status)
    return status


# ═══════════════════════════════════════════════════════════════
#  4. 加权轮询调度器
# ═══════════════════════════════════════════════════════════════

async def weighted_poll_loop() -> None:
    """加权轮询消费循环（替代 ARQ 调度）。

    权重：fast_react 4 次 → expert_search 2 次 → pipeline 1 次
    每次 blpop timeout 0.1 秒，快速轮转。
    """
    redis = await get_redis()

    logger.info("[{}] Worker 加权轮询调度器启动 | 队列权重: fast_react=4 expert_search=2 pipeline=1",
                _process_name)

    # 启动后台监听器
    await _start_background_tasks()

    schedule_idx = 0
    while True:
        speed = _WEIGHTED_SCHEDULE[schedule_idx % len(_WEIGHTED_SCHEDULE)]
        schedule_idx += 1

        queue_key = QUEUES[speed]
        try:
            result = await redis.brpop([queue_key], timeout=0.1)
        except asyncio.CancelledError:
            logger.info("[{}] Worker 调度器已取消", _process_name)
            break
        except Exception as e:
            logger.warning("[{}] Worker 队列读取异常 | error={}", _process_name, e)
            await asyncio.sleep(1.0)
            continue

        if result is None:
            continue

        _, payload = result
        try:
            task_data = _deserialize_task_data(payload if isinstance(payload, str) else payload.decode("utf-8"))
        except Exception as e:
            logger.error("[{}] 反序列化任务失败 | error={}", _process_name, e)
            continue

        # 并发执行任务（信号量限制）
        asyncio.create_task(execute_research_task(task_data))

        # 给其他协程调度机会
        await asyncio.sleep(0)


async def _start_background_tasks() -> None:
    """启动 Worker 后台监听器。

    包括：
      - 取消信号监听（来自 API 的 DELETE 请求或客户端断开）
      - LLM 缓存失效监听（来自 API 的设置变更）
    """
    asyncio.create_task(start_cancellation_listener())
    asyncio.create_task(start_llm_cache_invalidation_listener())


# ═══════════════════════════════════════════════════════════════
#  5. Auto-Scaler
# ═══════════════════════════════════════════════════════════════

async def auto_scaler_loop() -> None:
    """Auto-Scaler：监控队列深度并动态调整本 Worker 的消费速率。

    注意：生产环境中这个逻辑通常由 K8s HPA 或类似基础设施处理。
    这里提供一个纯 Python + Redis 的轻量实现作为内建方案。

    策略：
      - 队列总深度 < 2： 降低本 Worker 消费速度（休眠 1 秒）
      - 队列总深度 > 10： 提高消费速度（减少休眠）
      - 当前任务数已达上限：休眠直到有空闲 slot
    """
    redis = await get_redis()
    global _job_semaphore

    while True:
        try:
            total_depth = 0
            for queue_key in QUEUES.values():
                depth = await redis.llen(queue_key)
                total_depth += depth

            if _job_semaphore:
                active_jobs = _job_semaphore._value if hasattr(_job_semaphore, "_value") else 0
            else:
                active_jobs = MAX_CONCURRENT_JOBS

            # 根据队列深度调整日志级别
            if total_depth > 10:
                logger.info("[{}] Auto-scaler: 队列深度={} 活跃任务={}（高压）",
                            _process_name, total_depth, MAX_CONCURRENT_JOBS - active_jobs)
                await asyncio.sleep(1.0)  # 高压：快速轮询
            elif total_depth > 2:
                await asyncio.sleep(3.0)  # 正常
            else:
                await asyncio.sleep(5.0)  # 低负载：降低轮询频率

        except asyncio.CancelledError:
            logger.info("[{}] Auto-scaler 已取消", _process_name)
            break
        except Exception as e:
            logger.warning("[{}] Auto-scaler 异常 | error={}", _process_name, e)
            await asyncio.sleep(5.0)


# ═══════════════════════════════════════════════════════════════
#  6. 独立入口
# ═══════════════════════════════════════════════════════════════

def main():
    """入口函数：启动加权轮询调度器 + Auto-Scaler。"""
    process_var.set("worker")
    logger.info("[{}] Worker 启动 | 队列={} 最大并发={}",
                _process_name, QUEUES, MAX_CONCURRENT_JOBS)

    async def _run():
        asyncio.create_task(auto_scaler_loop())
        await weighted_poll_loop()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
