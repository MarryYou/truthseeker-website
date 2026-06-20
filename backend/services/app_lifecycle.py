"""系统生命周期管理 — 负责应用启动初始化与关闭资源清理。

在 Worker 架构下，API 进程职责减少：
  - 不再预编译 LangGraph 图（Worker 进程按需编译）
  - 不再管理 LangGraph Checkpointer/Store（Worker 进程管理）
  - 保留数据库、Redis、插件注册
  - 新增 LLM 缓存失效监听器
"""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI

from backend.db.engine import async_engine
from backend.db.models import Base
from backend.core.config import DATABASE_URL
from backend.core.logging import logger, source_var
from psycopg_pool import AsyncConnectionPool
from backend.core.llm import start_llm_cache_invalidation_listener
from backend.utils.redis import RedisClient


async def _periodic_checkpoints_cleanup(pool: Any):
    """后台异步任务：每 24 小时定期清理 checkpoints、checkpoint_blobs 和 checkpoint_writes 中 30 天以前的旧记录。"""
    # 刚启动时延迟 10 秒再清理，防止阻塞正常开机
    await asyncio.sleep(10.0)

    while True:
        logger.info("开始执行定期 Checkpoints 清理任务...")
        try:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    writes_deleted = 0
                    try:
                        await cur.execute(
                            "DELETE FROM checkpoint_writes "
                            "WHERE thread_id IN ("
                            "  SELECT id FROM research_tasks "
                            "  WHERE created_at < NOW() - INTERVAL '30 days'"
                            ");"
                        )
                        writes_deleted = cur.rowcount
                    except Exception:
                        pass

                    blobs_deleted = 0
                    try:
                        await cur.execute(
                            "DELETE FROM checkpoint_blobs "
                            "WHERE thread_id IN ("
                            "  SELECT id FROM research_tasks "
                            "  WHERE created_at < NOW() - INTERVAL '30 days'"
                            ");"
                        )
                        blobs_deleted = cur.rowcount
                    except Exception:
                        pass

                    checkpoints_deleted = 0
                    try:
                        await cur.execute(
                            "DELETE FROM checkpoints "
                            "WHERE thread_id IN ("
                            "  SELECT id FROM research_tasks "
                            "  WHERE created_at < NOW() - INTERVAL '30 days'"
                            ");"
                        )
                        checkpoints_deleted = cur.rowcount
                    except Exception:
                        pass

                    logger.info(
                        "定期 Checkpoints 清理完成 | 删除了 {} 条 writes, {} 条 blobs, {} 条 checkpoints",
                        writes_deleted, blobs_deleted, checkpoints_deleted
                    )
        except asyncio.CancelledError:
            logger.info("定期 Checkpoints 清理任务已被优雅取消。")
            raise
        except Exception as e:
            logger.error("定期 Checkpoints 清理任务发生异常 | error={}", e)

        await asyncio.sleep(86400.0)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """API 进程生命周期管理。"""
    # ── 设置进程日志标记 ──────────────────────────────────────
    source_var.set("api")

    # 1. 数据库初始化（自动建表，已有表跳过）
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. 插件注册（搜索与提取引擎）
    logger.info("系统插件装载完成: bocha, tavily, zhihu")

    # 3. 根据数据库类型决定是否启动后台清理任务
    use_pg = DATABASE_URL.startswith("postgresql")
    if use_pg:

        def _make_psycopg_dsn(url: str) -> str:
            return (
                url
                .replace("postgresql+asyncpg://", "postgresql://")
                .replace("postgresql+psycopg2://", "postgresql://")
                .replace("postgresql+psycopg://", "postgresql://")
            )

        psycopg_dsn = _make_psycopg_dsn(DATABASE_URL)
        cp_pool = AsyncConnectionPool(
            psycopg_dsn, min_size=1, max_size=2,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await cp_pool.open()
        _app.state.cleanup_task = asyncio.create_task(_periodic_checkpoints_cleanup(cp_pool))
    else:
        cp_pool = None

    # 4. 启动 LLM 缓存失效监听器（API 进程也需要清理本地缓存）
    if use_pg:
        _app.state.llm_cache_listener = asyncio.create_task(
            start_llm_cache_invalidation_listener()
        )

    # 5. 启动 Redis 广播任务取消订阅监听器
    # 注意：API 进程不再执行研究任务，但保留取消广播监听以支持 DELETE 请求转发
    _app.state.cancellation_listener_task = None

    yield

    # 5. 优雅停机
    logger.info("API 进程开始优雅停机...")

    # 取消定期清理协程
    cleanup_task = getattr(_app.state, "cleanup_task", None)
    if cleanup_task:
        logger.info("正在注销定期 Checkpoints 清理任务...")
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

    # 取消 LLM 缓存监听器
    llm_listener = getattr(_app.state, "llm_cache_listener", None)
    if llm_listener:
        llm_listener.cancel()
        try:
            await llm_listener
        except asyncio.CancelledError:
            pass

    # 关闭 Redis 连接
    await RedisClient.close()

    # 关闭数据库引擎
    await async_engine.dispose()

    if cp_pool:
        await cp_pool.close()

    logger.info("API 进程已安全关闭。")
