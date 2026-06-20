"""Session Management using Redis."""
from __future__ import annotations
import json
import secrets
from typing import Any, Optional
from logto import Storage
from backend.utils.redis import get_redis, get_sync_redis
from backend.core.config import JWT_EXPIRATION_HOURS

SESSION_PREFIX = "ts:session:"
SESSION_EXPIRE_SECONDS = JWT_EXPIRATION_HOURS * 3600
LOGTO_STORAGE_PREFIX = "ts:logto:"
LOGTO_STORAGE_TTL = 600

class LogtoRedisStorage(Storage):
    """适配 Logto SDK 的 Redis 存储类（同步实现）"""
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.prefix = f"{LOGTO_STORAGE_PREFIX}{session_id}:"

    def get(self, key: str) -> Optional[str]:
        redis = get_sync_redis()
        val = redis.get(f"{self.prefix}{key}")
        if val is None:
            return None
        if isinstance(val, bytes):
            return val.decode("utf-8")
        return val

    def set(self, key: str, value: Optional[str]) -> None:
        redis = get_sync_redis()
        if value is None:
            self.delete(key)
            return
        # Logto 状态通常只在登录流程中有效，设置 10 分钟过期
        redis.setex(f"{self.prefix}{key}", LOGTO_STORAGE_TTL, value)

    def delete(self, key: str) -> None:
        redis = get_sync_redis()
        redis.delete(f"{self.prefix}{key}")


class SessionManager:
    SESSION_EXPIRE_SECONDS = SESSION_EXPIRE_SECONDS

    @staticmethod
    def generate_session_id() -> str:
        """生成 32 位随机 Session ID"""
        return secrets.token_urlsafe(32)

    @classmethod
    async def create_session(
        cls, user_id: str, role: str, tenant_id: Optional[str] = None, session_id: Optional[str] = None
    ) -> str:
        """创建 Session 并存入 Redis"""
        if not session_id:
            session_id = cls.generate_session_id()
        redis = await get_redis()
        
        session_data = {
            "user_id": user_id,
            "role": role,
            "tenant_id": tenant_id
        }
        
        await redis.setex(
            f"{SESSION_PREFIX}{session_id}",
            cls.SESSION_EXPIRE_SECONDS,
            json.dumps(session_data)
        )
        return session_id

    @classmethod
    async def get_session(cls, session_id: str) -> Optional[dict[str, Any]]:
        """获取 Session 数据"""
        if not session_id:
            return None
            
        redis = await get_redis()
        data = await redis.get(f"{SESSION_PREFIX}{session_id}")
        if not data:
            return None
            
        try:
            return json.loads(data)
        except Exception:
            return None

    @classmethod
    async def delete_session(cls, session_id: str) -> None:
        """注销并删除 Session"""
        if not session_id:
            return
        redis = await get_redis()
        await redis.delete(f"{SESSION_PREFIX}{session_id}")
