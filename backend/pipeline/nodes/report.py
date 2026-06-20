from __future__ import annotations
import asyncio
import json
import re
from typing import Any, AsyncIterator, cast
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from backend.pipeline.state import StateHelper
from backend.pipeline.types import ResearchState, PipelineAbortError
from backend.pipeline.constants import (
    REPORT_MAX_CLAIMS,
    REPORT_MAX_SOURCES
)
from backend.pipeline.prompts import REPORT_PIPELINE_SYSTEM, REPORT_PIPELINE_HUMAN
from backend.core.llm import get_llm_for_stage
from backend.db.store import get_store_from_config
from backend.utils.llm_utils import extract_llm_content
from backend.core.logging import logger
from backend.utils.retry import retry


def _clean_title(title: str) -> str:
    """清理标题杂质：去除截断符、常见网站后缀等"""
    if not title:
        return "未知来源"
    title = re.sub(r"[\.\s\-—_]{2,}(\]|$)", "", title)
    suffixes = [
        r" - 百度百科", r"_百度百科", r" - 维基百科", r" - 知乎", r"_知乎",
        r"-新浪新闻", r"-搜狐新闻", r"-网易", r"-腾讯网", r"\|.*$", r"—.*$"
    ]
    for s in suffixes:
        title = re.sub(s, "", title)
    return title.strip()


def _post_process_markdown(text: str) -> str:
    """Markdown 后置美化：清理多余标点、修复格式残次"""
    text = re.sub(r"([。！？])\1+", r"\1", text)
    text = re.sub(r"\.{2,}[。]", "。", text)
    text = re.sub(r"^```markdown\n", "", text, flags=re.I)
    text = re.sub(r"\n```$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"^[，,、。.\s]+", "", text)  # 去除前导标点
    return text.strip()


@retry(max_retries=1, base_delay=1.0)
async def _generate_report_content(
    query: str,
    intent_type: str,
    claims: list[dict],
    conflicts: list[dict],
    sources: list[dict],
    instruction: str | None = None,
    user_id: str | None = None,
    preset_id: str | None = None,
    verdict_first: bool = False,
    include_comparison: bool = True,
    report_sections: list[str] | None = None,
    history_summary: str = "",
) -> str:
    """调用 LLM 生成最终 Markdown 报告正文 (Pipeline 深度模式)"""

    # 1. 证据分层处理
    sorted_claims = sorted(claims, key=lambda x: {"primary": 0, "secondary": 1, "indirect": 2}.get(x.get("importance", "indirect"), 3))
    
    # 2. 构造信源索引 (极简引用模式)
    source_payload = []
    for s in sources[:REPORT_MAX_SOURCES]:
        source_payload.append({
            "title": _clean_title(s.get("title", "")),
            "url": s.get("url", s.get("source_url", "")),
            "summary": (s.get("summary") or s.get("snippet") or "")[:400]
        })

    sys_prompt = REPORT_PIPELINE_SYSTEM
    human_prompt = REPORT_PIPELINE_HUMAN.format(
        query=query,
        intent_type=intent_type,
        claims_json=json.dumps(sorted_claims[:REPORT_MAX_CLAIMS], ensure_ascii=False),
        conflicts_json=json.dumps(conflicts, ensure_ascii=False),
        sources_json=json.dumps(source_payload, ensure_ascii=False),
        report_sections=report_sections or "根据内容自主决定",
        verdict_first="开启" if verdict_first else "普通",
        include_comparison="根据内容需要决定" if include_comparison else "不包含"
    )

    if history_summary:
        human_prompt += f"\n\n<history_background>\n{history_summary}\n</history_background>\n⚠️ 以上历史背景仅供了解对话前情，禁止在回答中复写。你的报告必须仅围绕最新问题「{query}」展开。"
    
    if instruction:
        human_prompt += f"\n\n<special_instruction>\n{instruction}\n</special_instruction>"

    messages = [SystemMessage(content=sys_prompt), HumanMessage(content=human_prompt)]
    
    llm = await get_llm_for_stage("report", user_id=user_id or "default", preset_id=preset_id)

    full_content = ""
    try:
        ait = llm.astream(messages).__aiter__()
        while True:
            try:
                chunk = await asyncio.wait_for(ait.__anext__(), timeout=120)
            except StopAsyncIteration:
                break
            if chunk and hasattr(chunk, "content"):
                full_content += str(chunk.content)
    except asyncio.TimeoutError:
        logger.warning("报告生成 LLM 流式调用超时（120s），返回已生成的 {} 字符", len(full_content))

    return _post_process_markdown(extract_llm_content(full_content))


async def report_node(state: ResearchState, config: RunnableConfig) -> AsyncIterator[dict[str, Any]]:
    """报告生成与润色 Node (多态处理器)"""
    h = StateHelper(state)
    execution_mode = state["control"].get("execution_mode", "research_pipeline")
    logger.info("report 启动 | 模式={} | 执行最终成文", execution_mode)
    
    query = h.query
    intent_type = h.intent_type
    report_instruction = state["output"]["pipeline"].get("report_instruction", "")
    conflict_dimensions = state["runtime"]["pipeline"].get("conflict_dimensions", [])
    insufficient_dimensions = state["runtime"]["pipeline"].get("insufficient_dimensions", [])
    overall_confidence = state["output"]["pipeline"].get("overall_confidence", 0.5)
    user_id = h.user_id
    preset_id = state["context"].get("preset_id")

    step_id = "generate_report_prompt"
    yield h.update_thought_step(step_id, "", status="running", label="编撰研究报告")

    rs = get_store_from_config(config)
    overrides = h.strategy_overrides

    try:
        final_report_md: str = ""
        filtered_key = state["output"]["diagnostics"].get("store_refs", {}).get("filtered", "final")
        all_sources = await rs.load_filtered_results(filtered_key)
        if not all_sources:
            all_sources = await rs.load_all_search_results()

        # ── 路径 A：Agent 模式（直接使用 Agent 生成的内容，不走润色路径）──
        if execution_mode in ("fast_react", "expert_search"):
            report_prompt = str(state["output"]["agent"].get("report_prompt", ""))
            stored_report = str(await rs.load_report("final") or "")
            logger.debug("Agent report sources | report_prompt_len={} stored_len={}", len(report_prompt), len(stored_report))
            draft_md = report_prompt or stored_report
            if not draft_md:
                messages = state["memory"].get("messages", [])
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage):
                        draft_md = str(msg.content)
                        break

            if not draft_md:
                raise PipelineAbortError("无法获取回答草稿")

            yield h.update_thought_step(step_id, "Agent 回答生成完毕。", type="info")
            final_report_md = draft_md
            meta = ""

        # ── 路径 B：Pipeline 模式 (深度重写) ──
        else:
            claims_key = state["output"]["diagnostics"].get("store_refs", {}).get("claims", "final")
            claims = await rs.load_claims(claims_key)

            conflicts_info = [{"dimension": dim, "description": "该维度存在来源矛盾"} for dim in conflict_dimensions]
            for dim in insufficient_dimensions:
                conflicts_info.append({"dimension": dim, "description": "该维度信息不足"})

            # 动态格式推断：根据证据复杂度注入样式要求
            dynamic_instruction = report_instruction or ""
            if not dynamic_instruction:
                total_claims = len(claims or [])
                if total_claims < 5:
                    dynamic_instruction = "当前收集到的核心证据较少，请采用简练的条目式或段落式直接回答，无需过度渲染多级章节。"
                elif total_claims > 15 or len(conflict_dimensions) > 0:
                    dynamic_instruction = "当前收集到的证据繁多或存在争议，请务必使用多级标题清晰划分维度，并强烈建议使用 Markdown 表格来对比不同信源的数据或观点出入。"

            yield h.update_thought_step(step_id, f"基于 {len(claims or [])} 条声明和 {len(all_sources)} 个信源编撰深度研报...", type="info")
            final_report_md = cast(str, await _generate_report_content(
                query=query,
                intent_type=intent_type,
                claims=claims or [],
                conflicts=conflicts_info,
                sources=all_sources,
                instruction=dynamic_instruction,
                user_id=user_id,
                preset_id=preset_id,
                verdict_first=bool(overrides.get("verdict_first", False)),
                include_comparison=bool(overrides.get("include_comparison", True)),
                report_sections=overrides.get("report_sections"),
                history_summary=state["memory"].get("history_summary", ""),
            ))
            
            # ── 视觉美化：生成进度条与结论卡片 ──
            def _get_conf_desc(c: float) -> str:
                if c >= 0.9: return "极高"
                if c >= 0.7: return "可靠"
                if c >= 0.5: return "中等"
                return "偏低"
            
            bar_filled = int(overall_confidence * 10)
            conf_bar = "█" * bar_filled + "░" * (10 - bar_filled)
            conf_label = _get_conf_desc(overall_confidence)
            conflict_label = f"⚠️ {', '.join(conflict_dimensions)}" if conflict_dimensions else "✅ 暂无显著冲突"
            
            meta = (
                f"\n\n---\n"
                f"> **📊 研究结论概要**\n"
                f"> \n"
                f"> * **综合置信度**：`{conf_bar}` **{overall_confidence:.0%}** ({conf_label})\n"
                f"> * **矛盾/争议点**：{conflict_label}\n"
            )

        # ── 统一落库 ──
        report_key = state["output"]["diagnostics"].get("store_refs", {}).get("report", "final")
        await rs.save_report(report_key, final_report_md)

        yield h.update_thought_step(step_id, "研究报告编撰完毕。", type="success", status="completed")
        
        output_data = {"agent" if execution_mode in ("fast_react", "expert_search") else "pipeline": {"report_prompt": final_report_md + meta}}
        yield {"output": {**output_data, "diagnostics": {"store_refs": {"report": report_key}}}}

    except PipelineAbortError as e:
        logger.error("报告处理中止 | error={}", e)
        raise
    except Exception as e:
        logger.error("报告处理失败 | error={}", e)
        yield h.update_thought_step(step_id, f"报告编撰过程中遭遇严重异常: {str(e)}", type="error", status="error")
        yield h.add_error(step_id, "报告生成失败", str(e))
        raise PipelineAbortError(f"最终报告生成节点异常，任务终止: {str(e)}") from e
