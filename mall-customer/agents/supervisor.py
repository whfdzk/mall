"""
Supervisor编排Agent — 中央协调者
负责接收用户请求，根据意图路由到对应子Agent，汇总结果返回。
采用LangGraph StateGraph实现，支持并行调度和Human-in-the-Loop断点。
"""

from __future__ import annotations

import operator
import os
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import RemoveMessage, add_messages

from agents.intent_router import IntentRouterAgent
from agents.knowledge_rag import KnowledgeRAGAgent
from agents.ticket_handler import TicketHandlerAgent
from agents.compliance_checker import ComplianceCheckerAgent
from agents.chitchat import ChitchatAgent
from agents.order_query import OrderQueryAgent
from agents.mock_llm import MockLLM
from memory.working_memory import WorkingMemory
from memory.long_term_memory import LongTermMemory
from tracing.otel_config import trace_agent_call


# ─── 状态定义 ───

# 短期记忆滑动窗口：Agent State 中最多保留最近 20 条消息（约 10 轮对话），
# 超出部分由 trim_history 节点用 RemoveMessage 移除，防止状态无限增长
MESSAGE_WINDOW_SIZE = 20


class AgentState(TypedDict):
    """Supervisor编排的全局状态"""
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str
    intent: str
    compliance_passed: bool
    current_agent: str
    retry_count: int


# ─── 记忆窗口 ───

def trim_history(state: AgentState) -> dict[str, Any]:
    """滑动窗口：把 Agent State 的消息裁剪到最近 MESSAGE_WINDOW_SIZE 条

    作为图的入口节点执行，紧接着本轮的输入合并之后——保证后续所有节点的
    LLM 只看得到窗口内的消息，checkpointer 持久化的也是有界状态。
    通过 RemoveMessage 走 add_messages reducer 裁剪，而不是直接覆盖列表。
    """
    messages = state.get("messages", [])
    overflow = len(messages) - MESSAGE_WINDOW_SIZE
    if overflow <= 0:
        return {}

    removals = [RemoveMessage(id=m.id) for m in messages[:overflow] if m.id]
    return {"messages": removals}


# ─── Supervisor节点 ───


class SupervisorNode:
    """Supervisor决策节点"""

    def __init__(self, llm: ChatOpenAI, working_memory: WorkingMemory, intent_router: IntentRouterAgent):
        self.llm = llm
        self.working_memory = working_memory
        self.intent_router = intent_router

    @trace_agent_call("supervisor")
    async def route_decision(self, state: AgentState) -> AgentState:
        """分析用户意图，决定路由"""
        messages = state["messages"]
        session_id = state.get("session_id", "default")

        last_text = ""
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                last_text = m.content if isinstance(m.content, str) else str(m.content)
                break
        if not last_text and messages:
            last_text = messages[-1].content

        # 统一交给意图路由 Agent 决策（真实 LLM 与 MockLLM 降级均由其内部处理）
        intent_result = await self.intent_router.classify(last_text)
        intent = intent_result.suggested_agent

        valid_intents = {"knowledge_rag", "order_query", "ticket_handler", "chitchat", "compliance_checker"}
        if intent not in valid_intents:
            intent = "knowledge_rag"

        self.working_memory.update(session_id, {"last_intent": intent})

        return {
            **state,
            "intent": intent,
            "current_agent": "supervisor",
        }

    @trace_agent_call("supervisor_synthesize")
    async def synthesize_response(self, state: AgentState) -> AgentState:
        """合规门控 — 子Agent的回答已由其本人写入 messages

        - 合规不通过：撤回本轮草稿消息（避免违规内容进入会话历史），追加转人工话术
        - 合规通过：末尾 AIMessage 即最终回复，不再追加（否则历史中出现重复消息）
        - 本轮无子Agent回答（如直达合规审查）：追加兜底话术
        """
        messages = state.get("messages", [])
        last = messages[-1] if messages else None

        if not state.get("compliance_passed", True):
            final_response = (
                "抱歉，您的请求涉及敏感内容，已转交人工客服处理。"
                "工单编号已自动生成，请留意后续通知。"
            )
            updates: list[BaseMessage] = []
            if isinstance(last, AIMessage) and last.id:
                updates.append(RemoveMessage(id=last.id))
            updates.append(AIMessage(content=final_response))
            return {**state, "messages": updates}

        if isinstance(last, AIMessage) and bool(last.content):
            return state

        final_response = "抱歉，暂时无法处理您的请求，请稍后重试。"
        return {**state, "messages": [AIMessage(content=final_response)]}


# ─── 路由函数 ───

def route_to_agent(state: AgentState) -> str:
    """根据意图路由到对应Agent节点"""
    intent = state.get("intent", "knowledge_rag")
    route_map = {
        "knowledge_rag": "knowledge_rag",
        "order_query": "order_query",
        "ticket_handler": "ticket_handler",
        "chitchat": "chitchat",
        "compliance_checker": "compliance_check",
    }
    return route_map.get(intent, "knowledge_rag")


def should_check_compliance(state: AgentState) -> str:
    """所有回复都需经过合规审查"""
    return "compliance_check"


# ─── 构建Graph ───

def create_supervisor_graph(
        llm: ChatOpenAI | None = None,
        working_memory: WorkingMemory | None = None,
        long_term_memory: LongTermMemory | None = None,
        checkpointer: Any | None = None,
        mcp_server: Any | None = None,
        enable_checkpointing: bool = True,
) -> StateGraph:
    """
    构建Supervisor编排的多Agent StateGraph。

    这是整个系统的核心入口，将各子Agent通过有向图连接起来，
    由Supervisor节点负责路由决策和结果汇总。

    Args:
        llm: 语言模型实例
        working_memory: 工作记忆
        long_term_memory: 长期记忆
        checkpointer: LangGraph checkpointer（如 AsyncRedisSaver），对话状态由其持久化；
            为 None 且 enable_checkpointing=True 时回退到进程内 MemorySaver
        enable_checkpointing: 是否启用检查点（支持断点恢复）
    """
    if llm is None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if api_key:
            print(f"[Supervisor] 使用真实 LLM: model={os.getenv('MODEL_NAME')}, base_url={os.getenv('OPENAI_BASE_URL')}")
            llm = ChatOpenAI(model=os.getenv("MODEL_NAME"),
                             api_key=api_key,
                             base_url=os.getenv("OPENAI_BASE_URL"),
                             temperature=0)
        else:
            print("[Supervisor] ⚠️ 未配置 OPENAI_API_KEY，降级为 MockLLM（规则引擎回复）")
            llm = MockLLM()
    if working_memory is None:
        working_memory = WorkingMemory()

    intent_router = IntentRouterAgent(llm)
    supervisor = SupervisorNode(llm, working_memory, intent_router)
    knowledge_agent = KnowledgeRAGAgent(llm, long_term_memory)
    order_agent = OrderQueryAgent(llm, mcp_server=mcp_server)
    ticket_agent = TicketHandlerAgent(llm, mcp_server=mcp_server)
    compliance_agent = ComplianceCheckerAgent(llm)
    chitchat_agent = ChitchatAgent(llm)

    graph = StateGraph(AgentState)

    graph.add_node("trim_history", trim_history)   # 滑动窗口：裁剪超窗口的历史消息
    graph.add_node("supervisor_route", supervisor.route_decision)
    graph.add_node("knowledge_rag", knowledge_agent.process)
    graph.add_node("order_query", order_agent.process)
    graph.add_node("ticket_handler", ticket_agent.process)
    graph.add_node("chitchat", chitchat_agent.process)
    graph.add_node("compliance_check", compliance_agent.process)
    graph.add_node("synthesize", supervisor.synthesize_response)

    graph.set_entry_point("trim_history")
    graph.add_edge("trim_history", "supervisor_route")

    graph.add_conditional_edges(
        "supervisor_route",
        route_to_agent,
        {
            "knowledge_rag": "knowledge_rag",
            "order_query": "order_query",
            "ticket_handler": "ticket_handler",
            "chitchat": "chitchat",
            "compliance_check": "compliance_check",
        },
    )

    graph.add_edge("knowledge_rag", "compliance_check")
    graph.add_edge("order_query", "compliance_check")
    graph.add_edge("ticket_handler", "compliance_check")
    graph.add_edge("chitchat", "compliance_check")
    graph.add_edge("compliance_check", "synthesize")
    graph.add_edge("synthesize", END)

    if checkpointer is None and enable_checkpointing:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)

    return compiled