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
