"""模块导读：本文件位于 app/observability/trace/__init__.py，属于可观测性层。

主要职责：记录 Trace、Span 和运行过程，帮助回放 Agent 与 RAG 的执行路径。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from app.observability.trace.trace_collector import TraceCollector

# 进程内 Trace 收集器用于兼容工作流中的轻量链路记录。
trace_collector = TraceCollector(max_traces=1000)

