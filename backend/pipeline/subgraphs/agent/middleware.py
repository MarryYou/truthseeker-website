"""TruthSeeker 研究 Agent 中间件

使用 LangChain create_agent 的 middleware hook 实现：
  - wrap_model_call：每次 LLM 调用前注入系统提示词，最后一步解除工具绑定
"""
from __future__ import annotations
from datetime import datetime, UTC
from typing import Awaitable, Callable
from langchain_core.messages import SystemMessage
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import ToolMessage, FunctionMessage


AGENT_SYSTEM_PROMPT = """你是 TruthSeeker AI 研究助理。你的回答必须紧贴用户【最新】提出的问题。

## 执行准则
1. **话题切换**：如果用户的问题转向了新领域（即便与历史对话有关），请立即转入新话题的研究，不要被历史回答的标题或排版所束缚。
2. **工具选择**：根据问题类型选择工具：
   - 常识、闲聊、问候 → 调用 `answer_directly`
   - 最新信息、对比、调研 → 调用 `search_web`
3. **停止条件**：信息收集充分后立即输出最终回答。不要复述历史回答的内容。
4. **输出格式**：简单问题用段落，调研类用规范 Markdown。每条事实必须紧跟引用 [来源名](URL)，文末附参考文献列表。
"""


FINAL_PROMPT = """你有足够的搜索结果了。请基于以下信息直接回答用户的问题。

## 问题
{query}

## 搜索结果
{search_data}

## 要求
1. 不要调用任何工具，直接输出最终回答
2. 使用规范的 Markdown 格式（## 章节 / 表格 / 列表）
3. 每条事实紧跟引用 [来源名](URL)
4. 不要复述对话历史"""


class ResearchAgentMiddleware(AgentMiddleware):
    """研究 Agent 中间件：控制工具绑定和提示词注入"""

    def __init__(self, execution_mode: str, query: str, max_steps: int = 10):
        super().__init__()
        self.execution_mode = execution_mode
        self.query = query
        self.max_steps = max_steps
        self._call_count = 0

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """每次 LLM 调用前注入系统提示词，最后一步解除工具绑定"""
        if self._call_count >= self.max_steps - 1:
            # 最后一步：解除工具绑定，用已有搜索结果生成最终报告
            # 🚨 修复隔离性：仅提取 ToolMessage 或包含搜索结果的消息，排除历史对话背景
            tool_outputs = []
            for m in reversed(request.messages or []):
                # 只收集本次任务中工具返回的真实数据
                if isinstance(m, (ToolMessage, FunctionMessage)):
                    if m.content and len(str(m.content)) > 20:
                        tool_outputs.append(str(m.content))
                # 如果遇到上一个 HumanMessage，说明已经回溯到了本次任务的起点，停止回溯
                elif hasattr(m, "type") and m.type == "human":
                    break
            
            search_data = "\n\n".join(reversed(tool_outputs))

            request = request.override(
                tools=[],
                system_message=SystemMessage(
                    content=FINAL_PROMPT.format(
                        query=self.query,
                        search_data=search_data[:8000],
                    ) if search_data else f"请直接回答：{self.query}"
                ),
            )
        else:
            current_date = datetime.now(UTC).strftime("%Y-%m-%d")
            request = request.override(
                system_message=SystemMessage(content=AGENT_SYSTEM_PROMPT + f"\n当前日期：{current_date}")
            )

        self._call_count += 1
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """异步版本：与 wrap_model_call 相同逻辑"""
        if self._call_count >= self.max_steps - 1:
            tool_outputs = []
            for m in reversed(request.messages or []):
                if isinstance(m, (ToolMessage, FunctionMessage)):
                    if m.content and len(str(m.content)) > 20:
                        tool_outputs.append(str(m.content))
                elif hasattr(m, "type") and m.type == "human":
                    break
            
            search_data = "\n\n".join(reversed(tool_outputs))
            request = request.override(
                tools=[],
                system_message=SystemMessage(
                    content=FINAL_PROMPT.format(query=self.query, search_data=search_data[:8000])
                    if search_data else f"请直接回答：{self.query}"
                ),
            )
        else:
            current_date = datetime.now(UTC).strftime("%Y-%m-%d")
            request = request.override(
                system_message=SystemMessage(content=AGENT_SYSTEM_PROMPT + f"\n当前日期：{current_date}")
            )

        self._call_count += 1
        return await handler(request)
