import os
import pytest
from unittest.mock import patch

def test_config_constants():
    """测试核心配置与常量是否被正确定义，以及主加密密钥是否安全派生"""
    # 提示：在导入 config 前，先 mock 写入 JWT_SECRET_KEY 以防初始化报错
    with patch.dict(os.environ, {"JWT_SECRET_KEY": "test-jwt-secret-key-123"}):
        from backend.core import config
        from backend.pipeline import constants
        
        # 1. 验证关键参数的默认类型与值
        assert isinstance(constants.DEFAULT_STAGE_MODELS, dict)
        assert "understanding" in constants.DEFAULT_STAGE_MODELS
        # 节点默认参数已统一到 NODE_DEFAULTS
        assert constants.NODE_DEFAULTS["filter_results"]["min_relevance_score"] == 0.35
        assert constants.NODE_DEFAULTS["multi_search"]["max_concurrent_engines"] == 3
        
        # 2. 验证派生的 ENCRYPTION_KEY
        assert len(config.ENCRYPTION_KEY) > 0


def test_config_missing_jwt_secret():
    """测试在缺失关键环境变量 JWT_SECRET_KEY 时，系统是否会如期抛出 RuntimeError 拦截"""
    import sys
    import importlib
    from unittest.mock import patch
    
    # 1. 备份环境
    old_env = os.environ.copy()
    
    try:
        # 2. 清空关键环境变量
        if "JWT_SECRET_KEY" in os.environ:
            del os.environ["JWT_SECRET_KEY"]
            
        # 3. 强制重新加载模块，并 Mock load_dotenv 防止它从磁盘加载 .env
        if "backend.core.config" in sys.modules:
            del sys.modules["backend.core.config"]
            
        with patch("dotenv.load_dotenv"):
            with pytest.raises(RuntimeError) as exc_info:
                importlib.import_module("backend.core.config")
        
        assert "JWT_SECRET_KEY" in str(exc_info.value)
        
    finally:
        # 4. 恢复环境
        os.environ.clear()
        os.environ.update(old_env)
