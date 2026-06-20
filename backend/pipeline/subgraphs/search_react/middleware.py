"""SearchReAct 中间件 — 对齐 agent 模式 + 旧 SEARCH_EVALUATION 逻辑"""
from __future__ import annotations
from datetime import datetime, UTC
from typing import Callable, Awaitable
from langchain_core.messages import SystemMessage
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

SEARCH_PROMPT = """你是搜索质量评估专家。根据研究维度搜索信息，并评估是否足够。

## 执行准则
1. 使用 `search_web` 搜索，每次针对一个维度或关键词
2. **调用 `search_web` 时请通过 `dimension` 参数指明本次搜索归属的研究维度，以便后续标记结果**
{lang_instruction}
{year_instruction}
5. **评估逻辑**：
   - 信息已足够覆盖维度 → 输出评估结论（needs_more_search: false）
   - 信息不足 → 可针对不足的维度补搜一次关键词，然后强制结束
   - 补搜后仍不足 → 也输出已有结果，不要死循环

当前日期：{current_date}
"""

FINAL_PROMPT = """请评估当前已获取的搜索结果是否足以支持回答用户问题。

## 评估标准
1. 信息完备度：是否已经覆盖了所有研究维度？
2. 质量：是否存在明显的矛盾或信息空白？
3. **成功/失败判定**：
   - 信息完备 → needs_more_search: false, next_strategy: done
   - 信息不完备但已尽力（触及搜索上限或无更多关键词可试）→ 同样输出已有结果，不要死循环

## 输出格式
请按以下格式输出评估结果（不要加 markdown 代码块标记）：

needs_more_search: true/false
next_strategy: done/deep/targeted
reason: <评估理由>
suggested_focus: <下轮搜索重点，10字以内>
keywords: <本轮搜索使用的所有关键词，逗号分隔>
urls: <发现的有价值 URL，逗号分隔>
dimensions_covered: <已覆盖的研究维度，逗号分隔>
summary: <本轮搜索结果摘要>
"""


class SearchAgentMiddleware(AgentMiddleware):
    """搜索 Agent 中间件 — 用实例计数器精确限制搜索轮次"""

    def __init__(self, max_steps: int = 10, bilingual: bool = False, include_year: bool = False):
        super().__init__()
        self._call_count = 0
        self.max_steps = max_steps
        self.bilingual = bilingual
        self.include_year = include_year

    def _build_search_prompt(self) -> str:
        lang_instruction = "3. 根据问题语境按需选择中文和/或英文关键词搜索" if self.bilingual else "3. 使用精准的关键词搜索"
        year_instruction = ""
        if self.include_year:
            current = datetime.now(UTC).year
            year_instruction = f"4. 在关键词中包含年份信息（如 {current}、{current-1}），确保搜索结果的时效性"
        return SEARCH_PROMPT.format(
            current_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            lang_instruction=lang_instruction,
            year_instruction=year_instruction,
        )

    def _update_request(self, request: ModelRequest) -> ModelRequest:
        # 使用实例计数器代替 request.state.remaining_steps（该值不会递减）
        if self._call_count >= self.max_steps - 1:
            request = request.override(tools=[], system_message=SystemMessage(content=FINAL_PROMPT))
        else:
            request = request.override(
                system_message=SystemMessage(content=self._build_search_prompt())
            )
        self._call_count += 1
        return request

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._update_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._update_request(request))
