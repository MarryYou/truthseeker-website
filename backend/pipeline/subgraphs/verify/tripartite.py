"""tripartite 节点 — 跨信源一致性校验（批量版，per-dimension batching）。

设计原则：
  - LLM 充当「裁判」：比较多信源之间的陈述是否一致，而不是猜测事实真假
  - 按维度分组批量验证：同一维度的全部 claims 合并到一个 LLM call（10+ calls → 2-3 calls）
  - 各维度间并发执行（asyncio.Semaphore 限速）
  - indirect 声明（背景信息）不单独验证，继承所在维度的整体结论

核心改进：
  旧逻辑：每条 claim 1 次 LLM（~15 calls）
  新逻辑：每个维度 1 次 LLM batch（~3 calls）
"""
from __future__ import annotations
import asyncio
import re
import json
import math
import time
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from langchain_core.runnables import RunnableConfig

from backend.core.llm import get_llm_for_stage
from backend.core.logging import logger
from backend.pipeline.subgraphs.verify.state import VerifyState
from backend.pipeline.types import ErrorEntry
# from backend.pipeline.prompts import TRIPARTITE_BATCH_PROMPT, TRIPARTITE_PROMPT (Obsolete)
from collections import defaultdict
from langchain_core.messages import SystemMessage, HumanMessage
from backend.pipeline.prompts import TRIPARTITE_SYSTEM, TRIPARTITE_HUMAN, TRIPARTITE_BATCH_SYSTEM, TRIPARTITE_BATCH_HUMAN, SINGLE_SOURCE_FACTUALITY_SYSTEM, SINGLE_SOURCE_FACTUALITY_HUMAN
from backend.services.embedding_service import embed_documents_with_preset
from backend.db.engine import async_session
from backend.utils.llm_utils import parse_llm_json, extract_llm_content, get_node_config

from backend.pipeline.constants import (
    VERIFY_BATCH_CLAIMS_MAX,
    VERIFY_MAX_EVIDENCE_PER_CLAIM
)

# 维度间并发上限
TRIPARTITE_MAX_CONCURRENCY = 5
# 每条 claim 最多参考多少个来源证据（防 token 超限）
TRIPARTITE_MAX_EVIDENCE = VERIFY_MAX_EVIDENCE_PER_CLAIM
# 每个维度批次最大 claims 数（超过则回落到 per-claim 模式以控制 token）
TRIPARTITE_MAX_CLAIMS_PER_BATCH = VERIFY_BATCH_CLAIMS_MAX
# 只对 primary + secondary 声明做跨源校验（indirect 代价不划算）
_VALIDATE_IMPORTANCE = {"primary", "secondary"}

# verdict → consistency_score 映射（用于无分数时的兜底）
_VERDICT_SCORE: dict[str, float] = {
    "consistent": 1.0,
    "mostly_consistent": 0.8,
    "single_source": 0.6,
    "unverifiable": 0.4,
    "contradictory": 0.1,
}


def _safe_float(val: Any, default: float = 0.5) -> float:
    """安全地将各种不规范值转换为 float，具备正则提取和清洗能力"""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return default
            
        # 1. 拦截大模型占位符样例 "0.0-1.0"
        if "0.0-1.0" in val_str:
            return default
            
        # 2. 拦截并处理其它的范围，例如 "0.7-0.8"
        if "-" in val_str:
            parts = val_str.split("-")
            try:
                return _safe_float(parts[0], default)
            except Exception:
                pass
                
        # 3. 处理百分比，如 "85%"
        if val_str.endswith("%"):
            try:
                return float(val_str[:-1].strip()) / 100.0
            except Exception:
                pass
                
        # 4. 用正则提取出第一个浮点数/整数数字，如 "0.85 (based on...)"
        match = re.search(r"[-+]?\d*\.\d+|\d+", val_str)
        if match:
            try:
                num = float(match.group())
                # 如果数字大于 1.0，但没有百分比符号，可能是把百分比写成了 0-100 的整数，在此除以 100 还原
                if num > 1.0:
                    return num / 100.0
                return num
            except Exception:
                pass
                
    return default


def _get_root_domain(url: str) -> str:
    if not url:
        return ""
    try:
        hostname = urlparse(url).hostname or ""
        parts = hostname.split(".")
        if len(parts) >= 3 and parts[-2] in ("com", "edu", "gov", "org", "net", "ac", "co"):
            return ".".join(parts[-3:])
        return ".".join(parts[-2:]) if len(parts) >= 2 else hostname
    except Exception:
        return url


def _find_evidence(
    claim: dict,
    filtered_items: list[dict],
    source_profiles: dict[str, dict],
    claim_vec_map: dict[str, list[float]] | None = None,
    doc_vec_map: dict[str, list[float]] | None = None,
    min_evidence: int = 2,
) -> list[dict]:
    """为一条 claim 从 filtered_items 中收集信源证据，结合向量余弦相似度与可信度综合排序。"""
    target_dim = claim.get("dimension", "")
    
    # 扩大召回范围：不仅找同维度，还找通用维度，甚至在证据不足时全量召回
    pool_items = [r for r in filtered_items if (r.get("dimension") or "通用") in (target_dim, "通用")]
    
    # 如果同维度+通用的池子都达不到最小证据数，则放宽至所有过滤后结果（跨维度补漏）
    if len(pool_items) < min_evidence and len(filtered_items) >= min_evidence:
        pool_items = filtered_items

    # 优先引用声明原始来源，再按 credibility 降序排其余来源
    origin_url = claim.get("source_url", "")
    claim_text = claim.get("text", "")
    claim_vec = claim_vec_map.get(claim_text) if claim_vec_map else None

    def cosine_similarity(v1, v2):
        if not v1 or not v2:
            return 0.0
        dot_prod = sum(a * b for a, b in zip(v1, v2))
        mag1 = math.sqrt(sum(a * a for a in v1))
        mag2 = math.sqrt(sum(b * b for b in v2))
        if mag1 * mag2 == 0:
            return 0.0
        return dot_prod / (mag1 * mag2)

    scored_items = []
    for r in pool_items:
        url = r.get("url", "")
        # 优先读取 full_text，回退至 content (手术级采样)
        doc_text = (r.get("full_text") or r.get("content") or r.get("summary") or r.get("snippet") or "")[:1500]
        
        sim_score = 0.5  # 默认兜底相似度
        if claim_vec and doc_vec_map:
            doc_vec = doc_vec_map.get(doc_text)
            if doc_vec:
                sim_score = cosine_similarity(claim_vec, doc_vec)
                
        credibility = source_profiles.get(url, {}).get("credibility", 0.5)
        
        # 混合检索评分：相似度权重为 0.7，可信度权重为 0.3
        score = 0.7 * sim_score + 0.3 * credibility
        is_origin = (url == origin_url)
        
        scored_items.append((r, score, is_origin))

    # 排序优先级：原始引用优先，然后按混合评分降序
    scored_items.sort(key=lambda x: (not x[2], -x[1]))

    evidence = []
    seen_urls = set()
    for r, score, _ in scored_items:
        url = r.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)

        profile = source_profiles.get(url, {})
        evidence.append({
            "url": url,
            "title": r.get("title", ""),
            "credibility": profile.get("credibility", 0.5),
            "source_type": profile.get("source_type", "unknown"),
            "content": (r.get("full_text") or r.get("content") or r.get("summary") or r.get("snippet") or "")[:1500],
            "similarity_score": score if claim_vec else None
        })
        if len(evidence) >= max(TRIPARTITE_MAX_EVIDENCE, min_evidence):
            break
    return evidence


# 单条核验超时（秒）
_VERIFY_ONE_TIMEOUT = 60
# 批量核验超时（秒）
_VERIFY_BATCH_TIMEOUT = 90
# 单维度最大声明数，超过则拆分子 batch 并发
_MAX_CLAIMS_PER_BATCH = 10


def _single_source_score(claim: dict, source_profiles: dict[str, dict]) -> float:
    """获取单信源声明基于原始来源可信度的分数，替代硬编码 0.6。"""
    source_url = claim.get("source_url", "")
    if source_url and source_profiles:
        return source_profiles.get(source_url, {}).get("credibility", 0.6)
    return 0.6


_VERIFY_ONE_FACTUALITY_TIMEOUT = 30


async def _verify_single_source_factuality(
    llm: Any,
    claim: dict,
    source_profiles: dict[str, dict],
    numeric_verify: bool,
) -> dict:
    """对单信源声明做事实合理性核验（用 LLM 自身知识判断，非交叉比对）"""
    source_url = claim.get("source_url", "")
    credibility = _single_source_score(claim, source_profiles)

    sys_prompt = SINGLE_SOURCE_FACTUALITY_SYSTEM
    human_prompt = SINGLE_SOURCE_FACTUALITY_HUMAN.format(
        claim_text=claim.get("text", ""),
        credibility=f"{credibility:.2f}" if credibility else "未知",
    )

    messages = [SystemMessage(content=sys_prompt), HumanMessage(content=human_prompt)]
    llm_start = time.time()
    try:
        resp = await asyncio.wait_for(llm.ainvoke(messages), timeout=_VERIFY_ONE_FACTUALITY_TIMEOUT)
        llm_duration = round(time.time() - llm_start, 2)
        raw = extract_llm_content(resp)

        json_match = re.search(r"<json>(.*?)</json>", raw, re.DOTALL)
        parsed = parse_llm_json(json_match.group(1) if json_match else raw)

        factuality_score = _safe_float(parsed.get("factuality_score"), credibility)
        # 跟 credibility 取加权平均（factuality 权重 0.6，credibility 权重 0.4）
        final_score = round(0.6 * factuality_score + 0.4 * credibility, 3)

        logger.debug("单信源事实核验 | claim='{}...' credibility={} factuality={} final={} duration={}s",
                     (claim.get("text") or "")[:30], credibility, factuality_score, final_score, llm_duration)

        return {
            "verdict": "single_source",
            "consistency_score": final_score,
            "conflicts": [],
            "reasoning": parsed.get("reasoning", "单信源事实核验"),
        }
    except asyncio.TimeoutError:
        logger.warning("单信源事实核验超时 | claim='{}...' timeout={}s", (claim.get("text") or "")[:30], _VERIFY_ONE_FACTUALITY_TIMEOUT)
        return {"verdict": "single_source", "consistency_score": credibility, "conflicts": [], "reasoning": "核验超时"}
    except Exception as e:
        logger.warning("单信源事实核验失败 | claim='{}...' error={}", (claim.get("text") or "")[:30], e)
        return {"verdict": "single_source", "consistency_score": credibility, "conflicts": [], "reasoning": f"核验出错: {str(e)}"}


async def _verify_one_claim(
    llm: Any,
    query: str,
    claim: dict,
    evidence: list[dict],
    numeric_verify: bool
) -> dict:
    """对单条声明做跨信源一致性 LLM 裁判"""
    evidence_json = json.dumps([
        {
            "index": i,
            "source": e.get("source_name", "未知"),
            "content": e.get("content", "")[:1200]
        }
        for i, e in enumerate(evidence)
    ], ensure_ascii=False)

    sys_prompt = TRIPARTITE_SYSTEM
    if not numeric_verify:
        sys_prompt += "\n\n⚠️ 额外要求：请忽略数字/数值方面的细微差异，只关注语义核心的一致性。"

    human_prompt = TRIPARTITE_HUMAN.format(
        claim_text=claim.get("text", ""),
        evidence_json=evidence_json
    )

    messages = [SystemMessage(content=sys_prompt), HumanMessage(content=human_prompt)]
    llm_start = time.time()
    try:
        resp = await asyncio.wait_for(llm.ainvoke(messages), timeout=_VERIFY_ONE_TIMEOUT)
        llm_duration = round(time.time() - llm_start, 2)
        logger.debug("单条核验 LLM 调用 | claim='{}...' evidence={} duration={}s",
                     (claim.get("text") or "")[:30], len(evidence), llm_duration)
        raw = extract_llm_content(resp)

        json_match = re.search(r"<json>(.*?)</json>", raw, re.DOTALL)
        parsed = parse_llm_json(json_match.group(1) if json_match else raw)

        verdict = parsed.get("verdict", "unverifiable")
        default_score = _VERDICT_SCORE.get(verdict, 0.5)
        consistency_score = _safe_float(parsed.get("consistency_score"), default_score)
        citation_confidence = _safe_float(parsed.get("citation_confidence"), 0.5)
        return {
            "verdict": verdict,
            "consistency_score": consistency_score,
            "citation_confidence": citation_confidence,
            "conflicts": parsed.get("conflicts", []),
            "reasoning": parsed.get("reasoning", "")
        }
    except asyncio.TimeoutError:
        logger.warning("声明单条核验超时 | claim='{}' timeout={}s", (claim.get("text") or "")[:30], _VERIFY_ONE_TIMEOUT)
        return {
            "verdict": "unverifiable",
            "consistency_score": 0.4,
            "citation_confidence": 0.5,
            "conflicts": [],
            "reasoning": f"核验超时（{_VERIFY_ONE_TIMEOUT}s）"
        }
    except Exception as e:
        logger.warning("声明核验失败 | claim='{}' error={}", (claim.get("text") or "")[:30], e)
        return {
            "verdict": "unverifiable",
            "consistency_score": 0.4,
            "citation_confidence": 0.5,
            "conflicts": [],
            "reasoning": f"核验出错: {str(e)}"
        }


async def _verify_dimension_batch(
    llm: Any,
    query: str,
    dimension: str,
    claims: list[dict],
    filtered_items: list[dict],
    source_profiles: dict[str, dict],
    claim_vec_map: dict[str, list[float]] | None,
    doc_vec_map: dict[str, list[float]] | None,
    min_evidence: int,
    numeric_verify: bool,
) -> list[dict]:
    """按维度批量验证多条声明（1 次 LLM 调用取代 N 次）"""

    # 为每条声明收集证据
    claim_entries = []
    evidence_pool = []
    seen_content = set()

    for i, c in enumerate(claims):
        ev = _find_evidence(c, filtered_items, source_profiles, claim_vec_map, doc_vec_map, min_evidence)

        claim_entries.append({
            "index": i,
            "text": c.get("text", ""),
            "importance": c.get("importance", "secondary"),
            "num_evidence": len(ev),
        })

        for e in ev:
            content = e.get("content", "")[:1200]
            dedup_key = content[:100]
            if dedup_key in seen_content:
                continue
            seen_content.add(dedup_key)
            evidence_pool.append({
                "source_index": len(evidence_pool),
                "source": e.get("source_name", e.get("url", "未知")),
                "content": content,
            })

    claims_json = json.dumps(claim_entries, ensure_ascii=False)[:4000]
    evidence_pool_json = json.dumps(evidence_pool, ensure_ascii=False)[:6000]

    sys_prompt = TRIPARTITE_BATCH_SYSTEM
    if not numeric_verify:
        sys_prompt += "\n\n⚠️ 额外要求：请忽略数字/数值方面的细微差异，只关注语义核心的一致性。"

    human_prompt = TRIPARTITE_BATCH_HUMAN.format(
        dimension=dimension,
        claims_json=claims_json,
        evidence_pool_json=evidence_pool_json,
    )

    messages = [SystemMessage(content=sys_prompt), HumanMessage(content=human_prompt)]
    llm_start = time.time()
    try:
        resp = await asyncio.wait_for(llm.ainvoke(messages), timeout=_VERIFY_BATCH_TIMEOUT)
        llm_duration = round(time.time() - llm_start, 2)
        logger.debug("批量核验 LLM 调用 | dim='{}' claims={} evidence_pool={} duration={}s",
                     dimension, len(claims), len(evidence_pool), llm_duration)
        raw = extract_llm_content(resp)

        json_match = re.search(r"<json>(.*?)</json>", raw, re.DOTALL)
        parsed_list = parse_llm_json(json_match.group(1) if json_match else raw)

        if not isinstance(parsed_list, list):
            raise ValueError("批量验证返回格式不是 JSON 数组")

        result_map = {}
        for entry in parsed_list:
            idx = entry.get("claim_index")
            if idx is not None:
                result_map[idx] = entry

        verified = []
        for i, c in enumerate(claims):
            batch_res = result_map.get(i, {})
            verdict = batch_res.get("verdict", "unverifiable")
            default_score = _VERDICT_SCORE.get(verdict, 0.5)
            consistency_score = _safe_float(batch_res.get("consistency_score"), default_score)
            citation_confidence = _safe_float(batch_res.get("citation_confidence"), 0.5)
            c.update({
                "verdict": verdict,
                "consistency_score": consistency_score,
                "citation_confidence": citation_confidence,
                "conflicts": batch_res.get("conflicts", []),
                "reasoning": batch_res.get("reasoning", "批量验证自动生成"),
            })
            verified.append(c)

        return verified
    except asyncio.TimeoutError:
        logger.warning("维度批量核验超时 | dim='{}' claims={} timeout={}s, 降级至逐条核验",
                       dimension, len(claims), _VERIFY_BATCH_TIMEOUT)
    except Exception as e:
        logger.warning("维度批量核验失败 | dim='{}' claims={} error={}, 降级至逐条核验",
                       dimension, len(claims), e)

    # fallback：逐条回退到单条验证（不含重试，超时兜底后速度快得多）
    verified = []
    for c in claims:
        ev = _find_evidence(c, filtered_items, source_profiles, claim_vec_map, doc_vec_map, min_evidence)
        if len(ev) < 2:
            # 单信源：primary 声明走事实核验，其余直接使用 credibility
            if c.get("importance") == "primary":
                res = await _verify_single_source_factuality(llm, c, source_profiles, numeric_verify)
                c.update(res)
            else:
                c.update({"verdict": "single_source", "consistency_score": _single_source_score(c, source_profiles), "conflicts": [], "reasoning": "仅有单信源支持"})
        else:
            res = await _verify_one_claim(llm, query, c, ev, numeric_verify)
            c.update(res)
        verified.append(c)
    return verified


async def tripartite_node(state: VerifyState, config: RunnableConfig) -> AsyncIterator[dict[str, Any]]:
    """跨信源一致性裁判节点 (支持思考链汇报)"""
    start_ts = time.time()
    logger.info("tripartite 启动 | 开始跨信源一致性校验")
    
    step_id = "verify_tripartite"
    yield {"thought_steps": [{
        "id": step_id, 
        "label": "证据一致性核验", 
        "status": "running"
    }]}

    try:
        query = state.get("query", "")
        claims: list[dict] = state.get("claims", [])
        filtered_items: list[dict] = state.get("_filtered_items", [])
        source_profiles: dict[str, dict] = state.get("source_profiles", {})
        user_id = state.get("user_id", "default")
        preset_id = state.get("preset_id")

        cv_config = await get_node_config(config, "cross_verify")
        min_evidence = cv_config.get("min_evidence_per_claim", 2)
        numeric_verify = cv_config.get("numeric_verify", True)

        if not claims:
            yield {"thought_steps": [{
                "id": step_id, "status": "completed", "new_sub_step": {"message": "无声明可校验。", "type": "info"}
            }]}
            yield {"claims": []}
            return

        to_verify = [c for c in claims if c.get("importance", "indirect") in _VALIDATE_IMPORTANCE]
        skip_indirect = [c for c in claims if c.get("importance", "indirect") == "indirect"]

        if not to_verify:
            yield {"claims": claims}
            return

        llm = await get_llm_for_stage(
            "verification",
            user_id=user_id,
            preset_id=preset_id,
        )

        # 1. 证据聚合 (复用原逻辑但更精简)
        verification_level = state.get("verification_level", "standard")
        claim_vec_map, doc_vec_map = {}, {}
        if verification_level == "strict":
            c_texts = [c["text"] for c in to_verify if c.get("text")]
            d_texts = list(set([
                ((r.get("full_text") or r.get("content") or "")[:1500])
                for r in filtered_items 
                if r.get("full_text") or r.get("content")
            ]))
            if c_texts and d_texts:
                configurable = config.get("configurable", {})
                db = configurable.get("db")
                if db is not None:
                    c_vecs = await embed_documents_with_preset(db, c_texts, user_id=user_id, preset_id=preset_id)
                    d_vecs = await embed_documents_with_preset(db, d_texts, user_id=user_id, preset_id=preset_id)
                else:
                    async with async_session() as session:
                        c_vecs = await embed_documents_with_preset(session, c_texts, user_id=user_id, preset_id=preset_id)
                        d_vecs = await embed_documents_with_preset(session, d_texts, user_id=user_id, preset_id=preset_id)
                claim_vec_map = dict(zip(c_texts, c_vecs))
                doc_vec_map = dict(zip(d_texts, d_vecs))

        # 2. 按维度分组批量验证
        dim_groups = defaultdict(list)
        for c in to_verify:
            dim = c.get("dimension", "通用")
            dim_groups[dim].append(c)

        # 维度间并发（信号量防止打满 API）
        dim_sem = asyncio.Semaphore(TRIPARTITE_MAX_CONCURRENCY)

        async def _process_dim(dim: str, dim_claims: list[dict]) -> list[dict]:
            """并发处理单个维度的核验"""
            async with dim_sem:
                logger.debug("维度核验启动 | dim='{}' claims={}", dim, len(dim_claims))
                if len(dim_claims) == 1:
                    c = dim_claims[0]
                    ev = _find_evidence(c, filtered_items, source_profiles, claim_vec_map, doc_vec_map, min_evidence)
                    logger.debug("声明证据匹配 | dim='{}' claim='{}...' evidence_count={}", dim, (c.get("text") or "")[:30], len(ev))
                    if len(ev) < 2:
                        # 单信源：primary 声明走事实核验，其余直接使用 credibility
                        if c.get("importance") == "primary":
                            res = await _verify_single_source_factuality(llm, c, source_profiles, numeric_verify)
                            c.update(res)
                        else:
                            c.update({"verdict": "single_source", "consistency_score": _single_source_score(c, source_profiles), "conflicts": [], "reasoning": "仅有单信源支持"})
                    else:
                        res = await _verify_one_claim(llm, query, c, ev, numeric_verify)
                        c.update(res)
                    return [c]
                elif len(dim_claims) <= _MAX_CLAIMS_PER_BATCH:
                    batch_verified = await _verify_dimension_batch(
                        llm, query, dim, dim_claims, filtered_items, source_profiles,
                        claim_vec_map, doc_vec_map, min_evidence, numeric_verify
                    )
                    # batch 返回后：对 primary single_source 补充事实核验
                    for i, c in enumerate(batch_verified):
                        if c.get("verdict") == "single_source" and c.get("importance") == "primary":
                            res = await _verify_single_source_factuality(llm, c, source_profiles, numeric_verify)
                            batch_verified[i].update(res)
                    return batch_verified
                else:
                    # 超过单 batch 上限，拆分子 batch 并发执行（信号量防止打满）
                    chunks = [dim_claims[i:i + _MAX_CLAIMS_PER_BATCH] for i in range(0, len(dim_claims), _MAX_CLAIMS_PER_BATCH)]
                    batch_sem = asyncio.Semaphore(3)
                    async def _run_chunk(chunk):
                        async with batch_sem:
                            return await _verify_dimension_batch(
                                llm, query, dim, chunk, filtered_items, source_profiles,
                                claim_vec_map, doc_vec_map, min_evidence, numeric_verify
                            )
                    chunk_results = await asyncio.gather(*[_run_chunk(c) for c in chunks])
                    merged = [item for r in chunk_results for item in r]
                    # 对 primary single_source 补充事实核验
                    for i, c in enumerate(merged):
                        if c.get("verdict") == "single_source" and c.get("importance") == "primary":
                            res = await _verify_single_source_factuality(llm, c, source_profiles, numeric_verify)
                            merged[i].update(res)
                    return merged

        tasks = [_process_dim(d, c) for d, c in dim_groups.items()]
        results = await asyncio.gather(*tasks)
        verified = [item for r in results for item in r]

        all_claims = verified + skip_indirect

        # 统计裁决分布
        verdict_counts = {}
        for c in verified:
            v = c.get("verdict", "")
            verdict_counts[v] = verdict_counts.get(v, 0) + 1
        summary_parts = [f"{v}: {n}" for v, n in verdict_counts.items()]

        duration = round(time.time() - start_ts, 2)
        logger.info("tripartite 完成 | 校验声明数={} | 耗时={}s | 分布={}", len(to_verify), duration, summary_parts)
        yield {"thought_steps": [{
            "id": step_id,
            "status": "completed",
            "new_sub_step": {
                "message": f"一致性校验完成。{len(to_verify)} 条声明 → {'，'.join(summary_parts)}",
                "type": "success"
            }
        }]}
        yield {"claims": all_claims}

    except Exception as e:
        logger.error("tripartite 节点发生异常 | error={}", e)
        yield {"error_log": [ErrorEntry(node="verify_tripartite", message="一致性校验失败", detail=str(e))]}

