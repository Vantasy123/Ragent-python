"""模块导读：本文件位于 app/knowledge/service.py，属于知识库基础层。

主要职责：连接向量库和知识分块数据，为 RAG 与工具调用提供检索能力。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from app.services.knowledge_service import KnowledgeService

__all__ = ["KnowledgeService"]
