import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from langchain.agents.middleware import ModelRequest, ModelResponse
from backend.pipeline.subgraphs.agent.graph import build_agent
from backend.pipeline.subgraphs.agent.middleware import ResearchAgentMiddleware

def test_build_agent_creation():
    """测试 build_agent 是否成功创建包含对应工具和中间件的 Agent"""
    mock_llm = MagicMock()
    mock_raw_store = MagicMock()
    
    with patch("backend.pipeline.subgraphs.agent.graph.create_agent") as mock_create_agent:
        build_agent(
            llm=mock_llm,
            raw_store=mock_raw_store,
            tenant_id="tenant123",
            user_id="user456",
            research_id="research789",
            task_id="task000",
            preset_id="preset_default",
            execution_mode="research_pipeline",
            query="test query",
        )
        
        mock_create_agent.assert_called_once()
        kwargs = mock_create_agent.call_args[1]
        
        assert kwargs["model"] == mock_llm
        tools = kwargs["tools"]
        tool_names = [t.name for t in tools]
        assert "search_web" in tool_names
        assert "answer_directly" in tool_names
        assert "fetch_full_content" not in tool_names
        
        middlewares = kwargs["middleware"]
        assert len(middlewares) == 1
        assert isinstance(middlewares[0], ResearchAgentMiddleware)

    # 检查 expert_search 模式下是否有 fetch_full_content
    with patch("backend.pipeline.subgraphs.agent.graph.create_agent") as mock_create_agent:
        build_agent(
            llm=mock_llm,
            raw_store=mock_raw_store,
            tenant_id="tenant123",
            user_id="user456",
            research_id="research789",
            task_id="task000",
            preset_id="preset_default",
            execution_mode="expert_search",
            query="test query",
        )
        kwargs = mock_create_agent.call_args[1]
        tools = kwargs["tools"]
        tool_names = [t.name for t in tools]
        assert "fetch_full_content" in tool_names


@pytest.mark.asyncio
async def test_research_agent_middleware_remaining_steps():
    """测试 ResearchAgentMiddleware 的 wrap_model_call / awrap_model_call 在不同 steps 下的表现"""
    middleware = ResearchAgentMiddleware(execution_mode="research_pipeline", query="what is search?", max_steps=10)
    
    # 1. 模拟步骤充足的情况 (remaining_steps = 10)
    mock_llm = MagicMock()
    request_many_steps = ModelRequest(
        model=mock_llm,
        messages=[HumanMessage(content="Hello")],
        tools=[MagicMock()],
        state={}
    )
    
    def handler_sync(req: ModelRequest) -> ModelResponse:
        assert req.system_message is not None
        assert "TruthSeeker AI 研究助理" in req.system_message.content
        assert req.tools is not None and len(req.tools) > 0
        return MagicMock()
    
    middleware.wrap_model_call(request_many_steps, handler_sync)
    
    async def handler_async(req: ModelRequest) -> ModelResponse:
        assert req.system_message is not None
        assert "TruthSeeker AI 研究助理" in req.system_message.content
        assert req.tools is not None and len(req.tools) > 0
        return MagicMock()
        
    await middleware.awrap_model_call(request_many_steps, handler_async)

    # 2. 模拟最后一步情况 (remaining_steps = 1)
    middleware._call_count = 9
    request_last_step = ModelRequest(
        model=mock_llm,
        messages=[
            HumanMessage(content="Hello"),
            AIMessage(content="Let me search..."),
            HumanMessage(content="Here is a very long search result payload that is more than 50 characters to trigger texts selection.")
        ],
        tools=[MagicMock()],
        state={}
    )
    
    def handler_sync_last(req: ModelRequest) -> ModelResponse:
        assert req.system_message is not None
        assert "你有足够的搜索结果了" in req.system_message.content
        assert len(req.tools) == 0  # 应该解除工具绑定
        return MagicMock()
        
    middleware.wrap_model_call(request_last_step, handler_sync_last)

    async def handler_async_last(req: ModelRequest) -> ModelResponse:
        assert req.system_message is not None
        assert "你有足够的搜索结果了" in req.system_message.content
        assert len(req.tools) == 0  # 应该解除工具绑定
        return MagicMock()

    await middleware.awrap_model_call(request_last_step, handler_async_last)


@pytest.mark.asyncio
async def test_search_web_tool_execution():
    """测试 build_agent 中的 search_web 工具的实际执行与结果落库"""
    mock_llm = MagicMock()
    mock_raw_store = MagicMock()

    with patch("backend.pipeline.subgraphs.agent.graph.create_agent") as mock_create_agent:
        build_agent(
            llm=mock_llm,
            raw_store=mock_raw_store,
            tenant_id="tenant123",
            user_id="user456",
            research_id="research789",
            task_id="task000",
            preset_id="preset_default",
            execution_mode="research_pipeline",
            query="test query",
        )
        kwargs = mock_create_agent.call_args[1]
        tools = kwargs["tools"]
        
        search_web_tool = None
        for t in tools:
            if t.name == "search_web":
                search_web_tool = t
                break
                
        assert search_web_tool is not None
        
        mock_search_results = [{"title": "Test Result Title", "url": "https://test.com", "snippet": "Test snippet data"}]
        
        with patch("backend.pipeline.subgraphs.agent.graph.SearchOrchestrator") as mock_orch_cls, \
             patch("backend.pipeline.subgraphs.agent.graph.ResearchStore") as mock_store_cls:
             
            mock_orch = mock_orch_cls.return_value
            mock_orch.search = AsyncMock(return_value=mock_search_results)
            
            mock_store = mock_store_cls.return_value
            mock_store.save_search_results = AsyncMock()
            
            # 调用工具
            result = await search_web_tool.ainvoke({"query": "AI research"})
            
            assert "Test Result Title" in result
            assert "https://test.com" in result
            assert "Test snippet data" in result
            
            # 验证 ResearchStore.save_search_results 被调用
            mock_store.save_search_results.assert_called_once_with("AI research", mock_search_results)


