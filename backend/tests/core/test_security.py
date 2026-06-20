from backend.core import security

def test_password_hashing():
    """测试密码哈希与验证"""
    pwd = "strong-password-123"
    hashed = security.get_password_hash(pwd)
    
    assert hashed.startswith("pbkdf2_sha256")
    assert hashed != pwd
    assert security.verify_password(pwd, hashed) is True
    assert security.verify_password("wrong-pwd", hashed) is False

def test_api_key_encryption():
    """测试 API Key 的对称加密与解密"""
    plain = "sk-1234567890abcdef"
    cipher = security.encrypt_api_key(plain)
    
    assert cipher != plain
    assert security.decrypt_api_key(cipher) == plain

def test_ssrf_safe_urls():
    """测试 SSRF 安全 URL 校验"""
    # 应当允许的公网地址
    assert security.is_ssrf_safe("https://www.google.com") is True
    assert security.is_ssrf_safe("https://api.openai.com/v1") is True
    
    # 应当拦截的私有地址
    assert security.is_ssrf_safe("http://localhost:8000") is False
    assert security.is_ssrf_safe("http://127.0.0.1") is False
    assert security.is_ssrf_safe("http://192.168.1.1") is False
    assert security.is_ssrf_safe("http://169.254.169.254/latest/meta-data/") is False
