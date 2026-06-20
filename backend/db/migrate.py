"""数据库表结构初始化与自愈迁移模块"""
from __future__ import annotations
from typing import Any
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from backend.db.models import Base, ResearchPreset, ResearchSession
from backend.core.logging import logger
from backend.db.seed import _build_business_config, _build_stages_config
from backend.pipeline.constants import SPEED_PROFILES, DEFAULT_PRESETS


async def init_db(engine: AsyncEngine) -> None:
    """自动创建所有未初始化的核心业务表"""
    logger.info("正在检查并初始化数据库表结构...")
    try:
        async with engine.begin() as conn:
            # create_all 会自动检测表是否存在，只创建不存在的表，对已有表无损
            await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库表结构初始化/检查完成。")
    except Exception as e:
        logger.error("初始化数据库表结构失败: {}", e)
        raise e


async def migrate_db(engine: AsyncEngine) -> None:
    """执行数据迁移：清理旧数据、补全新字段结构"""
    logger.info("开始执行数据迁移...")
    try:
        async with engine.begin() as conn:
            # Step 1: DDL 迁移 — 删除旧的 researches 表
            await _migrate_drop_old_research_table(conn)
            # Step 2: DDL 迁移 — 添加 users 档案列
            await _migrate_add_user_profile_columns(conn)
            # Step 2.5: DDL 迁移 — 添加 sessions 耗时统计列
            await _migrate_add_session_duration_column(conn)
            # Step 2.6: DDL 迁移 — 添加 tasks v3.0 协作列 (pending_approval, breakpoint_type)
            await _migrate_add_v3_task_columns(conn)
            # Step 2.7: DDL 迁移 — 添加 research_tasks updated_at 列 (僵尸任务看门狗)
            await _migrate_add_task_updated_at_column(conn)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await _migrate_update_speed_profiles(session)
            await _migrate_cleanup_jina_from_presets(session)
            await _migrate_fix_session_statuses(session)
            await session.commit()
        logger.info("数据迁移完成。")
    except Exception as e:
        logger.error("数据迁移失败: {}", e)
        # 迁移失败不阻断启动，仅记录错误
        logger.warning("数据迁移未成功，但不影响服务启动。可通过手动修复解决。")


async def _migrate_add_v3_task_columns(conn: Any) -> None:
    """DDL: 为 research_tasks 表添加 pending_approval 和 breakpoint_type 列 (v3.0)"""
    try:
        if conn.dialect.name == "sqlite":
            res = await conn.execute(text("PRAGMA table_info(research_tasks)"))
            columns = [row[1] for row in res.fetchall()]
        else:
            res = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='research_tasks'"
            ))
            columns = [row[0] for row in res.fetchall()]

        # 1. 检查 pending_approval
        if "pending_approval" not in columns:
            await conn.execute(text("ALTER TABLE research_tasks ADD COLUMN pending_approval BOOLEAN DEFAULT FALSE"))
            logger.info("迁移: 已添加 research_tasks.pending_approval 列")

        # 2. 检查 breakpoint_type
        if "breakpoint_type" not in columns:
            await conn.execute(text("ALTER TABLE research_tasks ADD COLUMN breakpoint_type VARCHAR(20)"))
            logger.info("迁移: 已添加 research_tasks.breakpoint_type 列")
            
    except Exception as e:
        logger.warning("迁移: 补全 research_tasks v3.0 协作列时出错: {}", e)


async def _migrate_add_session_duration_column(conn: Any) -> None:
    """DDL: 为 research_sessions 表添加 total_duration_seconds 列"""
    try:
        if conn.dialect.name == "sqlite":
            res = await conn.execute(text("PRAGMA table_info(research_sessions)"))
            columns = [row[1] for row in res.fetchall()]
        else:
            res = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='research_sessions'"
            ))
            columns = [row[0] for row in res.fetchall()]

        if "total_duration_seconds" not in columns:
            await conn.execute(text("ALTER TABLE research_sessions ADD COLUMN total_duration_seconds INTEGER DEFAULT 0"))
            logger.info("迁移: 已添加 research_sessions.total_duration_seconds 列")
    except Exception as e:
        logger.warning("迁移: 补全 session 耗时列时出错: {}", e)


async def _migrate_drop_old_research_table(conn: Any) -> None:
    """DDL: 删除旧的 researches 表（如果存在）"""
    try:
        # 获取现有表列表
        if conn.dialect.name == "sqlite":
            res = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='researches'"))
            exists = res.scalar() is not None
        else:
            res = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_name='researches'"
            ))
            exists = res.scalar() is not None

        if exists:
            await conn.execute(text("DROP TABLE researches"))
            logger.info("迁移: 已删除旧的 researches 表，准备启用新双表架构")
    except Exception as e:
        logger.warning("迁移: 删除旧表时出错 (可能已有其他进程处理): {}", e)


async def _migrate_add_user_profile_columns(conn: Any) -> None:
    """DDL: 为 users 表添加 full_name, avatar_url, role 列（如果不存在）"""
    try:
        # 获取现有列列表 (兼容 SQLite 和 PostgreSQL)
        if conn.dialect.name == "sqlite":
            res = await conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in res.fetchall()]
        else:
            res = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='users'"
            ))
            columns = [row[0] for row in res.fetchall()]

        # 1. 检查 full_name
        if "full_name" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR(255)"))
            logger.info("迁移: 已添加 users.full_name 列")

        # 2. 检查 avatar_url
        if "avatar_url" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url TEXT"))
            logger.info("迁移: 已添加 users.avatar_url 列")
            
        # 3. 检查 role
        if "role" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'"))
            logger.info("迁移: 已添加 users.role 列")
            
    except Exception as e:
        logger.warning("迁移: 补全用户信息列时出现非预期错误: {}", e)


async def _migrate_add_task_updated_at_column(conn: Any) -> None:
    """DDL: 为 research_tasks 表添加 updated_at 列（僵尸任务看门狗依赖）"""
    try:
        if conn.dialect.name == "sqlite":
            res = await conn.execute(text("PRAGMA table_info(research_tasks)"))
            columns = [row[1] for row in res.fetchall()]
        else:
            res = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='research_tasks'"
            ))
            columns = [row[0] for row in res.fetchall()]

        if "updated_at" not in columns:
            await conn.execute(text(
                "ALTER TABLE research_tasks ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP"
            ))
            # 首次迁移时用 created_at 回填历史数据的 updated_at
            await conn.execute(text("UPDATE research_tasks SET updated_at = created_at WHERE updated_at IS NULL"))
            logger.info("迁移: 已添加 research_tasks.updated_at 列，并用 created_at 回填历史数据")
    except Exception as e:
        logger.warning("迁移: 添加 research_tasks.updated_at 列时出错: {}", e)


async def _migrate_update_speed_profiles(session: AsyncSession) -> None:
    """根据最新的 SPEED_PROFILES 强制更新数据库中的系统预设"""
    stmt = select(ResearchPreset).where(ResearchPreset.is_system_default)
    result = await session.execute(stmt)
    presets = result.scalars().all()

    updated_count = 0
    for preset in presets:
        name = preset.name
        if name in SPEED_PROFILES:
            sp = SPEED_PROFILES[name]
            template = DEFAULT_PRESETS.get(name, {"engines": ["bocha"]})
            
            # 重新生成配置
            new_nodes_config = {
                "business": _build_business_config(name, template, sp),
                "stages": _build_stages_config(name),
            }
            
            # 对比关键参数看是否需要更新，并清洗废弃字段
            nodes_config_val = preset.nodes_config or {}
            old_bus = nodes_config_val.get("business", {})
            has_obsolete = "max_search_rounds" in old_bus or "verification_level" in old_bus
            
            needs_update = (
                has_obsolete or
                old_bus.get("speed") != name or
                old_bus.get("engines") != template.get("engines", ["bocha"])
            )
            
            if needs_update:
                preset.nodes_config = new_nodes_config
                flag_modified(preset, "nodes_config")
                updated_count += 1
                logger.info("迁移: 已更新系统预设 '{}' (id={}) 的搜索量配置并清洗旧参数", name, preset.id)

    if updated_count > 0:
        logger.info("迁移: 共同步并清洗了 {} 个系统预设的最新速度档位", updated_count)
    else:
        logger.info("迁移: 系统预设的配置已是最新且无历史残留参数")


async def _migrate_cleanup_jina_from_presets(session: AsyncSession) -> None:
    """迁移：从所有预设中清除 jina_reader 相关配置"""
    stmt = select(ResearchPreset)
    result = await session.execute(stmt)
    presets = result.scalars().all()

    updated_count = 0
    for preset in presets:
        nodes_config = preset.nodes_config
        if not nodes_config:
            continue
        business = nodes_config.get("business", {})
        changed = False

        # 移除 jina_reader 配置块
        if "jina_reader" in business:
            del business["jina_reader"]
            changed = True

        # 移除 engines 列表中的 jina
        engines = business.get("engines")
        if isinstance(engines, list) and "jina" in engines:
            business["engines"] = [e for e in engines if e != "jina"]
            changed = True

        if changed:
            flag_modified(preset, "nodes_config")
            updated_count += 1
            logger.info("迁移: 已从预设 '{}' (id={}) 清理 jina_reader 配置", preset.name, preset.id)

    if updated_count > 0:
        logger.info("迁移: 共清理 {} 个预设中的 jina_reader 残留配置", updated_count)
    else:
        logger.info("迁移: 所有预设已无 jina_reader 残留")


async def _migrate_fix_session_statuses(session: AsyncSession) -> None:
    """将现有的 'active' 状态修复为 'completed'，以匹配前端最新的状态显示逻辑"""
    # 批量更新：所有 status='active' 的都改为 'completed'
    # 因为在我们的新逻辑中，Session 开始是 'running'，结束是 'completed' 或 'failed'
    stmt = update(ResearchSession).where(ResearchSession.status == "active").values(status="completed")
    result = await session.execute(stmt)
    if result.rowcount > 0: # type: ignore
        logger.info("迁移: 已将 {} 条 Session 的 'active' 状态修复为 'completed'", result.rowcount) # type: ignore

