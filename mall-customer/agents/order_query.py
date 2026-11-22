"""
订单查询Agent — 查询用户真实订单
通过 MCP 工具协议调用 mall-server 内部接口，获取订单数据后用 LLM 生成自然回复。
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from tracing.otel_config import trace_agent_call


# 订单号：yyyyMMddHHmmss + 8 位雪花号（约 22 位连续数字）
ORDER_SN_RE = re.compile(r"\d{20,}")


ORDER_SYSTEM_PROMPT = """你是一个专业的电商订单查询客服，负责回答用户的订单相关问题。

回答规则：
1. 严格基于工具返回的订单数据回答，不要编造订单、金额或状态
2. 用户问某个具体订单时，优先找到对应订单号回答；问"我的订单"时整体说明
3. 状态用中文（待支付/已支付/已发货/已完成/已取消），金额保留两位小数，时间可简化为日期
4. 用户没有订单或未查询到时，友好告知
5. 不承诺退款、赔偿等操作；涉及投诉、退款、退货时，引导其说明原因以便创建工单
"""


class OrderQueryAgent:
    """订单查询Agent"""

    def __init__(self, llm: ChatOpenAI, mcp_server: Any | None = None):
        self.llm = llm
        self.mcp_server = mcp_server

    def _is_mock(self) -> bool:
        """是否处于无 Key 降级（MockLLM）状态"""
        return hasattr(self.llm, "route_intent")

    @staticmethod
    def _extract_order_sn(text: str) -> str | None:
        """从用户消息中提取订单号（约 22 位连续数字）"""
        m = ORDER_SN_RE.search(text or "")
        return m.group(0) if m else None

    @staticmethod
    def _format_orders(orders: list[dict]) -> str:
        if not orders:
            return "（无订单）"
        lines: list[str] = []
        for o in orders:
            items = "、".join(
                f"{it.get('product_name', '')}×{it.get('amount', 0)}"
                for it in o.get("items", [])
            )
            lines.append(
                f"订单号 {o.get('order_sn')}｜状态 {o.get('status')}｜"
                f"金额 {o.get('total_amount')}｜商品 {items or '未知'}｜"
                f"下单 {o.get('create_time')}｜发货 {o.get('delivery_time') or '未发货'}"
            )
        return "\n".join(lines)

    def _mock_answer(self, orders: list[dict], error: str | None) -> str:
        """无 Key 降级：直接用订单数据拼答复，跳过 LLM 生成"""
        if error:
            return "抱歉，订单查询暂时不可用，请稍后重试或联系人工客服。"
        if not orders:
            return "您当前没有订单记录。"
        return f"为您查询到 {len(orders)} 笔订单：\n\n{self._format_orders(orders)}"

    async def _llm_answer(self, query: str, orders: list[dict], error: str | None) -> str:
        if error:
            return "抱歉，订单查询暂时不可用，请稍后重试或联系人工客服。"
        context = self._format_orders(orders)
        messages = [
            SystemMessage(content=ORDER_SYSTEM_PROMPT),
            HumanMessage(content=f"用户问题: {query}\n\n该用户的订单数据:\n{context}"),
        ]
        response = await self.llm.ainvoke(messages)
        return response.content.strip()

    @trace_agent_call("order_query_process")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """作为Graph节点处理状态"""
        messages = state.get("messages", [])
        user_id = state.get("user_id", "anonymous")
        if not messages:
            return state

        last = messages[-1]
        last_message = last.content if isinstance(last.content, str) else str(last.content)

        # 用户提到具体订单号时只查该单，否则查该用户全部订单
        order_sn = self._extract_order_sn(last_message)

        orders: list[dict] = []
        error: str | None = None
        if self.mcp_server is not None:
            result = await self.mcp_server.call_tool("order_query", {
                "user_id": user_id,
                "order_id": order_sn or "",
            })
            if result.success:
                payload = result.result or {}
                if isinstance(payload, dict) and payload.get("error"):
                    error = payload.get("error")
                elif isinstance(payload, dict):
                    orders = payload.get("orders", [])
            else:
                error = result.error or "订单查询失败"
        else:
            error = "订单查询服务不可用"

        if self._is_mock():
            answer = self._mock_answer(orders, error)
        else:
            answer = await self._llm_answer(last_message, orders, error)

        return {
            **state,
            "messages": [AIMessage(content=answer)],
        }