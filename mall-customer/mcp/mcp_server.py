"""
MCP工具协议服务端 — Model Context Protocol实现
遵循Anthropic MCP标准，通过JSON-RPC 2.0提供工具注册/发现/调用能力。
支持动态工具扩展，Agent通过统一接口调用外部系统。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from datetime import datetime

from mcp.ticket_store import TicketStore
from mcp.mall_server_client import MallServerClient


@dataclass
class ToolDefinition:
    """MCP工具定义"""
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]
    category: str = "general"
    requires_auth: bool = False


@dataclass
class ToolCallResult:
    """工具调用结果"""
    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class MCPToolServer:
    """
    MCP工具服务端。

    实现 Model Context Protocol 的核心功能：
    1. 工具注册 (Tool Registration)
    2. 工具发现 (Tool Discovery) - Agent可查询可用工具列表
    3. 工具调用 (Tool Invocation) - 通过JSON-RPC 2.0协议调用
    4. 结果返回 (Result Delivery)

    遵循MCP规范：
    - 使用JSON-RPC 2.0消息格式
    - 支持工具的inputSchema声明
    - 提供标准化的错误码
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._call_log: list[ToolCallResult] = []

    def register_tool(self, tool: ToolDefinition) -> None:
        """注册一个MCP工具"""
        self._tools[tool.name] = tool

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        category: str = "general",
        requires_auth: bool = False,
    ) -> Callable:
        """工具注册装饰器"""
        def decorator(func: Callable[..., Awaitable[Any]]) -> Callable:
            tool = ToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema,
                handler=func,
                category=category,
                requires_auth=requires_auth,
            )
            self._tools[name] = tool
            return func
        return decorator

    def list_tools(self, category: str | None = None) -> list[dict]:
        """
        工具发现：列出所有可用工具。
        对应MCP的 tools/list 方法。
        """
        tools = []
        for tool in self._tools.values():
            if category and tool.category != category:
                continue
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "category": tool.category,
            })
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        """
        工具调用：执行指定工具。
        对应MCP的 tools/call 方法。
        """
        import time

        tool = self._tools.get(name)
        if tool is None:
            result = ToolCallResult(
                tool_name=name,
                success=False,
                error=f"Tool '{name}' not found. Available: {list(self._tools.keys())}",
            )
            self._call_log.append(result)
            return result

        start = time.time()
        try:
            output = await tool.handler(**arguments)
            duration_ms = (time.time() - start) * 1000

            result = ToolCallResult(
                tool_name=name,
                success=True,
                result=output,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            result = ToolCallResult(
                tool_name=name,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

        self._call_log.append(result)
        return result

    async def handle_jsonrpc(self, request: dict) -> dict:
        """
        处理JSON-RPC 2.0请求。
        MCP协议传输层实现。
        """
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id", 1)

        try:
            if method == "tools/list":
                result = self.list_tools(category=params.get("category"))
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                call_result = await self.call_tool(tool_name, arguments)
                result = {
                    "success": call_result.success,
                    "result": call_result.result,
                    "error": call_result.error,
                }
            elif method == "ping":
                result = {"status": "ok"}
            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": req_id,
                }

            return {"jsonrpc": "2.0", "result": result, "id": req_id}

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": req_id,
            }

    def get_call_log(self, last_n: int = 100) -> list[dict]:
        """获取最近的工具调用日志"""
        return [
            {
                "tool": r.tool_name,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "timestamp": r.timestamp,
                "error": r.error,
            }
            for r in self._call_log[-last_n:]
        ]


# mall-server 订单状态码 → 中文（oms_order.status）
ORDER_STATUS_TEXT: dict[int, str] = {
    0: "待支付",
    1: "已支付",
    2: "已发货",
    3: "已完成",
    4: "已取消",
}


def _simplify_order(order: dict) -> dict:
    """把 mall-server 订单实体精简为 LLM 易读的结构（去掉冗余/敏感字段）"""
    items = order.get("items") or []
    return {
        "order_sn": order.get("orderSn"),
        "status": ORDER_STATUS_TEXT.get(order.get("status"), order.get("status")),
        "total_amount": order.get("totalAmount"),
        "create_time": order.get("createTime"),
        "delivery_time": order.get("deliveryTime"),
        "items": [
            {"product_name": it.get("productName"), "amount": it.get("amount")}
            for it in items
        ],
    }


def create_default_tools(
    server: MCPToolServer,
    ticket_store: TicketStore | None = None,
    long_term_memory: Any | None = None,
    mall_server_client: MallServerClient | None = None,
) -> MCPToolServer:
    """注册默认的MCP工具集（ticket_store/long_term_memory/mall_server_client 由上层注入）"""
    ticket_store = ticket_store or TicketStore()

    @server.register(
        name="order_query",
        description="查询用户订单信息（真实数据来自 mall-server），可按订单号筛选",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID（必填，用于查询该用户的订单）"},
                "order_id": {"type": "string", "description": "订单号 order_sn，可选，用于筛选指定订单"},
            },
            "required": ["user_id"],
        },
        category="order",
    )
    async def order_query(user_id: str = "", order_id: str = "") -> dict:
        # 优先走 mall-server 真实订单接口；未配置或调用失败时降级为静态示例
        if mall_server_client is not None and mall_server_client.configured and user_id:
            try:
                orders = await mall_server_client.list_orders(user_id)
                simplified = [_simplify_order(o) for o in orders]
                if order_id:
                    simplified = [
                        o for o in simplified if o.get("order_sn") == order_id
                    ]
                return {"user_id": user_id, "count": len(simplified), "orders": simplified}
            except Exception as e:
                return {"error": f"订单查询失败: {e}", "orders": []}

        # 降级：未配置 mall-server 或未提供 user_id 时返回静态示例（仅用于开发调试）
        return {
            "user_id": user_id,
            "count": 1,
            "orders": [
                {
                    "order_sn": order_id or "ORD-20260401-001",
                    "status": "已发货",
                    "total_amount": 299.00,
                    "create_time": "2026-04-01T10:00:00",
                    "delivery_time": "2026-04-02T09:30:00",
                    "items": [{"product_name": "智能理财产品A", "amount": 1}],
                }
            ],
        }

    @server.register(
        name="knowledge_search",
        description="搜索企业知识库，返回相关文档片段",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询"},
                "top_k": {"type": "integer", "description": "返回数量", "default": 3},
            },
            "required": ["query"],
        },
        category="knowledge",
    )
    async def knowledge_search(query: str, top_k: int = 3) -> list[dict]:
        if long_term_memory is not None:
            return long_term_memory.search(query, top_k=top_k)
        return [{"content": f"关于'{query}'的知识库文档片段", "source": "FAQ.md", "score": 0.95}]

    @server.register(
        name="ticket_create",
        description="创建客服工单",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                "category": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": ["title", "description"],
        },
        category="ticket",
    )
    async def ticket_create(
        title: str,
        description: str,
        priority: str = "medium",
        category: str = "general",
        user_id: str = "anonymous",
    ) -> dict:
        return ticket_store.create(
            ticket_type=category,
            priority=priority,
            summary=title,
            details=description,
            user_id=user_id,
        )

    @server.register(
        name="ticket_query",
        description="查询客服工单状态",
        input_schema={
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
            },
            "required": ["ticket_id"],
        },
        category="ticket",
    )
    async def ticket_query(ticket_id: str) -> dict | None:
        return ticket_store.query(ticket_id)

    @server.register(
        name="ticket_update",
        description="更新客服工单（优先级/状态）",
        input_schema={
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                "status": {"type": "string"},
            },
            "required": ["ticket_id"],
        },
        category="ticket",
    )
    async def ticket_update(
        ticket_id: str, priority: str | None = None, status: str | None = None
    ) -> dict | None:
        ticket = None
        if priority is not None:
            ticket = ticket_store.update_priority(ticket_id, priority)
        if status is not None:
            ticket = ticket_store.update_status(ticket_id, status)
        return ticket

    @server.register(
        name="risk_check",
        description="风控接口 — 检查交易/操作的风险等级",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "action": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["user_id", "action"],
        },
        category="compliance",
    )
    async def risk_check(user_id: str, action: str, amount: float = 0.0) -> dict:
        risk_level = "low"
        if amount > 50000:
            risk_level = "high"
        elif amount > 10000:
            risk_level = "medium"

        return {
            "user_id": user_id,
            "action": action,
            "risk_level": risk_level,
            "requires_manual_review": risk_level == "high",
        }

    return server