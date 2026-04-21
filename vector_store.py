"""
向量存储模块 (Vector Store Module)

本模块负责向量数据库的集成和文档嵌入处理：
1. 嵌入模型的封装，集成阿里云百炼 Embedding API
2. PGVector 向量数据库的连接和检索
3. 文档向量化存储和相似度检索

技术栈：
- PGVector: PostgreSQL 向量扩展，支持高效的相似度搜索
- LangChain: 统一的向量存储接口
- 阿里云百炼: 提供中文优化的嵌入模型

主要组件：
- BailianEmbeddings: 阿里云百炼嵌入模型封装类
- vector_store: PGVector 实例，用于文档存储和检索
- seed_documents(): 初始化示例数据函数
"""
import logging
from typing import List
import requests
from langchain_core.embeddings import Embeddings
from langchain_postgres.vectorstores import PGVector
from langchain_core.documents import Document
from config import settings

logger = logging.getLogger(__name__)

# 获取或重用应用内配置
BAILIAN_API_KEY = settings.OPENAI_API_KEY
BAILIAN_BASE_URL = settings.OPENAI_API_BASE

# LangChain-postgres 需要的连接串(使用 psycopg 3 标准协议)
# 指向我们 Docker 中的 PostgreSQL
def _pgvector_connection_string() -> str:
    connection = settings.DATABASE_URL
    if connection.startswith("postgresql://"):
        return connection.replace("postgresql://", "postgresql+psycopg://", 1)
    if connection.startswith("postgres://"):
        return connection.replace("postgres://", "postgresql+psycopg://", 1)
    return connection


CONNECTION_STRING = _pgvector_connection_string()
COLLECTION_NAME = settings.COLLECTION_NAME


class BailianEmbeddings(Embeddings):
    """阿里云百炼 Embedding 模型封装"""
    
    def __init__(self, api_key: str = None, base_url: str = None):
        """初始化嵌入模型
        
        Args:
            api_key: API 密钥，如果不提供则使用配置中的值
            base_url: API 基础URL，如果不提供则使用配置中的值
        """
        self.api_key = api_key or BAILIAN_API_KEY
        self.base_url = base_url or BAILIAN_BASE_URL
        self.model_name = "text-embedding-v3"  # 阿里云百炼的嵌入模型
        
    def embed_query(self, text: str) -> List[float]:
        """将单个文本转换为向量
        
        Args:
            text: 要嵌入的文本
            
        Returns:
            向量表示的列表
        """
        return self.embed_documents([text])[0]
        
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """将多个文本转换为向量
        
        Args:
            texts: 要嵌入的文本列表
            
        Returns:
            向量列表
        """
        embeddings = []
        for text in texts:
            # 调用阿里云百炼 API
            response = requests.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model_name,
                    "input": text,
                    "encoding_format": "float"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                embedding = data["data"][0]["embedding"]
                embeddings.append(embedding)
            else:
                logger.error(f"嵌入API调用失败: {response.status_code} - {response.text}")
                # 返回零向量作为降级处理
                embeddings.append([0.0] * 1024)  # 假设向量维度为1024
                
        return embeddings


# 创建全局向量存储实例
embeddings = BailianEmbeddings()
vector_store = PGVector(
    embeddings=embeddings,
    collection_name=COLLECTION_NAME,
    connection=CONNECTION_STRING,
    use_jsonb=True,
)


def seed_documents():
    """初始化示例文档数据
    
    用于测试和演示目的，向向量数据库添加一些示例文档。
    在生产环境中通常不需要此函数。
    """
    sample_docs = [
        Document(
            page_content="Ragent 是一个基于大语言模型的智能对话系统，支持知识库问答和多轮对话。",
            metadata={"source": "system", "type": "introduction"}
        ),
        Document(
            page_content="向量检索技术通过将文本转换为向量，并在向量空间中进行相似度计算来实现高效的文本搜索。",
            metadata={"source": "system", "type": "technology"}
        ),
        Document(
            page_content="RAG（Retrieval-Augmented Generation）技术结合了检索和生成的优势，能够提供更准确和相关的回答。",
            metadata={"source": "system", "type": "rag"}
        )
    ]
    
    try:
        # 添加文档到向量存储
        vector_store.add_documents(sample_docs)
        logger.info(f"成功添加 {len(sample_docs)} 个示例文档到向量存储")
    except Exception as e:
        logger.error(f"添加示例文档失败: {e}")


# 如果是开发环境，自动初始化示例数据
if getattr(settings, "ENVIRONMENT", "production") == "development":
    seed_documents()
