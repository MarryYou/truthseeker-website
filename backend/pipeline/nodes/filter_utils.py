from __future__ import annotations
import re

from backend.core.logging import logger
from backend.pipeline.constants import (
    FILTER_TARGET_CHARS,
    FILTER_BATCH_MIN,
    FILTER_BATCH_MAX,
    FILTER_HIGH_SCORE_THRESHOLD,
    FILTER_MID_SCORE_THRESHOLD,
    FILTER_HIGH_SCORE_WINDOW,
    FILTER_MID_SCORE_WINDOW,
    FILTER_SUMMARY_FALLBACK,
    CONTEXT_UTILIZATION_RATIO,
    MODEL_CONTEXT_WINDOW_DEFAULT,
    CHARS_PER_TOKEN_ESTIMATE,
)

HTML_PATTERN = re.compile(r"<[^>]+>")

def clean_content(content: str) -> str:
    """去 HTML 标签、多余空格并截断"""
    if not content:
        return ""
    content = HTML_PATTERN.sub(" ", content)
    content = re.sub(r"\s+", " ", content).strip()
    return content

def _extract_valuable_results(
    all_results: list[dict],
    valuable_urls: list[str],
    manual_injections: set[str],
) -> list[dict]:
    """仅保留大模型真正感兴趣的（fetch或总结提及的）或人工注入的 URLs"""
    if valuable_urls or manual_injections:
        allowed_urls = set(valuable_urls) | manual_injections
        filtered_all = [r for r in all_results if (r.get("url") or r.get("source_url", "")) in allowed_urls]
        if filtered_all:
            return filtered_all
        logger.info("未过滤出任何匹配 valuable_urls 或 manual_injections 的网页，退化使用全量结果进行保底。")
    else:
        logger.info("未提取到显式 fetch 或引用的 URL，退化使用全量原始检索结果进行过滤。")
    return all_results


def calculate_cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """计算两向量的余弦相似度"""
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = sum(a * a for a in v1) ** 0.5
    norm_b = sum(b * b for b in v2) ** 0.5
    if norm_a * norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)

def calc_batch_size(items: list[dict]) -> int:
    """动态计算批次大小，控制大模型输入 Token 在安全范围内，提升吞吐"""
    if not items:
        return 8
    total_chars = sum(len(r.get("content", "")) for r in items)
    avg_chars = total_chars / len(items) if items else 0
    if avg_chars == 0:
        return 8
    return max(FILTER_BATCH_MIN, min(FILTER_BATCH_MAX, int(FILTER_TARGET_CHARS / max(avg_chars, 100))))

def get_surgical_window(content: str, dimensions: list[str], window_size: int = 2000) -> str:
    """基于维度关键词的定向采样（Surgical Truncation）
    
    不再盲目截取开头，而是在正文中寻找维度关键词最密集的区域。
    """
    if not content or not dimensions:
        return content[:window_size] if content else ""
    
    # 清洗文本，移除多余空格
    text = clean_content(content)
    if len(text) <= window_size:
        return text
        
    # 提取所有维度中的关键词
    all_keywords = []
    for d in dimensions:
        all_keywords.extend(re.findall(r"[\u4e00-\u9fa5\w]+", d))
    keywords = [k for k in all_keywords if len(k) >= 2]
    
    if not keywords:
        return text[:window_size]
        
    # 寻找关键词密度最高的窗口
    best_start = 0
    max_matches = -1
    
    # 步长设为窗口的一半，快速扫描
    step = window_size // 2
    for start in range(0, len(text) - window_size, step):
        chunk = text[start : start + window_size].lower()
        matches = sum(1 for k in keywords if k.lower() in chunk)
        if matches > max_matches:
            max_matches = matches
            best_start = start
            
    # 适当向回偏移一点，确保上下文连贯
    actual_start = max(0, best_start - 200)
    return text[actual_start : actual_start + window_size]

def _apply_token_pruning(keep_items: list[dict], dimensions: list[str]) -> tuple[list[dict], int]:
    """动态 Token 预算制截断 (针对 128k 优化)"""
    total_token_budget = int(MODEL_CONTEXT_WINDOW_DEFAULT * CONTEXT_UTILIZATION_RATIO)
    total_char_budget = int(total_token_budget * CHARS_PER_TOKEN_ESTIMATE)
    
    current_total_chars = 0
    final_pruned_items: list[dict] = []
    
    # 按分数从高到低排列
    keep_items.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    
    for item in keep_items:
        if current_total_chars >= total_char_budget:
            break
            
        score = item.get("relevance_score", 0)
        content = item.get("content", "")
        
        # ── 阶梯式预算分发 ──
        if score >= FILTER_HIGH_SCORE_THRESHOLD:
            # 高分信源
            item["content"] = get_surgical_window(content, dimensions, window_size=FILTER_HIGH_SCORE_WINDOW)
        elif score >= FILTER_MID_SCORE_THRESHOLD:
            # 中分信源
            item["content"] = get_surgical_window(content, dimensions, window_size=FILTER_MID_SCORE_WINDOW)
        else:
            # 低分信源
            item["content"] = f"[低分信源，仅保留摘要] {item.get('summary', '')}"[:FILTER_SUMMARY_FALLBACK]
            
        current_total_chars += len(item["content"])
        final_pruned_items.append(item)
        
    return final_pruned_items, current_total_chars
