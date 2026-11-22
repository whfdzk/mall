"""
工单存储 — 默认内存实现，可选 SQLite 持久化。

独立成模块，供 MCP 工具与 TicketHandlerAgent 共享同一实例：
Agent 通过 MCP 工具协议访问工单，不再直接持有存储。

通过构造参数 ``db_path`` 传入 SQLite 文件路径即可启用持久化
（跨重启保留），未传时保持内存实现，便于单元测试与降级。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class TicketStatus(str, Enum):
    CREATED = "created"
    PROCESSING = "processing"
    PENDING_REVIEW = "pending_review"
    RESOLVED = "resolved"
    CLOSED = "closed"
    ESCALATED = "escalated"


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketStore:
    """工单存储：默认内存实现；传入 ``db_path`` 时启用 SQLite 持久化。

    - 内存模式下所有数据保存在进程内，重启即丢失（用于测试/降级）。
    - SQLite 模式下每次写入同步落盘，重启后自动加载历史工单。
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path
        self._tickets: dict[str, dict] = {}
        self._conn: sqlite3.Connection | None = None
        if db_path:
            self._init_db()

    # ------------------------------------------------------------------
    # 持久化基础设施
    # ------------------------------------------------------------------
    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id  TEXT PRIMARY KEY,
                type       TEXT NOT NULL,
                priority   TEXT NOT NULL,
                status     TEXT NOT NULL,
                summary    TEXT NOT NULL,
                details    TEXT NOT NULL,
                user_id    TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
        self._load()

    def _load(self) -> None:
        """启动时把历史工单载入内存缓存。"""
        rows = self._conn.execute("SELECT * FROM tickets").fetchall()
        cols = [c[0] for c in self._conn.execute("SELECT * FROM tickets").description]
        self._tickets = {r[0]: dict(zip(cols, r)) for r in rows}

    def _save(self, ticket: dict) -> None:
        """同步写回 SQLite（INSERT OR REPLACE 幂等）。"""
        if self._conn is None:
            return
        self._conn.execute(
            """
            INSERT OR REPLACE INTO tickets
                (ticket_id, type, priority, status, summary, details, user_id, created_at, updated_at)
            VALUES (:ticket_id, :type, :priority, :status, :summary, :details, :user_id, :created_at, :updated_at)
            """,
            ticket,
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # 业务接口
    # ------------------------------------------------------------------
    def create(
        self, ticket_type: str, priority: str, summary: str, details: str, user_id: str
    ) -> dict:
        now = datetime.now().isoformat()
        ticket_id = f"TK-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        ticket = {
            "ticket_id": ticket_id,
            "type": ticket_type,
            "priority": priority,
            "status": TicketStatus.CREATED.value,
            "summary": summary,
            "details": details,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        self._tickets[ticket_id] = ticket
        self._save(ticket)
        return ticket

    def query(self, ticket_id: str) -> dict | None:
        return self._tickets.get(ticket_id)

    def query_by_user(self, user_id: str) -> list[dict]:
        return [t for t in self._tickets.values() if t["user_id"] == user_id]

    def update_priority(self, ticket_id: str, priority: str) -> dict | None:
        ticket = self._tickets.get(ticket_id)
        if ticket:
            ticket["priority"] = priority
            ticket["updated_at"] = datetime.now().isoformat()
            self._save(ticket)
        return ticket

    def update_status(self, ticket_id: str, status: str) -> dict | None:
        ticket = self._tickets.get(ticket_id)
        if ticket:
            ticket["status"] = status
            ticket["updated_at"] = datetime.now().isoformat()
            self._save(ticket)
        return ticket