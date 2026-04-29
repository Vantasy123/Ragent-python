"""
查询拆分器模块 (Query Splitter Module)

本模块实现了复杂查询的智能拆分功能，将多意图或复杂问题分解为多个子问题。
通过 LLM 分析查询意图，生成相关子问题列表，提高检索准确性和答案完整性。

主要功能：
1. 查询分析：识别复杂查询中的多个意图
2. 子问题生成：将复杂问题拆分为多个简单子问题
3. 意图识别：区分事实性问题、比较性问题、多步骤问题等
4. 答案融合：为后续答案合并提供基础

核心组件：
- QuerySplitter: 主要的查询拆分类
- SubQuestions: 子问题数据结构定义
- LLM 驱动：使用 ChatGPT 进行智能拆分

拆分策略：
1. 问题分类：判断是否需要拆分
2. 意图分析：识别问题中的多个方面
3. 子问题生成：创建相关且独立的子问题
4. 质量控制：确保子问题数量和相关性

使用场景：
- 多意图问题："Python 的优势和学习资源"
- 比较问题："比较 Vue 和 React 的差异"
- 步骤问题："如何部署和监控 Web 应用"
- 综合问题："机器学习的算法和应用场景"

技术特性：
- 智能判断：自动识别是否需要拆分
- 数量控制：限制子问题数量避免过度拆分
- 质量保证：确保子问题相关性和独立性
- 错误处理：降级策略保证服务可用性
"""
"""
查询拆分器
将复杂问题拆分为多个子问题，分别检索后融合答案
"""
import logging
from typing import List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from app.core.config import settings

logger = logging.getLogger(__name__)


class SubQuestions(BaseModel):
    """子问题结构"""
    questions: List[str] = Field(
        description="拆分后的子问题列表",
        min_items=1,
        max_items=5
    )


class QuerySplitter:
    """查询拆分器"""
    
    def __init__(self):
        """初始化查询拆分器"""
        self.llm = ChatOpenAI(
            model=settings.CHAT_MODEL,
            temperature=0.0,
            streaming=False
        )
        
        self.split_prompt = """你是一个问题分解专家。请判断用户的问题是否需要拆分为多个子问题。

规则：
1. 如果问题是简单的单一问题，返回原始问题
2. 如果问题包含多个方面或需要多角度分析，拆分为 2-5 个子问题
3. 每个子问题应该是独立的、具体的
4. 子问题应该覆盖原问题的所有关键方面

示例：
- "公司的报销规定和出差政策是什么？" 
  -> ["公司的报销规定是什么？", "公司的出差政策是什么？"]
  
- "Python和Java有什么区别？"
  -> ["Python的主要特点是什么？", "Java的主要特点是什么？", "Python和Java在性能上有什么区别？", "Python和Java在应用场景上有什么不同？"]

用户问题：
{question}

请返回 JSON 格式的子问题列表。"""
    
    def split(self, question: str) -> List[str]:
        """
        拆分查询
        
        Args:
            question: 用户原始问题
            
        Returns:
            子问题列表
        """
        try:
            # 使用结构化输出
            llm_with_structured_output = self.llm.with_structured_output(SubQuestions)
            
            prompt = self.split_prompt.format(question=question)
            result = llm_with_structured_output.invoke([HumanMessage(content=prompt)])
            
            sub_questions = result.questions
            
            logger.info(f"Query split: '{question[:50]}...' -> {len(sub_questions)} sub-questions")
            
            return sub_questions
            
        except Exception as e:
            logger.error(f"Query splitting failed: {str(e)}, returning original query")
            return [question]
    
    def should_split(self, question: str) -> bool:
        """
        判断是否需要拆分
        
        Args:
            question: 用户问题
            
        Returns:
            是否需要拆分
        """
        # 简单启发式判断
        # 1. 包含多个问号
        if question.count("?") + question.count("？") > 1:
            return True
        
        # 2. 包含连接词（和、与、以及、区别、对比等）
        split_keywords = ["和", "与", "以及", "区别", "对比", "比较", "vs", "versus"]
        if any(keyword in question for keyword in split_keywords):
            return True
        
        # 3. 问题过长
        if len(question) > 100:
            return True
        
        return False



