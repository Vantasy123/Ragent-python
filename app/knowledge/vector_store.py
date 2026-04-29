"""
向量存储模块。

本模块负责：
1. 封装百炼 Embedding 能力
2. 初始化并维护 Milvus collection
3. 提供与原有调用方式兼容的向量写入和检索接口
"""

from __future__ import annotations

import json
import logging
from threading import Lock
from typing import Any, List
from urllib.parse import urlparse

import requests
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

from app.core.config import settings

logger = logging.getLogger(__name__)

BAILIAN_API_KEY = settings.OPENAI_API_KEY
BAILIAN_BASE_URL = settings.OPENAI_API_BASE
COLLECTION_NAME = settings.COLLECTION_NAME
VECTOR_DIMENSION = settings.VECTOR_DIMENSION

_vector_store_instance = None
_vector_store_lock = Lock()


class BailianEmbeddings(Embeddings):
    """阿里云百炼 Embedding 模型封装。"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or BAILIAN_API_KEY
        self.base_url = base_url or BAILIAN_BASE_URL
        self.model_name = settings.EMBEDDING_MODEL

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            response = requests.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_name,
                    "input": text,
                    "encoding_format": "float",
                },
                timeout=60,
            )

            if response.status_code == 200:
                data = response.json()
                embeddings.append(data["data"][0]["embedding"])
                continue

            logger.error("嵌入 API 调用失败: %s - %s", response.status_code, response.text)
            embeddings.append([0.0] * VECTOR_DIMENSION)

        return embeddings


class MilvusVectorStoreAdapter:
    """
    Milvus 适配层。

    对外暴露的接口尽量保持稳定，
    这样摄取节点和检索链路可以少改代码。
    """

    def __init__(self, embeddings: Embeddings):
        self.embeddings = embeddings
        self.alias = "ragent_python_milvus"
        self.collection = self._init_collection()

    def _connect(self) -> None:
        if connections.has_connection(self.alias):
            return

        parsed = urlparse(settings.MILVUS_URI)
        host = parsed.hostname or "localhost"
        port = parsed.port or 19530

        # 统一在这里建立连接，后续所有读写都复用同一别名。
        connections.connect(
            alias=self.alias,
            host=host,
            port=port,
            token=settings.MILVUS_TOKEN or None,
        )

    def _init_collection(self) -> Collection:
        self._connect()

        if not utility.has_collection(COLLECTION_NAME, using=self.alias):
            logger.info("Milvus collection 不存在，开始创建: %s", COLLECTION_NAME)
            schema = CollectionSchema(
                fields=[
                    FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, is_primary=True, auto_id=False, max_length=128),
                    FieldSchema(name="kb_id", dtype=DataType.VARCHAR, max_length=128),
                    FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=128),
                    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                    FieldSchema(name="metadata", dtype=DataType.JSON),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=VECTOR_DIMENSION),
                ],
                description="Ragent Python 知识库向量集合",
            )
            collection = Collection(name=COLLECTION_NAME, schema=schema, using=self.alias)
            collection.create_index(
                field_name="embedding",
                index_params={"index_type": "AUTOINDEX", "metric_type": "COSINE", "params": {}},
            )
        else:
            collection = Collection(name=COLLECTION_NAME, using=self.alias)

        collection.load()
        return collection

    @staticmethod
    def _escape_expr_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def _build_chunk_row(self, doc: Document, chunk_id: str, vector: list[float]) -> dict[str, Any]:
        metadata = dict(doc.metadata or {})
        return {
            "chunk_id": chunk_id,
            "kb_id": str(metadata.get("kb_id") or ""),
            "doc_id": str(metadata.get("doc_id") or ""),
            "content": doc.page_content,
            "metadata": metadata,
            "embedding": vector,
        }

    def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> None:
        if not documents:
            return

        if ids and len(ids) != len(documents):
            raise ValueError("ids length must match documents length")

        vectors = self.embeddings.embed_documents([doc.page_content for doc in documents])
        rows = [
            self._build_chunk_row(doc, ids[index] if ids else doc.metadata.get("chunk_id", ""), vector)
            for index, (doc, vector) in enumerate(zip(documents, vectors, strict=False))
        ]

        # 先删后插，保证 chunk_id 幂等更新，避免重复主键写入失败。
        chunk_ids = [row["chunk_id"] for row in rows if row["chunk_id"]]
        if chunk_ids:
            self.delete_by_chunk_ids(chunk_ids)

        self.collection.insert(rows)
        self.collection.flush()

    def similarity_search_with_score(self, query: str, k: int = 4, filter: str | None = None) -> list[tuple[Document, float]]:
        query_vector = self.embeddings.embed_query(query)
        results = self.collection.search(
            data=[query_vector],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {}},
            limit=k,
            expr=filter,
            output_fields=["chunk_id", "kb_id", "doc_id", "content", "metadata"],
        )

        matches: list[tuple[Document, float]] = []
        for hit in results[0]:
            metadata = hit.entity.get("metadata") or {}
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {"raw_metadata": metadata}

            matches.append(
                (
                    Document(page_content=hit.entity.get("content") or "", metadata=metadata),
                    float(hit.distance),
                )
            )
        return matches

    def delete_by_chunk_ids(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        escaped = [f'"{self._escape_expr_value(chunk_id)}"' for chunk_id in chunk_ids if chunk_id]
        if not escaped:
            return
        expr = f"chunk_id in [{', '.join(escaped)}]"
        self.collection.delete(expr)
        self.collection.flush()

    def delete_by_doc_id(self, doc_id: str) -> None:
        if not doc_id:
            return
        expr = f'doc_id == "{self._escape_expr_value(doc_id)}"'
        self.collection.delete(expr)
        self.collection.flush()


embeddings = BailianEmbeddings()


def get_vector_store() -> MilvusVectorStoreAdapter:
    global _vector_store_instance
    if _vector_store_instance is None:
        with _vector_store_lock:
            if _vector_store_instance is None:
                _vector_store_instance = MilvusVectorStoreAdapter(embeddings=embeddings)
    return _vector_store_instance


class LazyVectorStore:
    """延迟代理，避免模块导入时立刻连接 Milvus。"""

    def __getattr__(self, name: str):
        return getattr(get_vector_store(), name)


vector_store = LazyVectorStore()


def seed_documents():
    """开发环境下写入少量示例数据。"""
    sample_docs = [
        Document(
            page_content="Ragent 是一个基于大语言模型的智能对话系统，支持知识库问答和多轮对话。",
            metadata={"source": "system", "type": "introduction", "kb_id": "system", "doc_id": "seed"},
        ),
        Document(
            page_content="向量检索技术通过将文本转换为向量，并在向量空间中进行相似度计算来实现高效的文本搜索。",
            metadata={"source": "system", "type": "technology", "kb_id": "system", "doc_id": "seed"},
        ),
        Document(
            page_content="RAG 技术结合了检索和生成的优势，能够提供更准确和相关的回答。",
            metadata={"source": "system", "type": "rag", "kb_id": "system", "doc_id": "seed"},
        ),
    ]

    try:
        vector_store.add_documents(sample_docs, ids=["seed_0", "seed_1", "seed_2"])
        logger.info("成功添加 %s 个示例文档到 Milvus", len(sample_docs))
    except Exception as exc:
        logger.error("添加示例文档失败: %s", exc)


if getattr(settings, "ENVIRONMENT", "production") == "development":
    seed_documents()
