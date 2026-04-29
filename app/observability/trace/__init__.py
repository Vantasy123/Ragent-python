"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from app.observability.trace.trace_collector import TraceCollector

# 进程内 Trace 收集器用于兼容工作流中的轻量链路记录。
trace_collector = TraceCollector(max_traces=1000)

