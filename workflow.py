"""
工作流程模块 (Workflow Module)

本模块定义了 Ragent AI 代理的核心工作流程引擎，使用 LangGraph 构建的状态图来管理
多步骤的对话处理流程。

主要功能：
1. 意图识别：分析用户输入，判断是否为知识搜索、行动调用或闲聊
2. 查询优化：对用户查询进行改写，考虑对话历史
3. 知识检索：从多渠道检索相关知识块，并使用重排器优化排序
4. 响应生成：根据检索到的知识为用户生成回答
5. 工具调用：处理用户需要的特定工具调用请求

工作流程流程图：
START → intent_analyzer_node → (条件路由)
  ├─ KNOWLEDGE_SEARCH → query_rewrite_node → knowledge_search_node → END
  ├─ ACTION_CALL → action_call_node → END
  └─ CASUAL_CHAT → casual_chat_node → END
"""

from __future__ import annotations

import logging  # 日志模块，用于记录代码执行过程中的各种信息
import time  # 时间模块，用于计算操作耗时
from typing import Annotated, Literal  # 类型提示工具

from langchain_core.messages import BaseMessage, HumanMessage  # LangChain 消息类型
from langchain_openai import ChatOpenAI  # OpenAI 的 ChatGPT 模型封装
from langgraph.graph import END, START, StateGraph  # LangGraph 状态图构建工具
from langgraph.graph.message import add_messages  # 消息聚合函数
from pydantic import BaseModel, Field  # 数据模型和字段验证框架
from typing_extensions import TypedDict  # 类型字典，用于定义结构化状态

# 项目内部模块导入
from database import SessionLocal  # 数据库会话工厂
from memory.session_manager import SessionManager  # 会话管理器，处理对话历史
from mcp.tool_registry import ToolRegistry  # 工具注册表，管理可用的工具
from model.health_checker import HealthChecker  # 模型健康检查器
from model.model_router import ModelRouter  # 模型路由器，管理多个 LLM 模型的选择和降级
from rag.query.query_rewriter import QueryRewriter  # 查询改写器，优化查询质量
from rag.query.query_splitter import QuerySplitter  # 查询分割器（定义但未使用）
from rag.retrieval.multi_channel_retriever import MultiChannelRetriever  # 多渠道检索器
from rag.retrieval.reranker import RerankerService  # 重排服务，对检索结果重新排序
from services.settings_service import get_runtime_settings  # 获取运行时配置
from trace.trace_collector import TraceStatus  # 追踪状态枚举

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)

# ============================================================================
# 核心组件初始化
# ============================================================================

# 模型路由器：管理多个 LLM 模型，处理模型选择和故障转移
model_router = ModelRouter()

# 健康检查器：监控模型可用性和性能指标
health_checker = HealthChecker(model_router)

# 工具注册表：存储所有可用的工具/插件，供代理调用
tool_registry = ToolRegistry()

# 查询改写器：使用 LLM 基于对话历史改写用户查询，提高检索准确率
query_rewriter = QueryRewriter()

# 查询分割器：将复杂查询分解为多个子查询（此版本中未使用）
query_splitter = QuerySplitter()

# 重排服务：使用语义模型对检索结果重新排序，提高相关性
reranker = RerankerService()

# 多渠道检索器：从多个数据源（向量库、全文搜索等）检索相关文档
multi_channel_retriever = MultiChannelRetriever()



# ============================================================================
# 主 LLM 初始化函数
# ============================================================================

def build_primary_llm(streaming: bool = True) -> ChatOpenAI:
    """
    构建主要的语言模型实例。

    此函数从模型路由器获取当前可用的最佳模型，并使用运行时配置（如温度参数）
    创建一个 ChatOpenAI 实例。

    参数：
        streaming (bool): 是否启用流式响应。默认为 True，允许实时逐字输出响应。
                         在需要快速响应的场景（如意图分析）中可设置为 False。

    返回：
        ChatOpenAI: 配置完整的 LLM 实例，可直接调用 ainvoke() 方法进行异步推理。

    异常：
        RuntimeError: 当所有模型不可用时抛出。

    示例：
        llm = build_primary_llm(streaming=False)  # 用于结构化输出
        response = await llm.ainvoke("Hello")
    """
    # 从模型路由器获取当前最佳可用模型（考虑故障、负载等因素）
    current_model = model_router.get_available_model()
    if not current_model:
        raise RuntimeError("No available models")
    
    # 获取运行时配置，包括温度、历史轮数保留等参数
    runtime_settings = get_runtime_settings()
    
    # 使用模型信息和运行时配置创建 ChatOpenAI 实例
    return ChatOpenAI(
        model=current_model.model_name,  # 模型名称，如 "gpt-4"
        temperature=runtime_settings.temperature,  # 控制生成的随机性（0-1，值越低越确定性）
        openai_api_key=current_model.api_key,  # API 密钥
        openai_api_base=current_model.api_base,  # API 基础 URL（支持自定义端点）
        streaming=streaming,  # 是否流式返回
    )


# 创建全局 LLM 实例，用于整个工作流程
# 注意：这是在模块加载时创建的，如果需要动态更新模型，需要调用 build_primary_llm()
llm = build_primary_llm()



# ============================================================================
# 数据模型定义
# ============================================================================

class AgentState(TypedDict):
    """
    代理工作流程的状态字典。

    LangGraph 中的状态用于在各个节点间传递数据。状态中的每个字段都会被保留
    并在节点间流转，支持节点对状态的读写和更新。

    属性：
        messages (list[BaseMessage]): 对话消息列表，包含 HumanMessage 和 AIMessage。
                                    使用 add_messages 聚合函数，新消息会被追加到列表。
        
        intent_type (str): 识别出的用户意图类型，值为以下之一：
                         - "CASUAL_CHAT": 闲聊，无需知识检索
                         - "KNOWLEDGE_SEARCH": 知识搜索，需要检索文档
                         - "ACTION_CALL": 行动调用，需要调用工具/API
        
        session_id (str): 会话 ID，用于跟踪同一用户的多轮对话。
                         帮助检索该会话的历史消息和上下文。
        
        retrieved_chunks (list): 从知识库检索到的文档块列表。
                               每个块包含内容、来源、相关性评分等信息。
        
        rewritten_query (str): 查询改写器输出的优化后查询。
                              相比原始查询更清晰、更准确地表达用户意图。
        
        trace_id (str): 追踪 ID，用于关联本次请求的所有操作日志和 span，便于性能分析。
    """
    messages: Annotated[list[BaseMessage], add_messages]
    intent_type: str
    session_id: str
    retrieved_chunks: list
    rewritten_query: str
    trace_id: str


class Intent(BaseModel):
    """
    意图分析模型。

    使用 Pydantic 定义结构化输出模式。通过 LLM 的 with_structured_output() 方法，
    确保 LLM 输出严格符合这个模式（通过 JSON Schema 或函数调用等方式）。

    属性：
        intent_name (Literal): 识别出的意图类型，使用字面量类型确保只能取特定值：
            - "CASUAL_CHAT": 用户进行日常闲聊，如问候、天气等，不需要知识库
            - "KNOWLEDGE_SEARCH": 用户查询企业知识库，如产品介绍、技术文档等
            - "ACTION_CALL": 用户请求执行特定动作，如创建工单、生成报告等
    """
    intent_name: Literal["CASUAL_CHAT", "KNOWLEDGE_SEARCH", "ACTION_CALL"] = Field(
        description="Identify whether the user wants casual chat, knowledge search, or a tool/action call."
    )



# ============================================================================
# 工作流程节点（Workflow Nodes）
# 每个节点是一个异步函数，接收当前状态，返回状态更新字典
# ============================================================================

async def intent_analyzer_node(state: AgentState) -> dict:
    """
    意图分析节点。

    工作流程的第一步。通过调用 LLM 分析用户最后一条消息，判断用户的真实意图是什么。
    结果决定后续走哪个分支（知识搜索、行动调用或闲聊）。

    处理流程：
    1. 从状态获取追踪上下文（用于记录性能指标）
    2. 提取用户最后一条消息的内容
    3. 使用结构化输出强制 LLM 返回符合 Intent 模型的 JSON
    4. 记录意图分析的耗时和结果到追踪系统

    参数：
        state (AgentState): 当前工作流程状态

    返回：
        dict: 包含 intent_type 的状态更新字典

    性能特性：
        - 使用 streaming=False 以获得更快的响应
        - 记录到追踪系统供性能分析
        - 异常时默认返回 "CASUAL_CHAT" 作为降级选项
    """
    from api.traces import trace_collector  # 导入追踪收集器（延迟导入避免循环依赖）

    # 获取本次请求的追踪上下文，如果存在则创建一个 span 记录此操作
    trace_ctx = trace_collector.get_trace(state.get("trace_id"))
    span = trace_ctx.create_span("intent_analysis") if trace_ctx else None
    start_time = time.time()  # 记录开始时间，用于计算耗时

    try:
        # 获取消息列表并提取最后一条用户消息
        messages = state.get("messages", [])
        last_user_input = messages[-1].content

        # 使用 with_structured_output() 强制 LLM 返回 Intent 类型的结构化数据
        # 注意：需要 streaming=False 以支持结构化输出
        analyzer = build_primary_llm(streaming=False).with_structured_output(Intent)
        response = await analyzer.ainvoke(f"用户说：{last_user_input}。请分析意图归属。")
        
        # 提取意图，如果响应为空则默认为闲聊
        intent_val = response.intent_name if response else "CASUAL_CHAT"
        
        # 记录完成，包含意图类型和耗时（毫秒）
        if span:
            span.complete(metadata={
                "intent": intent_val,
                "elapsed_ms": round((time.time() - start_time) * 1000, 2)
            })
        
        return {"intent_type": intent_val}
    
    except Exception as exc:
        logger.error("Intent analysis failed: %s", exc)
        # 错误情况下记录异常到追踪系统
        if span:
            span.complete(TraceStatus.ERROR, error=str(exc))
        # 降级处理：出错时默认使用闲聊路径
        return {"intent_type": "CASUAL_CHAT"}



async def query_rewrite_node(state: AgentState) -> dict:
    """
    查询改写节点。

    当意图识别为 "KNOWLEDGE_SEARCH" 时调用。通过 LLM 基于对话历史改写用户查询，
    提高后续检索的准确性。例如：
    - 用户说："它怎么样？" → 改写为："产品 X 的性能和使用体验怎么样？"
    - 缩写和口语化表达 → 标准化、清晰的查询

    处理流程：
    1. 从数据库获取该会话的历史对话（最近 N 轮）
    2. 将原始查询、历史对话、当前消息发送给 LLM
    3. LLM 输出优化后的查询表述
    4. 将改写结果存储到状态中供后续节点使用

    参数：
        state (AgentState): 当前工作流程状态

    返回：
        dict: 包含 rewritten_query 的状态更新字典

    数据库交互：
        - 打开数据库会话获取历史对话
        - 获取后立即关闭连接（使用 try-finally 确保清理）

    配置参数：
        - history_keep_turns: 从运行时设置获取，决定检索多少轮历史对话
    """
    from api.traces import trace_collector

    trace_ctx = trace_collector.get_trace(state.get("trace_id"))
    span = trace_ctx.create_span("query_rewrite") if trace_ctx else None
    start_time = time.time()

    try:
        # 提取用户的原始查询
        messages = state.get("messages", [])
        original_query = messages[-1].content
        session_id = state.get("session_id")
        runtime_settings = get_runtime_settings()

        # 从数据库获取该会话的历史对话，用于提供上下文
        db_session = SessionLocal()
        try:
            session_mgr = SessionManager(db_session)
            # 获取最近 N 轮对话（N 由运行时设置决定）
            chat_history = session_mgr.get_chat_history(
                session_id, 
                max_rounds=runtime_settings.history_keep_turns
            )
            # 调用查询改写器，将原始查询改写为更清晰的版本
            rewritten_query = query_rewriter.rewrite(original_query, chat_history)
        finally:
            # 确保数据库连接被关闭，即使发生异常也会执行
            db_session.close()

        # 记录改写前后的查询到追踪系统
        if span:
            span.complete(metadata={
                "original_query": original_query[:50],  # 只记录前 50 个字符
                "rewritten_query": rewritten_query[:50],
                "elapsed_ms": round((time.time() - start_time) * 1000, 2),
            })
        
        return {"rewritten_query": rewritten_query}
    
    except Exception as exc:
        logger.error("Query rewrite failed: %s", exc)
        if span:
            span.complete(TraceStatus.ERROR, error=str(exc))
        # 异常情况下，返回原始查询作为降级
        return {"rewritten_query": state["messages"][-1].content}



async def knowledge_search_node(state: AgentState) -> dict:
    """
    知识搜索节点。

    执行完整的 RAG（检索增强生成）流程，基于改写后的查询从知识库检索相关文档，
    进行重排优化，然后使用 LLM 结合检索结果为用户生成回答。

    工作流程：
    1. 多渠道检索：从向量库、全文搜索等多个渠道检索相关文档块
    2. 初步过滤：获取 top_k 个候选块
    3. 重排（Reranking）：使用语义相似度模型对结果重排，过滤低相关性块
    4. 上下文构建：将重排后的块组织成提示词中的上下文
    5. LLM 生成：调用 LLM 基于上下文和查询生成回答
    6. 异常处理：任何步骤失败时使用降级策略

    参数：
        state (AgentState): 当前工作流程状态

    返回：
        dict: 包含 messages（AI 响应）和 retrieved_chunks（检索的文档块）的状态更新

    多个追踪 Span：
        - knowledge_retrieval: 总的知识检索流程
        - multi_channel_retrieval: 多渠道检索的耗时
        - reranking: 重排的耗时和过滤效果
        - llm_generation: LLM 生成的耗时

    关键指标：
        - 检索块数量：从检索到重排前后的数量对比
        - 重排质量：通过相关性评分衡量
    """
    from api.traces import trace_collector

    trace_ctx = trace_collector.get_trace(state.get("trace_id"))
    span = trace_ctx.create_span("knowledge_retrieval") if trace_ctx else None
    start_time = time.time()

    try:
        # 步骤 1: 多渠道检索
        # ============================================================================
        # 获取改写后的查询，如果不存在则使用原始查询
        query = state.get("rewritten_query") or state["messages"][-1].content
        runtime_settings = get_runtime_settings()

        # 创建检索 span 记录多渠道检索过程
        retrieval_span = trace_ctx.create_span("multi_channel_retrieval") if trace_ctx else None
        
        # 从多个渠道（向量、BM25、关键字等）检索相关文档块
        retrieved_chunks = multi_channel_retriever.retrieve(
            query=query, 
            top_k=runtime_settings.top_k  # top_k 通常为 10-20
        )
        
        # 记录检索结果的统计信息
        if retrieval_span:
            retrieval_span.complete(metadata={
                "chunk_count": len(retrieved_chunks),
                # 提取检索结果来自的数据源类型
                "channels": list({chunk.channel for chunk in retrieved_chunks})
            })

        # 步骤 2: 重排优化
        # ============================================================================
        rerank_span = trace_ctx.create_span("reranking") if trace_ctx else None
        
        # 将文档块的内容提取出来用于重排
        documents = [chunk.content for chunk in retrieved_chunks]
        
        # 使用重排器对结果重新排序，并根据相关性阈值过滤低质量结果
        reranked_results = reranker.rerank_with_threshold(query, documents)

        # 步骤 3: 构建最终的文档块列表（包含重排后的相关性评分）
        final_chunks = []
        for result in reranked_results:
            idx = result["index"]  # 原始检索结果中的索引
            if idx < len(retrieved_chunks):
                chunk = retrieved_chunks[idx]
                chunk.score = result["score"]  # 添加重排后的相关性评分
                final_chunks.append(chunk)

        # 记录重排前后的数量对比
        if rerank_span:
            rerank_span.complete(metadata={
                "before_count": len(documents),
                "after_count": len(final_chunks)
            })

        # 步骤 4: 构建提示词上下文
        # ============================================================================
        # 只使用排名前 5 的块构建上下文（控制上下文长度）
        context_text = "\n\n".join(
            f"[{index + 1}] {chunk.content}" 
            for index, chunk in enumerate(final_chunks[:5])
        )
        
        # 构建发送给 LLM 的完整提示词
        prompt = (
            "请根据以下企业私有知识为用户解答。如果知识与问题无关，请说明你不知道。\n\n"
            f"相关知识：\n{context_text}\n\n"
            f"问题：{query}\n\n"
            "请给出准确、简洁的回答。"
        )

        # 步骤 5: LLM 生成回答
        # ============================================================================
        generation_span = trace_ctx.create_span("llm_generation") if trace_ctx else None
        
        # 使用带故障转移的 LLM 调用生成回答
        response = await _generate_with_fallback(prompt)
        
        if generation_span:
            generation_span.complete(metadata={
                "response_length": len(response.content)
            })

        # 步骤 6: 完成整个知识搜索流程的追踪
        if span:
            span.complete(metadata={
                "retrieved_count": len(retrieved_chunks),
                "final_count": len(final_chunks),
                "elapsed_ms": round((time.time() - start_time) * 1000, 2),
            })

        # 返回状态更新：AI 消息和检索结果
        return {
            "messages": [response],
            "retrieved_chunks": [chunk.to_dict() for chunk in final_chunks],
        }
    
    except Exception as exc:
        logger.error("Knowledge search failed: %s", exc)
        if span:
            span.complete(TraceStatus.ERROR, error=str(exc))
        # 异常降级：不使用知识，直接基于原始查询生成回答
        fallback_response = await _generate_with_fallback(state["messages"])
        return {"messages": [fallback_response]}



async def action_call_node(state: AgentState) -> dict:
    """
    行动调用节点。

    当意图识别为 "ACTION_CALL" 时调用。处理用户请求特定工具或 API 调用的场景。
    例如：创建工单、生成报告、修改配置等。

    工作流程：
    1. 收集所有可用工具的列表和描述
    2. 构建工具选择提示词
    3. 使用 LLM 选择合适的工具和参数
    4. 返回 LLM 的选择结果给用户

    注意：此版本中工具链路还未完全接通，所以只返回 LLM 的选择建议供用户确认。
    完整实现应该在这里实际调用选定的工具。

    参数：
        state (AgentState): 当前工作流程状态

    返回：
        dict: 包含 messages（工具选择结果）的状态更新

    工具注册表：
        - tool_registry.list_tools(): 返回所有可用工具的列表
        - 每个工具包含 name 和 description 字段
    """
    from api.traces import trace_collector

    trace_ctx = trace_collector.get_trace(state.get("trace_id"))
    span = trace_ctx.create_span("action_call") if trace_ctx else None
    start_time = time.time()

    try:
        # 获取用户的原始请求
        messages = state.get("messages", [])
        user_query = messages[-1].content
        
        # 从工具注册表获取所有可用工具，格式化为可读的文本
        tool_listing = "\n".join([
            f'- {tool["name"]}: {tool["description"]}' 
            for tool in tool_registry.list_tools()
        ])
        
        # 构建发送给 LLM 的提示词，让 LLM 选择合适的工具
        tool_selection_prompt = (
            f"用户问题：{user_query}\n\n"
            f"可用工具：\n{tool_listing}\n\n"
            '请以 JSON 返回要调用的工具与参数，格式如 {"tool_name":"xxx","params":{"k":"v"}}。'
            '如果不需要工具，返回 {"tool_name": null}。'
        )
        
        # 调用 LLM 获取工具选择（不使用流式输出以获得完整 JSON）
        selection_response = await build_primary_llm(streaming=False).ainvoke(
            [HumanMessage(content=tool_selection_prompt)]
        )
        
        # 返回工具选择建议给用户
        # TODO: 完整实现应该在此处执行工具调用而非只返回建议
        response_content = f"工具链路暂未完全接通，模型选择结果如下：\n\n{selection_response.content}"
        response = HumanMessage(content=response_content)

        # 记录行动调用的耗时
        if span:
            span.complete(metadata={
                "elapsed_ms": round((time.time() - start_time) * 1000, 2)
            })
        
        return {"messages": [response]}
    
    except Exception as exc:
        logger.error("Action call failed: %s", exc)
        if span:
            span.complete(TraceStatus.ERROR, error=str(exc))
        # 异常降级：使用闲聊回答
        fallback_response = await _generate_with_fallback(state["messages"])
        return {"messages": [fallback_response]}



async def casual_chat_node(state: AgentState) -> dict:
    """
    闲聊节点。

    当意图识别为 "CASUAL_CHAT" 时调用。处理不需要知识库检索或工具调用的普通对话。
    LLM 基于对话历史和用户输入进行自由生成回答。

    工作流程：
    1. 直接调用 LLM 基于消息历史进行回答
    2. 使用故障转移机制处理模型可用性问题
    3. 记录响应耗时到追踪系统

    参数：
        state (AgentState): 当前工作流程状态

    返回：
        dict: 包含 messages（LLM 生成的回答）的状态更新

    降级策略：
        - 异常时返回友好的错误提示消息
    """
    from api.traces import trace_collector

    trace_ctx = trace_collector.get_trace(state.get("trace_id"))
    span = trace_ctx.create_span("casual_chat") if trace_ctx else None
    start_time = time.time()

    try:
        # 直接传递消息历史给 LLM 进行回答
        response = await _generate_with_fallback(state.get("messages", []))
        
        if span:
            span.complete(metadata={
                "elapsed_ms": round((time.time() - start_time) * 1000, 2)
            })
        
        return {"messages": [response]}
    
    except Exception as exc:
        logger.error("Casual chat failed: %s", exc)
        if span:
            span.complete(TraceStatus.ERROR, error=str(exc))
        # 返回友好的错误提示
        return {"messages": [HumanMessage(content="抱歉，我遇到了一些问题，请稍后再试。")]}



# ============================================================================
# 辅助函数（Helper Functions）
# ============================================================================

async def _generate_with_fallback(messages_or_prompt):
    """
    使用故障转移机制的 LLM 文本生成函数。

    系统中可能配置了多个 LLM 模型（如主模型、备模型等），以提高可用性。
    当某个模型出现故障时，此函数会自动尝试其他可用模型，实现无缝降级。

    工作流程：
    1. 从模型路由器获取当前最优模型
    2. 尝试使用该模型生成响应
    3. 如果成功：记录成功状态并返回结果
    4. 如果失败：
       - 记录该模型的故障状态
       - 从模型路由器请求备用模型
       - 重复尝试直到成功或所有模型都已尝试

    参数：
        messages_or_prompt: 可以是以下之一：
            - str: 单一的提示词字符串，会被包装为 HumanMessage
            - list: 完整的消息历史（LangChain BaseMessage 列表）

    返回：
        BaseMessage: LLM 生成的响应消息

    异常：
        RuntimeError: 当没有可用的模型或所有模型都失败时抛出

    模型路由器的职责：
        - record_request(model, success): 记录请求结果，用于评估模型健康状态
        - get_fallback_model(current_model): 返回下一个可尝试的模型
    """
    # 获取当前最可用的模型
    current_model = model_router.get_available_model()
    if not current_model:
        raise RuntimeError("No available models for generation")

    last_error = None  # 记录最后一个错误以便调试

    # 持续尝试直到成功或用尽所有模型
    while current_model:
        try:
            # 获取运行时配置
            runtime_settings = get_runtime_settings()
            
            # 为当前模型创建 LLM 实例
            temp_llm = ChatOpenAI(
                model=current_model.model_name,
                temperature=runtime_settings.temperature,
                openai_api_key=current_model.api_key,
                openai_api_base=current_model.api_base,
                streaming=False,  # 生成函数中不使用流式
            )
            
            # 根据输入类型进行 LLM 调用
            if isinstance(messages_or_prompt, str):
                # 如果是字符串提示词，包装为 HumanMessage
                response = await temp_llm.ainvoke([HumanMessage(content=messages_or_prompt)])
            else:
                # 如果是消息列表，直接传递
                response = await temp_llm.ainvoke(messages_or_prompt)
            
            # 成功！记录成功状态（用于模型路由器的评分）
            model_router.record_request(current_model, success=True)
            return response
        
        except Exception as exc:
            # 记录这次失败
            last_error = exc
            logger.warning("Model %s failed: %s", current_model.name, exc)
            
            # 向模型路由器报告失败（降低该模型的评分）
            model_router.record_request(current_model, success=False)
            
            # 尝试获取备用模型
            current_model = model_router.get_fallback_model(current_model)

    # 所有模型都已尝试且全部失败
    logger.error("All models failed. Last error: %s", last_error)
    raise last_error


def route_intent(state: AgentState) -> str:
    """
    条件路由函数。

    根据意图分析的结果决定工作流程应该转向哪个节点。
    这个函数在 LangGraph 中作为条件路由的目标。

    工作流程：
    - KNOWLEDGE_SEARCH → query_rewrite_node（知识搜索路径）
    - ACTION_CALL → action_call_node（工具调用路径）
    - 其他（包括默认值） → casual_chat_node（闲聊路径）

    参数：
        state (AgentState): 包含 intent_type 的当前状态

    返回：
        str: 下一个要执行的节点名称
    """
    intent = state.get("intent_type", "CASUAL_CHAT")
    if intent == "KNOWLEDGE_SEARCH":
        return "query_rewrite_node"
    if intent == "ACTION_CALL":
        return "action_call_node"
    return "casual_chat_node"


# ============================================================================
# LangGraph 工作流程构建
# ============================================================================
# 
# 工作流程图（ASCII 表示）：
#
#        START
#          │
#          ▼
#   intent_analyzer_node (分析用户意图)
#          │
#          │ (条件路由)
#    ┌─────┼─────┐
#    │     │     │
#    ▼     ▼     ▼
#   query  action casual
#   rewrite call  chat
#   node   node  node
#    │     │     │
#    ▼     │     │
#   knowledge │   │
#   search    │   │
#   node      │   │
#    │        │   │
#    └───┬────┘   │
#        │        │
#        └────┬───┘
#             ▼
#            END
#

# 创建状态图实例，指定状态类型
workflow = StateGraph(AgentState)

# 添加工作流程节点（共 5 个节点）
workflow.add_node("intent_analyzer_node", intent_analyzer_node)
workflow.add_node("query_rewrite_node", query_rewrite_node)
workflow.add_node("casual_chat_node", casual_chat_node)
workflow.add_node("knowledge_search_node", knowledge_search_node)
workflow.add_node("action_call_node", action_call_node)

# 添加边（连接）：从 START 开始执行 intent_analyzer_node
workflow.add_edge(START, "intent_analyzer_node")

# 添加条件边：根据 intent_analyzer_node 的输出（intent_type）决定路由
workflow.add_conditional_edges(
    "intent_analyzer_node",  # 源节点
    route_intent,            # 路由函数，返回下一个节点名称
    {
        # 映射：路由函数返回值 → 对应的目标节点
        "casual_chat_node": "casual_chat_node",
        "query_rewrite_node": "query_rewrite_node",
        "action_call_node": "action_call_node",
    },
)

# 添加边：查询改写后进入知识搜索节点
workflow.add_edge("query_rewrite_node", "knowledge_search_node")

# 添加边：各个最终节点都导向 END
workflow.add_edge("casual_chat_node", END)
workflow.add_edge("knowledge_search_node", END)
workflow.add_edge("action_call_node", END)

# 编译工作流程为可执行的图
# compile() 会生成一个 RunnableGraph 实例，可直接调用 ainvoke() 执行
app_graph = workflow.compile()

# 使用示例：
# ────────────────────────────────────────────────────────────────────────
# from workflow import app_graph, AgentState
# from langchain_core.messages import HumanMessage
#
# # 准备初始状态
# initial_state = AgentState(
#     messages=[HumanMessage(content="请介绍一下我们的产品")],
#     intent_type="",
#     session_id="user_123_session_1",
#     retrieved_chunks=[],
#     rewritten_query="",
#     trace_id="trace_abc123",
# )
#
# # 执行工作流程
# result = await app_graph.ainvoke(initial_state)
#
# # 获取最终响应
# final_response = result["messages"][-1].content
# print(final_response)

