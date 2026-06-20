import asyncio
import pytest
from backend.core.logging import logger, trace_id_var, task_id_var

class LogCapture:
    def __init__(self):
        self.messages = []

    def write(self, message):
        self.messages.append(message)

def test_basic_logging():
    """测试基本日志打印（冒烟测试）"""
    logger.info("This is a basic test message")
    logger.error("This is an error test message")
    # 无异常即视为通过

@pytest.mark.asyncio
async def test_trace_id_isolation():
    """测试并发环境下，Hierarchical ID 的上下文隔离是否生效"""

    # 1. 准备捕获日志
    capture = LogCapture()
    # 临时添加一个 sink 到 logger 中
    # 注意：extra 中的 trace_id 已被重命名为 session_id
    handler_id = logger.add(capture.write, format="{extra[session_id]}:{extra[task_id]} - {message}")

    try:
        # 2. 定义一个会打印日志的异步任务
        async def worker(task_name: str, sess_id: str, task_id: str):
            # 设置 Session 和 Task ID
            token_sess = trace_id_var.set(sess_id)
            token_task = task_id_var.set(task_id)
            try:
                await asyncio.sleep(0.1)
                logger.info(f"Message from {task_name}")
            finally:
                trace_id_var.reset(token_sess)
                task_id_var.reset(token_task)

        # 3. 并发执行两个任务
        await asyncio.gather(
            worker("Worker-A", "SESS-A", "TASK-1"),
            worker("Worker-B", "SESS-B", "TASK-2")
        )

        # 4. 断言验证
        records = capture.messages
        assert len(records) >= 2
        
        # 验证内容中是否包含隔离的 ID
        assert any("SESS-A:TASK-1 - Message from Worker-A" in r for r in records)
        assert any("SESS-B:TASK-2 - Message from Worker-B" in r for r in records)
        
    finally:
        # 移除临时 handler
        logger.remove(handler_id)
