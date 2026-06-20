"""全局配置。

配置分为三层，优先级从高到低：
  1️⃣ 环境变量 (用户必填 / 可选) — 部署时通过 .env 或容器环境注入
  2️⃣ 系统静态常量 — 代码级硬编码，一般无需修改
  3️⃣ 数据库动态配置 — 用户在运行时通过 API / UI 修改，覆盖 1️⃣ 和 2️⃣ 的默认值

注意：本模块只管理第 1️⃣ 和第 2️⃣ 层。第 3️⃣ 层见 CRUD / ModelConfig。
"""
from __future__ import annotations

import base64
import hashlib
import os

from dotenv import load_dotenv

load_dotenv()


# ╔════════════════════════════════════════════════════════════════════════╗
# ║  1️⃣  环境变量 — 用户必填 (缺失会直接 RuntimeError 阻止启动)         ║
# ╚════════════════════════════════════════════════════════════════════════╝

# ── 1.1 JWT 签名密钥 ──────────────────────────────────────────────────────
# 用途：签发 / 验证用户登录 Token，同时作为 AES 加密密钥的派生源。
# 生成：python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY 环境变量未设置，请在 .env 中配置它！"
    )


# ╔════════════════════════════════════════════════════════════════════════╗
# ║  2️⃣  环境变量 — 可选 (有合理默认值，不设置也能跑)                    ║
# ╚════════════════════════════════════════════════════════════════════════╝

# ── 2.1 AES 加密密钥 (用于加密用户存库的 API Key) ─────────────────────────
# 如果不设置，会自动从 JWT_SECRET_KEY 派生（SHA256 → urlsafe_b64encode）。
# 独立设置可实现"轮换 JWT 不影响已加密数据"的安全策略。
ENCRYPTION_KEY: str
_raw_enc_key = os.getenv("ENCRYPTION_KEY", "")
if _raw_enc_key:
    ENCRYPTION_KEY = _raw_enc_key
else:
    derived_bytes = hashlib.sha256(JWT_SECRET_KEY.encode("utf-8")).digest()
    ENCRYPTION_KEY = base64.urlsafe_b64encode(derived_bytes).decode("utf-8")

# ── 2.2 数据库连接 ────────────────────────────────────────────────────────
# 本地开发默认 SQLite；生产环境使用 Postgres。
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./truthseeker.db",
)

# ── 2.3 LangGraph Store 命名空间前缀 ──────────────────────────────────────
STORE_NS_PREFIX: str = os.getenv("STORE_NS_PREFIX", "truthseeker")

# ── 2.4 Redis 连接 ────────────────────────────────────────────────────────
# 用于分布式限流与缓存。
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── 2.5 Logto 配置 (Resource Server & Client) ──────────────────────────────
# 用于校验 Logto 发出的 Access Token (RS256) 以及进行 OIDC 登录
LOGTO_ENDPOINT: str = os.getenv("LOGTO_ENDPOINT", "")
if not LOGTO_ENDPOINT:
    raise RuntimeError(
        "LOGTO_ENDPOINT 环境变量未设置，请在 .env 中配置 Logto 域名！"
    )
LOGTO_CLIENT_ID: str = os.getenv("LOGTO_CLIENT_ID") or os.getenv("LOGTO_APP_ID", "")
LOGTO_CLIENT_SECRET: str = os.getenv("LOGTO_CLIENT_SECRET") or os.getenv("LOGTO_APP_SECRET", "")
LOGTO_API_RESOURCE: str = os.getenv("LOGTO_API_RESOURCE", "https://api.your-domain.com")
LOGTO_JWKS_URL: str = f"{LOGTO_ENDPOINT.rstrip('/')}/oidc/jwks"
LOGTO_ISSUER: str = f"{LOGTO_ENDPOINT.rstrip('/')}/oidc"

# ── 2.6 服务端配置 ──────────────────────────────────────────────────────
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000/")
CORS_ORIGINS: list[str] = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if origin.strip()]


# ╔════════════════════════════════════════════════════════════════════════╗
# ║  3️⃣  系统静态常量 — 代码级默认值，修改需重启服务                      ║
# ╚════════════════════════════════════════════════════════════════════════╝

# ── 3.1 Session & Security 参数 ─────────────────────────────────────────────
JWT_EXPIRATION_HOURS: int = 24

# ── 3.2 管线常量（从 pipeline/constants.py 重导出，保持向后兼容）──────────

