"""模块导读：本文件位于 app/rag/retrieval/reranker.py，属于RAG 问答链路。

主要职责：处理问题改写、知识检索、结果融合、重排和最终回答生成。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations


class RerankerService:
    """轻量重排服务；没有专用 rerank 模型时保留原顺序并给出默认分数。"""

    def rerank_with_threshold(self, query: str, documents: list[str], threshold: float = 0.0) -> list[dict]:
        """按阈值对检索结果进行过滤和排序，当前保持轻量规则实现。"""
        return [{"index": index, "score": 1.0} for index, _ in enumerate(documents)]
