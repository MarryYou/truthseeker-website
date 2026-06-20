from __future__ import annotations
import asyncio
from typing import Any, cast
import dashscope
from langchain_openai import OpenAIEmbeddings
from backend.pipeline.constants import EMBEDDING_BATCH_SIZE

# ============================================================
# 核心 API: 文本向量化批量提取
# ============================================================
async def embed_documents(
    texts: list[str],
    cfg: dict | None = None,
    decrypted_api_key: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    preset_id: str | None = None,  # 💡 优化：支持直接传入 preset_id 避免内部重复查询
) -> list[list[float]]:
    """将文本列表转换为高维向量列表（支持分批处理与双路由）
    
    1. 无 key 强阻断。
    2. 对 dashscope.MultiModalEmbedding 使用 asyncio.to_thread 包装防卡死。
    3. 每次最大分批处理 10 条，以防超出大模型厂商 Token 限制。
    """
    if not texts:
        return []
        
    # 1. 强校验：必须要传入明确的 cfg
    if cfg is None:
        raise ValueError("未提供有效的 embedding 配置 (cfg=None)")
            
    provider = cfg.get("provider")
    model = cfg.get("model") or cfg.get("model_name")
    timeout = cfg.get("timeout", 30)
    
    params = cfg.get("params") or cfg.get("extra") or {}
    base_url = params.get("base_url") or cfg.get("base_url")
    
    # 2. 定位到 provider 级别后，获取解密后的用户专属 API Key
    if not decrypted_api_key:
        decrypted_api_key = cfg.get("api_key")
            
    # 3. 🚨 强校验：无 API Key 阻断
    if not decrypted_api_key:
        raise ValueError(f"用户/租户未配置对应的 API 密钥: provider={provider}")
        
    # 🚨 对于 openai 必须要配置 base_url，防止回退到隐藏的 OpenAI 默认地址
    if provider == "openai" and not base_url:
        raise ValueError(f"用户/租户未配置对应的 API 接入点 (base_url): provider={provider}")

    batch_size = EMBEDDING_BATCH_SIZE
    all_vectors: list[list[float]] = []

    # 3. 分批发送请求
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        
        # ── 路由分支 1: DashScope SDK ──────────────────────────────────
        if provider == "dashscope":
            # 通义千问多模态向量接口要求输入形式为: [{'text': ...}]
            inputs = [{"text": t} for t in batch]
            
            # 使用 asyncio.to_thread 异步执行同步的 SDK 方法，防止阻塞主线程
            resp = await asyncio.to_thread(
                dashscope.MultiModalEmbedding.call,
                model=cast(str, model),
                input=cast(Any, inputs),
                api_key=decrypted_api_key
            )
            
            if resp.status_code == 200:
                embeddings_list = resp.output.get("embeddings", [])
                # 按照 index 排序，保障向量的返回顺序与输入文本一致
                embeddings_list.sort(key=lambda x: x.get("index", 0))
                batch_vectors = [item["embedding"] for item in embeddings_list]
                all_vectors.extend(batch_vectors)
            else:
                raise RuntimeError(
                    f"DashScope MultiModalEmbedding 调用失败 | code={resp.code} message={resp.message}"
                )
                
        # ── 路由分支 2: OpenAI 兼容大模型 ─────────────────────────────
        elif provider == "openai":
            embeddings = OpenAIEmbeddings(
                model=cast(str, model),
                api_key=cast(Any, decrypted_api_key),
                base_url=base_url,
                timeout=timeout,
            )
            batch_vectors = await embeddings.aembed_documents(batch)
            all_vectors.extend(batch_vectors)
            
        else:
            raise ValueError(f"不支持的 Embedding 厂商: {provider}")
            
    return all_vectors
