"""
FastAPI入口 — 提供REST API + SSE流式响应
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from agents.supervisor import create_supervisor_graph
from memory.working_memory import WorkingMemory
from memory.short_term_memory import ShortTermMemory
from memory.long_term_memory import LongTermMemory
from mcp.mcp_server import MCPToolServer, create_default_tools
from mcp.ticket_store import TicketStore
from mcp.mall_server_client import MallServerClient
from tracing.otel_config import init_tracer, AgentMetrics

load_dotenv()


working_memory = WorkingMemory()
short_term_memory = ShortTermMemory()
long_term_memory = LongTermMemory(index_path=os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index"))
ticket_store = TicketStore(db_path=os.getenv("TICKET_DB_PATH", "./data/tickets.db"))
mall_server_client = MallServerClient()
mcp_server = create_default_tools(
    MCPToolServer(),
    ticket_store=ticket_store,
    long_term_memory=long_term_memory,
    mall_server_client=mall_server_client,
)
metrics = AgentMetrics()
graph = None

# 商品知识库文档来源标识：同步时按此来源清理已下架商品
PRODUCT_KB_SOURCE = "mall-server/products"


def _build_product_content(p: dict) -> str:
    """把商品数据拼成知识库文档内容（与文档 id 的 MD5 计算保持一致）。"""
    name = (p.get("name") or "").strip()
    price = p.get("price")
    category = (p.get("categoryName") or "").strip()
    detail = (p.get("detail") or "").strip()
    parts = [f"商品：{name}", f"价格：{price}元", f"分类：{category}"]
    if detail:
        parts.append(f"简介：{detail[:200]}")
    return "｜".join(parts)


async def _sync_products_to_kb() -> int:
    """从 mall-server 拉取上架商品同步到长期记忆知识库（增量，失败静默降级）。

    - 新增/变更商品：按内容 MD5 幂等写入
    - 已下架商品：移除对应来源的旧文档，避免 RAG 召回已下架商品
    """
    if not mall_server_client.configured:
        print("[知识库] 未配置 MALL_SERVER_URL，跳过商品同步")
        return 0
    try:
        products = await mall_server_client.list_products()
    except Exception as exc:
        print(f"[知识库] 商品同步失败，沿用已有知识库: {exc}")
        return 0

    current_ids: set[str] = set()
    pending: list[dict] = []
    for p in products:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        content = _build_product_content(p)
        current_ids.add(hashlib.md5(content.encode()).hexdigest()[:12])
        pending.append({
            "content": content,
            "metadata": {
                "type": "product",
                "product_id": p.get("id"),
                "name": name,
                "category": (p.get("categoryName") or "").strip(),
            },
        })

    removed = long_term_memory.remove_by_source(PRODUCT_KB_SOURCE, keep_ids=current_ids)
    for item in pending:
        long_term_memory.add_document(
            content=item["content"],
            source=PRODUCT_KB_SOURCE,
            metadata=item["metadata"],
        )
    long_term_memory.save()
    print(f"[知识库] 商品同步完成：移除已下架 {removed} 条，当前上架 {len(pending)} 个")
    return len(pending)


async def _periodic_kb_sync(interval: int) -> None:
    """周期性同步商品知识库，捕获异常避免后台任务退出。"""
    while True:
        await asyncio.sleep(interval)
        try:
            await _sync_products_to_kb()
        except Exception as exc:
            print(f"[知识库] 定时同步异常: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global graph

    init_tracer(
        service_name=os.getenv("OTEL_SERVICE_NAME", "smart-cs-multi-agent"),
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )

    # 短期记忆：Redis 持久化 Agent State，Redis 不可用时自动降级内存
    await short_term_memory.setup()

    graph = create_supervisor_graph(
        working_memory=working_memory,
        long_term_memory=long_term_memory,
        checkpointer=short_term_memory.checkpointer,
        mcp_server=mcp_server,
    )

    if long_term_memory.is_empty():
        long_term_memory.add_document(
            content="我们的理财产品A年化收益率为3.5%-5.2%，投资期限为6个月至3年，最低投资金额10000元。注意：理财非存款，产品有风险，投资须谨慎。",
            source="product_faq.md",
        )
        long_term_memory.add_document(
            content="退款政策：用户在购买后7天内可申请无理由退款，超过7天需提供合理原因。退款将在3-5个工作日内原路退回。",
            source="refund_policy.md",
        )
        long_term_memory.add_document(
            content="开户流程：1.准备身份证原件 2.填写开户申请表 3.进行视频认证 4.设置交易密码 5.完成风险评估问卷。整个流程约需15-30分钟。",
            source="account_guide.md",
        )
        long_term_memory.save()

    # 接入真实业务数据：拉取 mall-server 上架商品写入知识库（幂等）
    await _sync_products_to_kb()

    # 商品知识库定时增量同步（KB_SYNC_INTERVAL_SECONDS<=0 时关闭）
    sync_task: asyncio.Task | None = None
    interval = int(os.getenv("KB_SYNC_INTERVAL_SECONDS", "3600") or "0")
    if interval > 0:
        sync_task = asyncio.create_task(_periodic_kb_sync(interval))
        print(f"[知识库] 已启动定时同步，间隔 {interval} 秒")

    yield

    if sync_task is not None:
        sync_task.cancel()
    await short_term_memory.aclose()
    ticket_store.close()


app = FastAPI(
    title="智能客服多Agent系统",
    description="基于LangGraph的Supervisor编排多Agent智能客服系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """可选鉴权：仅当配置了 API_AUTH_TOKEN 时，对 /api/ 前缀的请求校验 X-API-Key 头。

    默认（未配置 token）为放行，不影响既有调用方；/health 不受保护。
    """
    token = os.getenv("API_AUTH_TOKEN", "").strip()
    if token and request.url.path.startswith("/api/"):
        if request.headers.get("X-API-Key") != token:
            return JSONResponse(status_code=401, content={"detail": "未授权访问"})
    return await call_next(request)


class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    intent: str
    compliance_passed: bool


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """主聊天接口 — SSE流式输出"""
    if graph is None:
        raise HTTPException(status_code=503, detail="系统初始化中")

    session_id = request.session_id or str(uuid.uuid4())

    async def event_generator():
        from langchain_core.messages import AIMessage, HumanMessage

        initial_state = {
            "messages": [HumanMessage(content=request.message)],
            "user_id": request.user_id,
            "session_id": session_id,
            "intent": "",
            "compliance_passed": True,
            "current_agent": "",
            "retry_count": 0,
        }

        config = {"configurable": {"thread_id": session_id}}

        try:
            result = await graph.ainvoke(initial_state, config=config)
            # 最终回复即 Agent State 中末尾的 AIMessage（子Agent草稿或合成节点兜底话术）
            messages = result.get("messages") or []
            last = messages[-1] if messages else None
            final_response = (
                last.content
                if isinstance(last, AIMessage) and last.content
                else "系统处理异常，请稍后重试"
            )
        except Exception as e:
            # 不把内部异常细节透传给客户，仅记录服务端日志
            print(f"[api] chat 处理失败: {type(e).__name__}: {e}")
            final_response = "抱歉，系统处理您的请求时出现异常，请稍后重试。"

        # 模拟打字机流式切块输出
        chunk_size = 4
        for i in range(0, len(final_response), chunk_size):
            chunk = final_response[i:i + chunk_size]
            payload = json.dumps({"content": chunk}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.03)

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/history/{session_id}")
async def get_history(session_id: str, last_n: int = 20):
    """获取对话历史 — 读取 LangGraph Agent State（checkpointer）"""
    if graph is None:
        raise HTTPException(status_code=503, detail="系统初始化中")
    history = await short_term_memory.get_history(graph, session_id, last_n=last_n)
    return {"session_id": session_id, "messages": history}


@app.get("/api/tools")
async def list_tools():
    """MCP工具发现接口"""
    return {"tools": mcp_server.list_tools()}


@app.post("/api/tools/call")
async def call_tool(request: dict):
    """MCP工具调用接口"""
    result = await mcp_server.call_tool(
        name=request.get("name", ""),
        arguments=request.get("arguments", {}),
    )
    return {
        "success": result.success,
        "result": result.result,
        "error": result.error,
        "duration_ms": result.duration_ms,
    }


@app.post("/api/kb/sync")
async def sync_kb():
    """手动触发商品知识库同步，返回本次上架商品数量（0 表示无变更或未配置）。"""
    count = await _sync_products_to_kb()
    return {"status": "ok", "synced": count}


@app.get("/api/metrics")
async def get_metrics():
    """获取系统指标"""
    return {
        "agent_metrics": metrics.get_summary(),
        "tool_call_log": mcp_server.get_call_log(last_n=20),
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )