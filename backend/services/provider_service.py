"""Model provider management and connectivity verification services."""
from __future__ import annotations
import httpx
from backend.core.llm import test_llm_connection
from backend.core.registry import PROVIDER_FALLBACK_MODELS
from backend.search.registry import plugin_registry


def format_connection_error(e: Exception, provider_name: str) -> str:
    """格式化供应商连接报错信息，输出更加人性化的友好提示"""
    err_str = str(e)
    
    # 针对 httpx 状态码异常，尝试从 response body 中解析出服务商的具体错误描述
    if isinstance(e, httpx.HTTPStatusError):
        try:
            body = e.response.json()
            if isinstance(body, dict):
                detail = body.get("detail") or body.get("error", {}).get("message") or body.get("msg")
                if detail:
                    err_str = f"{err_str} (服务商返回: {detail})"
        except Exception:
            try:
                text = e.response.text
                if text and len(text) < 200: # 避免把整个大段 HTML 网页塞进去
                    err_str = f"{err_str} (服务商返回: {text})"
            except Exception:
                pass

    # 针对 401 / 403 (未授权或权限拒绝)
    if "401" in err_str or "403" in err_str or "unauthorized" in err_str.lower() or "forbidden" in err_str.lower():
        return f"连接失败：API 密钥或权限校验未通过。请确保您为供应商【{provider_name.upper()}】配置的 Key 准确无误且未被服务商禁用。"
    
    # 针对 429 Too Many Requests 或 余额不足
    if "429" in err_str or "too many requests" in err_str.lower() or "insufficient_quota" in err_str.lower() or "quota" in err_str.lower() or "limit" in err_str.lower():
        return f"连接失败：API 调用频次超限或账户欠费余额不足 (429/Insufficient Quota)。请检查您的【{provider_name.upper()}】账户状态。"

    # 针对 400 模型不支持或坏请求
    if "400" in err_str or "invalid" in err_str.lower() or "model" in err_str.lower() or "invalid_request_error" in err_str.lower():
        return f"连接失败：API 服务商拒绝了请求 (400 Bad Request)。这通常是由于配置的模型不存在、该密钥无权限访问，或请求格式有误。原因为: {err_str}"
        
    # 针对网络超时 / 连通性
    if "timeout" in err_str.lower() or "connect" in err_str.lower() or "dns" in err_str.lower() or "httpx" in err_str.lower():
        return f"网络连通失败：连接供应商【{provider_name.upper()}】服务超时或无法建立链接。请检查网络稳定性、代理或 Base URL 设置。原因为: {err_str}"
        
    return f"连接测试未通过: {err_str}"


async def test_provider_connection(
    category: str, 
    provider_name: str, 
    plain_key: str, 
    base_url: str | None = None,
    model_name: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 10,
    timeout: int = 10
) -> bool:
    """测试指定供应商凭证的连接性"""
    if category == "llm":
        # 智能 fallback 模型名，避免某些网关限制 "ping" 模型导致失败
        model = model_name
        if not model or model == "ping":
            model = PROVIDER_FALLBACK_MODELS.get(provider_name, "gpt-4o-mini")
                
        cfg = {
            "provider": provider_name,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
            "params": {"base_url": base_url}
        }
        return await test_llm_connection(cfg, plain_key)
    elif category == "search":
        plugin = plugin_registry.get_plugin(provider_name)
        if plugin:
            return await plugin.test_connection(plain_key)
        return True
    return True


async def fetch_provider_models(provider_name: str, key: str, base_url: str) -> list[str]:
    """从供应商 API 实时拉取模型列表"""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {key}"}
        )
        resp.raise_for_status()
        resp_data = resp.json()
        # 兼容 OpenAI 格式
        return [m["id"] for m in resp_data.get("data", [])]
