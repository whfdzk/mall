"""
工单处理Agent — 工单CRUD与流转
负责创建、查询、更新工单，对接工单系统，处理退款/理赔/开户等业务办理类需求。
通过MCP工具协议调用外部工单系统。
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from mcp.ticket_store import TicketStore
from tracing.otel_config import trace_agent_call


# 从对话历史中提取已有工单号（TK-YYYYMMDD-XXXXXX）
TICKET_RE = re.compile(r"TK-\d{8}-[A-Fa-f0-9]{6}")


TICKET_SYSTEM_PROMPT = """你是一个专业的工单处理Agent，负责处理客户的业务办理请求。

你的职责：
1. 分析用户需求，判断是否需要创建工单
2. 提取工单关键信息（类型、优先级、描述）
3. 创建工单并返回工单号
4. 查询/更新现有工单状态

工单类型：
- refund: 退款申请
- claim: 理赔申请
- account_open: 开户申请
- account_change: 账户变更
- complaint: 投诉工单
- general: 通用工单

优先级判断规则：
- urgent: 资金安全、账户被盗
- high: 退款超时、理赔争议
- medium: 常规业务办理
- low: 信息咨询类

重要规则：
- 当用户消息在指代、查询或要求处理某个**已存在**的工单（如"那个工单""它""刚才的单子""查一下进度""给它加急"）时，action 必须为 query 或 update，并从**对话历史**中提取已有工单号填入 ticket_id；此时**严禁新建工单**。
- 只有用户提出**全新**的办理/投诉请求时才 action=create。

请以JSON格式返回工单信息：
{
    "action": "create|query|update",
    "ticket_id": "仅 action 为 query/update 时必填：从对话历史中提取的已有工单号（TK- 开头），确定不了时省略此字段",
    "ticket_type": "refund|claim|account_open|...",
    "priority": "low|medium|high|urgent",
    "summary": "工单摘要",
    "details": "详细描述"
}
"""


class TicketHandlerAgent:
    """工单处理Agent"""

    def __init__(
        self,
        llm: ChatOpenAI,
        ticket_store: TicketStore | None = None,
        mcp_server: Any | None = None,
    ):
        self.llm = llm
        # mcp_server 存在时，工单操作统一走 MCP 工具协议；否则降级为内存 TicketStore
        self.mcp_server = mcp_server
        self.ticket_store = ticket_store or TicketStore()

    def _is_mock(self) -> bool:
        """是否处于无 Key 降级（MockLLM）状态"""
        return hasattr(self.llm, "route_intent")

    def _extract_ticket_id_from_text(self, text: str) -> str | None:
        """从文本中提取工单号"""
        match = TICKET_RE.search(text)
        return match.group(0) if match else None

    def _mock_analyze(self, user_message: str, history: str = "") -> dict:
        """无 Key 降级：用关键词规则分析工单意图，替代 LLM JSON 解析"""
        existing_id = self._extract_ticket_id_from_text(history)

        query_kw = ("查询", "查一下", "进度", "状态", "怎么样", "处理到", "催办", "看看")
        update_kw = ("加急", "升级", "催办", "改", "重新")

        action = "create"
        if existing_id and any(k in user_message for k in query_kw + update_kw):
            action = "update" if any(k in user_message for k in update_kw) else "query"

        type_map = (
            ("退款", "refund"), ("退货", "refund"), ("退钱", "refund"),
            ("理赔", "claim"), ("开户", "account_open"), ("投诉", "complaint"), ("差评", "complaint"),
        )
        ticket_type = "general"
        for kw, t in type_map:
            if kw in user_message:
                ticket_type = t
                break

        if any(k in user_message for k in ("被盗", "资金安全", "盗刷", "诈骗", "冻结")):
            priority = "urgent"
        elif any(k in user_message for k in ("超时", "争议", "投诉", "加急", "差评")):
            priority = "high"
        elif any(k in user_message for k in ("咨询", "了解", "怎么", "如何", "流程", "政策")):
            priority = "low"
        else:
            priority = "medium"

        return {
            "action": action,
            "ticket_id": existing_id,
            "ticket_type": ticket_type,
            "priority": priority,
            "summary": user_message[:100],
            "details": user_message,
        }

    @trace_agent_call("ticket_analyze")
    async def analyze_request(self, user_message: str, history: str = "") -> dict:
        """分析用户需求，提取工单信息（history 为最近对话，供提取已有工单号等上下文）"""
        if self._is_mock():
            return self._mock_analyze(user_message, history)

        if history:
            user_content = f"对话历史:\n{history}\n\n当前用户消息: {user_message}"
        else:
            user_content = f"用户消息: {user_message}"
        messages = [
            SystemMessage(content=TICKET_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        response = await self.llm.ainvoke(messages)

        import json
        content = response.content.strip()
        # LLM 可能用 ```json 代码块包裹，剥壳后再解析
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.DOTALL)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {
                "action": "create",
                "ticket_type": "general",
                "priority": "medium",
                "summary": user_message[:100],
                "details": user_message,
            }

    @trace_agent_call("ticket_create")
    async def create_ticket(self, ticket_info: dict, user_id: str) -> str:
        """创建工单（优先走 MCP 工具协议）"""
        if self.mcp_server is not None:
            result = await self.mcp_server.call_tool("ticket_create", {
                "title": ticket_info.get("summary", ""),
                "description": ticket_info.get("details", ""),
                "priority": ticket_info.get("priority", "medium"),
                "category": ticket_info.get("ticket_type", "general"),
                "user_id": user_id,
            })
            ticket = result.result if result.success else None
            if ticket is None:
                return "工单创建失败，请稍后重试或联系人工客服。"
        else:
            ticket = self.ticket_store.create(
                ticket_type=ticket_info.get("ticket_type", "general"),
                priority=ticket_info.get("priority", "medium"),
                summary=ticket_info.get("summary", ""),
                details=ticket_info.get("details", ""),
                user_id=user_id,
            )

        priority_label = {
            "low": "普通", "medium": "中等", "high": "高", "urgent": "紧急"
        }.get(ticket["priority"], "中等")

        return (
            f"工单已创建成功！\n\n"
            f"📋 工单号: {ticket['ticket_id']}\n"
            f"📝 类型: {ticket['type']}\n"
            f"⚡ 优先级: {priority_label}\n"
            f"📄 摘要: {ticket['summary']}\n"
            f"🕐 创建时间: {ticket['created_at']}\n\n"
            f"我们将尽快处理您的请求，请保存好工单号以便后续查询。"
        )

    @trace_agent_call("ticket_query")
    async def query_ticket(self, ticket_id: str) -> str:
        """查询工单状态（优先走 MCP 工具协议）"""
        if self.mcp_server is not None:
            result = await self.mcp_server.call_tool("ticket_query", {"ticket_id": ticket_id})
            ticket = result.result if result.success else None
        else:
            ticket = self.ticket_store.query(ticket_id)
        if not ticket:
            return f"未找到工单号 {ticket_id}，请确认工单号是否正确。"

        status_label = {
            "created": "已创建",
            "processing": "处理中",
            "pending_review": "待审核",
            "resolved": "已解决",
            "closed": "已关闭",
            "escalated": "已升级",
        }.get(ticket["status"], ticket["status"])

        return (
            f"工单查询结果：\n\n"
            f"📋 工单号: {ticket['ticket_id']}\n"
            f"📊 状态: {status_label}\n"
            f"📝 类型: {ticket['type']}\n"
            f"📄 摘要: {ticket['summary']}\n"
            f"🕐 创建时间: {ticket['created_at']}\n"
            f"🔄 更新时间: {ticket['updated_at']}"
        )

    def _format_history(self, messages: list[Any]) -> str:
        """把对话历史（最近 10 条）格式化为文本，注入分析 prompt。"""
        lines: list[str] = []
        for m in messages[-10:]:
            role = "用户" if isinstance(m, HumanMessage) else "客服"
            content = m.content if isinstance(m.content, str) else str(m.content)
            lines.append(f"{role}: {content[:500]}")
        return "\n".join(lines)

    def _extract_ticket_id(self, messages: list[Any]) -> str | None:
        """从对话历史（由新到旧）中提取最近出现的已有工单号。"""
        for m in reversed(messages):
            content = m.content if isinstance(m.content, str) else str(m.content)
            match = TICKET_RE.search(content)
            if match:
                return match.group(0)
        return None

    def _format_update(self, ticket: dict) -> str:
        priority_label = {
            "low": "普通", "medium": "中等", "high": "高", "urgent": "紧急"
        }.get(ticket["priority"], "中等")
        status_label = {
            "created": "已创建", "processing": "处理中", "pending_review": "待审核",
            "resolved": "已解决", "closed": "已关闭", "escalated": "已升级",
        }.get(ticket["status"], ticket["status"])
        return (
            f"工单已更新成功！\n\n"
            f"📋 工单号: {ticket['ticket_id']}\n"
            f"⚡ 优先级: {priority_label}\n"
            f"📊 状态: {status_label}\n"
            f"🕐 更新时间: {ticket['updated_at']}\n\n"
            f"我们会按更新后的要求处理，请保存好工单号以便后续查询。"
        )

    @trace_agent_call("ticket_handler_process")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """作为Graph节点处理状态"""
        messages = state.get("messages", [])
        user_id = state.get("user_id", "anonymous")

        if not messages:
            return state

        last_message = messages[-1].content
        # 关键修复：把对话历史一并交给分析 LLM，否则它只看得到最新一条消息，
        # 无法得知用户指代的已有工单（记忆存了却用不上）
        history_text = self._format_history(messages[:-1])
        ticket_info = await self.analyze_request(last_message, history_text)

        action = ticket_info.get("action", "create")
        # 双保险：LLM 没带 ticket_id 时，直接从对话历史里提取
        ticket_id = ticket_info.get("ticket_id") or self._extract_ticket_id(messages)

        if action in ("query", "update") and ticket_id:
            if action == "update":
                priority = ticket_info.get("priority", "medium")
                if self.mcp_server is not None:
                    result = await self.mcp_server.call_tool(
                        "ticket_update", {"ticket_id": ticket_id, "priority": priority}
                    )
                    updated = result.result if result.success else None
                else:
                    updated = self.ticket_store.update_priority(ticket_id, priority)
                result = (
                    self._format_update(updated)
                    if updated
                    else f"未找到工单号 {ticket_id}，请确认工单号是否正确。"
                )
            else:
                result = await self.query_ticket(ticket_id)
        else:
            result = await self.create_ticket(ticket_info, user_id)

        return {
            **state,
            "messages": [AIMessage(content=result)],
        }