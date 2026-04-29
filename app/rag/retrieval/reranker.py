"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations


class RerankerService:
    """轻量重排服务；没有专用 rerank 模型时保留原顺序并给出默认分数。"""

    def rerank_with_threshold(self, query: str, documents: list[str], threshold: float = 0.0) -> list[dict]:
        return [{"index": index, "score": 1.0} for index, _ in enumerate(documents)]
