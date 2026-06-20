from __future__ import annotations
from langchain_core.runnables import RunnableConfig
from backend.pipeline.types import ResearchState
from backend.core.llm import get_llm_for_stage
from backend.utils.llm_utils import extract_llm_content
from backend.core.logging import logger

SUMMARY_PROMPT = """请用 2-3 句话总结以下问答内容中的核心事实。
你的目标是提取关键数据、结论、名称和时间，为下一轮对话提供背景。

用户问题：{query}
AI 回答：{answer}

要求：只提取事实性信息，保持极其简练，不要任何开场白。"""

SOCIAL_WORDS = frozenset({
    "你好", "谢谢", "再见", "嗨", "hello", "hi", "thanks", "thank", "bye", "早上好", "下午好", "晚上好"
})

async def summary_node(state: ResearchState, config: RunnableConfig) -> dict:
    """总结节点：在问答结束后提取事实摘要，用于多轮对话上下文"""
    query = state["runtime"]["shared"].get("query", "")
    answer = state["output"]["agent"].get("report_prompt", "") or state["output"]["pipeline"].get("report_prompt", "")
    user_id = state["context"].get("user_id", "default")
    preset_id = state["context"].get("preset_id")
    
    execution_mode = state["control"].get("execution_mode", "research_pipeline")
    # 💡 极速模式下针对日常社交词或极短输入，直接跳过 LLM 事实摘要生成，以极致提速并省 Token
    if execution_mode == "fast_react":
        clean_query = query.strip().lower()
        if len(clean_query) <= 3 or any(w in clean_query for w in SOCIAL_WORDS):
            logger.info("极速模式简单会话，跳过摘要生成")
            return {"memory": {"history_summary": state["memory"].get("history_summary", "")}}

    if not answer:
        logger.warning("Summary Node 缺少回答内容，跳过总结 | query='{}' preset_id={}", query[:30], preset_id)
        return {}

    try:
        logger.debug("开始为当前回答生成事实摘要 | answer_len={}", len(answer))
        # Agent 模式复用自身模型，Pipeline 模式使用默认 understanding 模型
        summary_stage = execution_mode if execution_mode in ("fast_react", "expert_search") else "understanding"
        llm = await get_llm_for_stage(summary_stage, user_id=user_id, preset_id=preset_id)
        
        truncated_answer = answer[:3000]
        prompt = SUMMARY_PROMPT.format(query=query, answer=truncated_answer)
        
        resp = await llm.ainvoke(prompt)
        summary = extract_llm_content(resp).strip()
        
        logger.info("生成历史事实摘要完毕 | len={}", len(summary))
        return {"memory": {"history_summary": summary}}
        
    except Exception as e:
        logger.error("生成事实摘要失败 | error={}", e)
        return {"memory": {"history_summary": f"关于 {query} 的讨论。"}}
