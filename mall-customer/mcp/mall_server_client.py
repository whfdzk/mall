"""
mall-server（Java）内部接口客户端 — 供 MCP 工具查询真实业务数据。

Agent 不持有用户的登录 token，因此由 mall-server 提供 /internal/agent/* 内部接口，
以 user_id 代查真实数据；服务间通过 X-Internal-Token 鉴权，避免接口裸奔。
"""

from __future__ import annotations

import os

import httpx


class MallServerClient:
    """mall-server（Java）内部接口客户端"""

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("MALL_SERVER_URL", "")).rstrip("/")
        self.token = token or os.getenv("MALL_SERVER_INTERNAL_TOKEN", "")

    @property
    def configured(self) -> bool:
        """是否已配置 mall-server 地址（未配置时工具降级为静态示例）"""
        return bool(self.base_url)

    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Token": self.token} if self.token else {}

    async def list_orders(self, user_id: str) -> list[dict]:
        """查询用户订单列表，返回原始订单数据（含商品明细）"""
        url = f"{self.base_url}/internal/agent/order/list"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url, params={"userId": user_id}, headers=self._headers()
            )
            resp.raise_for_status()
            payload = resp.json()

        # mall-server 统一响应体：{code, message, data}
        if payload.get("code") != 200:
            raise RuntimeError(f"mall-server 返回错误: {payload.get('message')}")

        return payload.get("data") or []

    async def list_products(self) -> list[dict]:
        """查询上架商品列表，用于知识库导入真实业务数据。"""
        url = f"{self.base_url}/internal/agent/product/list"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()

        if payload.get("code") != 200:
            raise RuntimeError(f"mall-server 返回错误: {payload.get('message')}")

        return payload.get("data") or []