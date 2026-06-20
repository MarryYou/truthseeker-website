"""arbitrate 节点 — 矛盾汇总、置信度聚合、结果写 Store。

职责：
  1. 扫描 claims 的 verdict 字段，归纳 conflict_dimensions / insufficient_dimensions
  2. 按维度等权重计算 overall_confidence（复用修复后的聚合逻辑）
  3. 将 claims 落库（写入 Store），更新 store_refs
  4. 生成人类可读的 warnings 列表
  5. 输出字段与 ResearchState 同名，LangGraph 自动合并回父图
"""
from __future__ import annotations
import time
from collections import defaultdict
from typing import AsyncIterator, Any

from langchain_core.runnables import RunnableConfig

from backend.core.logging import logger
from backend.db.store import get_store_from_config
from backend.pipeline.subgraphs.verify.state import VerifyState
from backend.pipeline.types import ErrorEntry

# verdict → 该声明对置信度的贡献权重（consistency_score 已由 tripartite 提供，此处作为兜底）
_VERDICT_BASE_SCORE: dict[str, float] = {
    "consistent": 1.0,
    "mostly_consistent": 0.8,
    "single_source": 0.6,
    "unverifiable": 0.4,
    "contradictory": 0.1,
}

# 维度级别的固定基准分（用于缺失/矛盾/不足的维度）
_DIM_CONF_MISSING = 0.0     # 该维度完全无存活结果
_DIM_CONF_CONFLICT = 0.4    # 该维度存在信源矛盾
_DIM_CONF_INSUFFICIENT = 0.5  # 该维度有结果但 LLM 判定覆盖不足


def _compute_dim_confidence(
    dim: str,
    dim_claims: list[dict],
    is_conflict: bool,
    is_insufficient: bool,
    has_data: bool,
    dim_sources: list[dict] | None = None,
    source_profiles: dict[str, dict] | None = None,
) -> float:
    """计算单个维度的置信度分数。"""
    # 优先级：有数据且冲突 < 有数据且不足 < 无数据但标记为不足 < 无数据且未标记
    if is_conflict:
        return _DIM_CONF_CONFLICT
    if is_insufficient:
        return _DIM_CONF_INSUFFICIENT
    
    if not has_data:
        return _DIM_CONF_MISSING
    
    # 若无 claims 提取（Standard 快速通道），直接根据同维度信源可信度算均值
    if not dim_claims:
        if dim_sources and source_profiles:
            credibilities = []
            for s in dim_sources:
                url = s.get("url")
                if url:
                    cred = source_profiles.get(url, {}).get("credibility")
                    if cred is not None:
                        credibilities.append(float(cred))
            if credibilities:
                return round(sum(credibilities) / len(credibilities), 3)
        return _DIM_CONF_INSUFFICIENT

    # 取该维度已验证声明的 consistency_score 均值（primary 声明权重 x2）
    weighted_sum = 0.0
    weight_total = 0.0
    for c in dim_claims:
        score = float(c.get("consistency_score", _VERDICT_BASE_SCORE.get(c.get("verdict", "unverifiable"), 0.5)))
        weight = 2.0 if c.get("importance") == "primary" else 1.0
        weighted_sum += score * weight
        weight_total += weight
    return round(weighted_sum / weight_total, 3) if weight_total else _DIM_CONF_INSUFFICIENT


async def arbitrate_node(state: VerifyState, config: RunnableConfig) -> AsyncIterator[dict[str, Any]]:
    """汇总矛盾维度、聚合置信度、写 Store、生成 warnings (支持思考链汇报)。"""
    start_ts = time.time()
    logger.info("arbitrate 启动 | 开始最终共识仲裁与打分")
    
    step_id = "verify_arbitrate"
    yield {"thought_steps": [{
        "id": step_id, 
        "label": "证据可信度裁决", 
        "status": "running"
    }]}

    try:
        claims: list[dict] = state.get("claims", [])
        dimensions: list[str] = state.get("dimensions", [])
        insufficient_dims_from_atomize: list[str] = state.get("insufficient_dimensions", [])
        store_refs_existing: dict[str, str] = state.get("store_refs", {})

        rs = get_store_from_config(config)

        # 1. 按维度归纳 claims 与网页信源
        filtered_items = state.get("_filtered_items", [])
        dim_sources: dict[str, list[dict]] = defaultdict(list)
        for item in filtered_items:
            dim = item.get("dimension", "通用")
            dim_sources[dim].append(item)

        dim_claims: dict[str, list[dict]] = defaultdict(list)
        for c in claims:
            dim = c.get("dimension", "通用")
            dim_claims[dim].append(c)

        # 2. 找出有矛盾声明的维度
        conflict_dimensions: list[str] = []
        for dim, dim_cs in dim_claims.items():
            if any(c.get("verdict") == "contradictory" for c in dim_cs):
                conflict_dimensions.append(dim)

        # 3. 收集 insufficient
        insufficient_dimensions: list[str] = list(insufficient_dims_from_atomize)
        for dim, dim_cs in dim_claims.items():
            if dim in insufficient_dimensions or dim in conflict_dimensions:
                continue
            if dim_cs and all(c.get("verdict") == "unverifiable" for c in dim_cs if "verdict" in c):
                insufficient_dimensions.append(dim)

        yield {"thought_steps": [{
            "id": step_id, 
            "new_sub_step": {"message": "正在根据多方核验结果，对各研究维度进行加权打分与矛盾冲突判定...", "type": "info"}
        }]}

        # 4. 按声明加权平均计算 overall_confidence（取代按维度等权平均）
        #    每条声明的 consistency_score 按重要性加权，primary 权重 x2
        if claims:
            weighted_sum = 0.0
            weight_total = 0.0
            for c in claims:
                score = float(c.get("consistency_score", 0.5))
                weight = 2.0 if c.get("importance") == "primary" else 1.0
                weighted_sum += score * weight
                weight_total += weight
            overall_confidence = round(weighted_sum / weight_total, 3) if weight_total else 0.5
        else:
            overall_confidence = 0.5

        # 如果存在严重冲突维度，整体可信度应受到惩罚，而非简单均值掩盖
        if conflict_dimensions:
            overall_confidence = round(overall_confidence * 0.8, 3)

        # 5. 生成人类可读 warnings
        warnings: list[str] = []
        if conflict_dimensions:
            warnings.append(f"以下维度存在信源矛盾，建议补充核实：{'、'.join(conflict_dimensions)}")
        if insufficient_dimensions:
            warnings.append(f"以下维度信息覆盖不足，建议追加搜索：{'、'.join(insufficient_dimensions)}")
        if overall_confidence < 0.5:
            warnings.append(f"综合置信度偏低（{overall_confidence:.22f}），本报告结论仅供参考")

        # 6. 将 claims 落库
        claims_key = state.get("store_refs", {}).get("claims", "final")
        await rs.save_claims(claims_key, claims)

        # 7. 更新已验证事实缓冲区 (v3.0 知识承袭)
        # 仅选择已达成共识的声明
        new_proven_facts = [
            {
                "claim": c["text"], 
                "dimension": c.get("dimension", "通用"), 
                "source_url": c.get("source_url")
            }
            for c in claims 
            if c.get("verdict") in ("consistent", "mostly_consistent")
        ]

        yield {"thought_steps": [{
            "id": step_id, 
            "status": "completed",
            "new_sub_step": {
                "message": f"裁决完成。全网共识度: {overall_confidence:.0%}，识别到 {len(conflict_dimensions)} 处显著冲突。", 
                "type": "success"
            }
        }]}

        duration = round(time.time() - start_ts, 2)
        logger.info("arbitrate 完成 | 置信度={} | 矛盾维度={} | 耗时={}s", overall_confidence, len(conflict_dimensions), duration)

        yield {
            "conflict_dimensions": conflict_dimensions,
            "insufficient_dimensions": insufficient_dimensions,
            "overall_confidence": overall_confidence,
            "warnings": warnings,
            "store_refs": {**store_refs_existing, "claims": claims_key},
            "proven_facts": new_proven_facts,
        }
    except Exception as e:
        logger.error("arbitrate 节点发生异常 | error={}", e)
        yield {"thought_steps": [{
            "id": step_id, 
            "status": "error",
            "new_sub_step": {"message": f"最终裁决出错: {str(e)}", "type": "error"}
        }]}
        yield {
            "error_log": [ErrorEntry(node="verify_arbitrate", message="一致性仲裁与打分失败", detail=str(e))]
        }

