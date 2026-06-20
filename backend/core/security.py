from __future__ import annotations
import hashlib
import secrets
import hmac
import socket
import ipaddress
from urllib.parse import urlparse
from fastapi import HTTPException, status
from cryptography.fernet import Fernet

# 导入我们的配置
from backend.core.config import (
    ENCRYPTION_KEY,
)

# ============================================================
# 1. PBKDF2 Password Hashing
# ============================================================
_PBKDF2_ITERATIONS = 480000
_PBKDF2_KEYLEN = 32
_SALT_LENGTH = 16


def get_password_hash(password: str) -> str:
    """PBKDF2-SHA256 密码加密存储。格式: pbkdf2_sha256$iterations$salt$hash"""
    salt = secrets.token_bytes(_SALT_LENGTH)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS, dklen=_PBKDF2_KEYLEN
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${key.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码是否与哈希密码匹配"""
    try:
        parts = hashed.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        stored_hash = parts[3]
        
        # 安全比对：重新推算哈希值并使用 hmac.compare_digest 抵御时间差攻击
        key = hashlib.pbkdf2_hmac(
            "sha256", plain.encode("utf-8"), salt, iterations, dklen=_PBKDF2_KEYLEN
        )
        return hmac.compare_digest(key.hex(), stored_hash)
    except Exception:
        return False


# ============================================================
# 2. Symmetric Encryption (API Key storage)
# ============================================================
def encrypt_api_key(plain: str) -> str:
    """加密明文 API Key 密文存储"""
    # Fernet 对称加密器需要 bytes 格式的 key
    f = Fernet(ENCRYPTION_KEY.encode("utf-8"))
    return f.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_api_key(cipher: str) -> str:
    """解密密文 API Key"""
    f = Fernet(ENCRYPTION_KEY.encode("utf-8"))
    return f.decrypt(cipher.encode("utf-8")).decode("utf-8")


# ============================================================
# 4. SSRF 请求防护
# ============================================================
def is_ssrf_safe(url: str) -> bool:
    """判断目标 URL 是否为合法的公网地址，阻断本地及私有局域网请求"""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
            
        # 通过 DNS 解析出对应的所有 IP 地址（防范 DNS Rebinding 攻击）
        addr_info = socket.getaddrinfo(host, None)
        for info in addr_info:
            ip_str = info[4][0]
            ip = ipaddress.ip_address(ip_str)
            
            # 判断解析出的 IP 是否是回环、私有或保留 IP
            if ip.is_loopback or ip.is_private or ip.is_reserved:
                # 特殊放行：198.18.0.0/15 是 RFC 2544 预留的基准测试网段，
                # 但在很多使用 Clash 等代理的环境中会被用作外部域名的映射地址，故此处予以放行。
                if isinstance(ip, ipaddress.IPv4Address):
                    if ipaddress.IPv4Network("198.18.0.0/15").supernet_of(ipaddress.IPv4Network(f"{ip_str}/32")):
                        continue
                return False
        return True
    except Exception:
        # 无法解析等异常情况一律视为不安全
        return False


def validate_url_for_ssrf(url: str) -> None:
    """SSRF 拦截方法，如果不安全直接抛出 HTTPException 拒绝执行"""
    if not is_ssrf_safe(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="检测到潜在的 SSRF (服务端请求伪造) 攻击，拒绝请求"
        )
