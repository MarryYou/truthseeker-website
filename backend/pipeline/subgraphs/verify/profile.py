"""profile 节点 — 信源画像：URL 启发式 + 动态分批 LLM 内容质量评估。

设计：
  阶段 1（启发式，0ms）：
    对每个 URL 根据域名类型、时效性、广告特征计算 domain_score。
    domain_score ≥ 0.75（gov/edu/主流媒体）→ 不需要 LLM 二次判断，直接使用启发式分数。

  阶段 2（动态分批 LLM，只处理"灰色地带"信源）：
    domain_score < 0.75 的商业/未知域名 → 送入 LLM 批量内容质量评估。
    动态分批：按 token 预算（而非固定条数）切批，每批 ≤ BATCH_TOKEN_BUDGET token。
    各批并发调用（受 semaphore 限速）。

  最终 credibility_score = domain_score × 0.6 + content_quality × 0.4
    （对 LLM 未评估的高置信信源，content_quality 默认等于 domain_score）

  缓存：
    已评估的信源画像按 URL 哈希缓存 1h，避免同一来源重复 LLM 评估。
"""
from __future__ import annotations
import hashlib
from cachetools import TTLCache
import asyncio
import json
import time
from typing import Any, AsyncIterator, cast
from urllib.parse import urlparse
from langchain_core.runnables import RunnableConfig

from backend.pipeline.subgraphs.verify.state import VerifyState
from backend.pipeline.types import ErrorEntry
from backend.pipeline.constants import (
    DOMAIN_TRUST_THRESHOLD,
    BATCH_TOKEN_BUDGET,
    PROFILE_MAX_CONCURRENCY,
)
from backend.pipeline.prompts import PROFILE_BATCH_PROMPT
from backend.core.llm import get_llm_for_stage
from backend.utils.llm_utils import parse_llm_json, extract_llm_content, get_node_config
from backend.core.logging import logger

# 信源画像缓存：按 URL 哈希缓存 1h，避免同一来源在不同任务中重复 LLM 评估
_profile_cache: TTLCache = TTLCache(maxsize=500, ttl=3600)


# ── 域名可信度启发式映射表 ──────────────────────────────────────────

_DOMAIN_SCORES: dict[str, float] = {
    # 极高置信 (0.9 - 1.0)
    "gov.cn": 1.0, "gov": 0.95, "mil": 0.95, "edu.cn": 0.9, "edu": 0.9, "org.cn": 0.85,
    "people.com.cn": 0.95, "xinhuanet.com": 0.95, "news.cn": 0.95, "cctv.com": 0.9,
    "nytimes.com": 0.9, "reuters.com": 0.9, "wsj.com": 0.9, "bbc.co.uk": 0.9, "nature.com": 1.0,
    # 中高置信 (0.7 - 0.85)
    "zhihu.com": 0.75, "wikipedia.org": 0.8, "github.com": 0.8, "stackoverflow.com": 0.8,
    "sina.com.cn": 0.75, "qq.com": 0.7, "163.com": 0.7, "sohu.com": 0.7,
}

_SOURCE_TYPE_MAP: dict[str, list[str]] = {
    "community": ["zhihu.com", "reddit.com", "quora.com"],
    "official":  ["gov.cn", "people.com.cn", "xinhuanet.com", "cctv.com"],
    "media":     ["sina.com.cn", "qq.com", "163.com", "sohu.com", "ifeng.com", "nytimes.com"],
}


def _get_domain_score(url: str) -> tuple[float, str]:
    """启发式计算域名基础分与类型。"""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        
        score = 0.5  # 默认基准分
        stype = "web"

        # 匹配映射表
        for d, s in _DOMAIN_SCORES.items():
            if netloc == d or netloc.endswith(f".{d}"):
                score = max(score, s)
        
        for t, domains in _SOURCE_TYPE_MAP.items():
            if any(netloc == d or netloc.endswith(f".{d}") for d in domains):
                stype = t
                break
                
        return score, stype
    except Exception:
        return 0.5, "web"


# ── 动态分批工具 ────────────────────────────────────────────────────

def _estimate_tokens(item: dict) -> int:
    """粗估单条 item 的 token 量（中英文混合约 3 字符/token）"""
    text = item.get("url", "") + item.get("summary", item.get("snippet", ""))
    return max(30, len(text) // 3)


def _split_batches(items: list[dict]) -> list[list[dict]]:
    """按 BATCH_TOKEN_BUDGET 动态切批，而非固定条数。"""
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_tokens = 0
    
    for it in items:
        toks = _estimate_tokens(it)
        if current_tokens + toks > BATCH_TOKEN_BUDGET and current:
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(it)
        current_tokens += toks
    if current:
        batches.append(current)
    return batches


async def _process_batch(llm: Any, batch: list[dict]) -> dict[int, dict]:
    """单批次 LLM 评估"""
    # 构造 batch prompt 输入
    inputs = []
    for i, it in enumerate(batch):
        # 使用手术级采样截取的内容
        content = it.get("full_text") or it.get("content") or it.get("summary") or it.get("snippet", "")
        inputs.append({
            "index": i,
            "url": it["url"],
            "summary": content[:1200] # 增加画像深度
        })
    
    prompt = PROFILE_BATCH_PROMPT.format(sources_json=json.dumps(inputs, ensure_ascii=False))
    try:
        resp = await asyncio.wait_for(llm.ainvoke(prompt), timeout=60)
        raw = extract_llm_content(resp)
        # LLM might return a list of objects or a dict containing a list
        parsed_data = parse_llm_json(raw)
        results = cast(list[dict], parsed_data)
        if not isinstance(results, list):
            raise ValueError("LLM 返回格式不是列表")
        return {r["index"]: r for r in results if "index" in r}
    except asyncio.TimeoutError:
        logger.warning("profile LLM 批次评估超时（60s），降级至域名启发式评分")
        return {}


# ── 主节点 ───────────────────────────────────────────────────────────

async def profile_node(state: VerifyState, config: RunnableConfig) -> AsyncIterator[dict[str, Any]]:
    """信源画像节点：启发式快速过滤 + 动态分批 LLM 内容质量补充评估 (支持思考链汇报)"""
    start_ts = time.time()
    logger.info("profile 启动 | 开始信源画像分析")
    
    step_id = "verify_profile"
    yield {"thought_steps": [{
        "id": step_id, 
        "label": "信源可信度评估", 
        "status": "running"
    }]}

    try:
        filtered_items: list[dict] = state.get("_filtered_items", [])
        user_id = state.get("user_id", "default")
        preset_id = state.get("preset_id")

        # 读取 cross_verify 节点参数
        node_config = await get_node_config(config, "cross_verify")
        verification_level = state.get("verification_level") or node_config.get("verification_level", "standard")

        if not filtered_items:
            yield {"source_profiles": {}}
            return

        # 1. 执行阶段 1：启发式评分
        profiles: dict[str, dict] = {}
        need_llm: list[dict] = []
        skip_llm: list[dict] = []

        for item in filtered_items:
            url = item["url"]
            d_score, s_type = _get_domain_score(url)
            item["_domain_score"] = d_score
            item["_source_type"] = s_type
            
            if d_score >= DOMAIN_TRUST_THRESHOLD or verification_level == "skip":
                skip_llm.append(item)
            else:
                need_llm.append(item)

        # 2. 如果不需要 LLM 评估（skip 级别或全是权威网），直接产出结果
        llm_count = 0
        if not need_llm or verification_level == "skip":
            for item in filtered_items:
                d_score = item["_domain_score"]
                profiles[item["url"]] = {
                    "credibility": d_score,
                    "domain_score": d_score,
                    "content_quality": d_score,
                    "source_type": item["_source_type"],
                    "has_marketing_tone": False,  # 快速路径始终不检测营销
                    "has_expert_evidence": d_score >= DOMAIN_TRUST_THRESHOLD,
                    "llm_assessed": False,
                }

            yield {"thought_steps": [{
                "id": step_id, 
                "status": "completed",
                "new_sub_step": {
                    "message": f"快速画像完成，已为 {len(profiles)} 个域名建立启发式可信度档案。", 
                    "type": "success"
                }
            }]}
            duration = round(time.time() - start_ts, 2)
            logger.info("profile 完成 | 总计画像数={} | LLM评估数=0 | 耗时={}s", len(filtered_items), duration)
            yield {"source_profiles": profiles}
            return

        # strict 模式：完整 LLM 批量评估
        # 先检查缓存，已评估的信源跳过 LLM
        cached_llm = []
        still_need_llm = []
        for item in need_llm:
            url_hash = hashlib.sha256(item["url"].encode()).hexdigest()
            cached = _profile_cache.get(url_hash)
            if cached is not None:
                cached_llm.append(cached)
                # 不用走 LLM，直接用缓存值
                profiles[item["url"]] = {**cached, "llm_assessed": True}
                llm_count += 1
            else:
                still_need_llm.append(item)

        # 过滤掉已缓存的，只评估未评估的
        uncached_llm = still_need_llm
        n_to_evaluate = len(uncached_llm)

        yield {"thought_steps": [{
            "id": step_id,
            "new_sub_step": {
                "message": f"严格验证模式。{len(skip_llm)} 个官方/权威信源已快速放行，{len(cached_llm)} 个已有缓存，正在对 {n_to_evaluate} 个信源进行深度内容质量核查...",
                "type": "info"
            }
        }]}

        # 执行阶段 2：LLM 评估（只评估未缓存的）
        if uncached_llm:
            llm = await get_llm_for_stage("verification", user_id=user_id, preset_id=preset_id)
            batches = _split_batches(uncached_llm)
            semaphore = asyncio.Semaphore(PROFILE_MAX_CONCURRENCY)

            async def _worker(batch_items: list[dict]):
                async with semaphore:
                    return await _process_batch(llm, batch_items)

            batch_results_list = await asyncio.gather(*[_worker(b) for b in batches])

            # 汇总结果并写入缓存
            for idx, batch_items in enumerate(batches):
                batch_map = batch_results_list[idx]
                for i, item in enumerate(batch_items):
                    url = item["url"]
                    d_score = item["_domain_score"]

                    # 提取 LLM 评估值，若失败则 fallback
                    llm_eval = batch_map.get(i, {})
                    llm_val = llm_eval.get("content_quality")
                    c_quality = float(llm_val) if llm_val is not None else d_score
                    has_marketing = bool(llm_eval.get("has_marketing_tone", False))
                    has_expert = bool(llm_eval.get("has_expert_evidence", d_score >= 0.8))

                    # 最终可信度公式：提升内容质量的权重（0.5 vs 0.5）
                    credibility = (d_score * 0.5) + (c_quality * 0.5)

                    # 如果非权威域名但包含了高质量事实，给予奖励
                    if has_expert and d_score < 0.6:
                        credibility = min(0.9, credibility + 0.15)

                    # 如果有营销倾向
                    if has_marketing:
                        if c_quality < 0.5:
                            credibility = max(0.1, credibility - 0.4)
                        else:
                            credibility = max(0.1, credibility - 0.1)

                    profile_entry = {
                        "credibility": round(credibility, 2),
                        "domain_score": d_score,
                        "content_quality": c_quality,
                        "source_type": item["_source_type"],
                        "has_marketing_tone": has_marketing,
                        "has_expert_evidence": has_expert,
                    }

                    profiles[url] = {**profile_entry, "llm_assessed": True}
                    llm_count += 1

                    # 写入缓存
                    url_hash = hashlib.sha256(url.encode()).hexdigest()
                    _profile_cache[url_hash] = profile_entry

        # 补全跳过 LLM 的部分
        for item in skip_llm:
            d_score = item["_domain_score"]
            profiles[item["url"]] = {
                "credibility": d_score,
                "domain_score": d_score,
                "content_quality": d_score,
                "source_type": item["_source_type"],
                "has_marketing_tone": False,
                "has_expert_evidence": True,
                "llm_assessed": False,
            }

        yield {"thought_steps": [{
            "id": step_id, 
            "status": "completed",
            "new_sub_step": {
                "message": f"信源画像构建完毕。已识别 {len(skip_llm)} 个高置信域名，并对 {llm_count} 个中低置信信源进行了内容质量穿透评估。", 
                "type": "success"
            }
        }]}
        
        duration = round(time.time() - start_ts, 2)
        logger.info("profile 完成 | 总计画像数={} | LLM评估数={} | 耗时={}s", len(filtered_items), llm_count, duration)
        yield {"source_profiles": profiles}

    except Exception as e:
        logger.error("profile 节点故障 | error={}", e)
        yield {"thought_steps": [{
            "id": step_id, 
            "status": "error",
            "new_sub_step": {"message": f"画像评估出错: {str(e)}", "type": "error"}
        }]}
        yield {
            "error_log": [ErrorEntry(node="verify_profile", message="信源画像评估失败", detail=str(e))]
        }
