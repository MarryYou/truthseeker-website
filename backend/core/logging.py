"""基于 loguru 的统一日志模块，支持 Trace ID 链路追踪

在 Docker 环境下，所有日志写往 stderr（由 Docker 日志驱动收集），
不产生文件，以避免容器内日志膨胀。
"""

from __future__ import annotations
from contextvars import ContextVar
from loguru import logger as lg
import sys

# 核心追踪变量
# trace_id_var 代表 Session (Research) ID
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
# task_id_var 代表当前执行的具体 Task ID
task_id_var: ContextVar[str] = ContextVar("task_id", default="")
# mode_var 代表执行模式 (fast_react, etc.)
mode_var: ContextVar[str] = ContextVar("execution_mode", default="")
# 记录请求来源：internal (INT) 或 external (EXT)
source_var: ContextVar[str] = ContextVar("request_source", default="EXT")
# 进程标记：api / worker / unknown
process_var: ContextVar[str] = ContextVar("process", default="?")

lg.remove()

_CONSOLE_FMT = (
    "<green>{time:HH:mm:ss}</green> │ <level>{level: <8}</level> │ "
    "<blue>{extra[process]:<6}</blue> │ "
    "<cyan>{extra[session_id]:<8}</cyan>:<cyan>{extra[task_id]:<8}</cyan> │ "
    "<yellow>{extra[mode]:<12}</yellow> │ <magenta>{extra[source]:<3}</magenta> │ "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

# 仅添加 stderr 处理器（Docker 捕获为容器日志）
lg.add(sys.stderr, level="DEBUG", format=_CONSOLE_FMT, colorize=True, backtrace=True, diagnose=True)

# 污点（Patch）函数，为所有日志记录添加 session_id, task_id 和 source
def _patch_record(record):
    record["extra"].setdefault("session_id", trace_id_var.get() or "no-sess")
    record["extra"].setdefault("task_id", task_id_var.get() or "no-task")
    record["extra"].setdefault("mode", mode_var.get() or "none")
    record["extra"].setdefault("source", "INT" if source_var.get() == "internal" else "EXT")
    record["extra"].setdefault("process", process_var.get() or "?")

logger = lg.patch(_patch_record)

__all__ = ["logger", "trace_id_var", "task_id_var", "mode_var", "source_var", "process_var"]
