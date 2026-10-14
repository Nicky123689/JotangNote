"""AI 会话管理：把对话历史持久化到 MySQL（Bonus：进程重启也不丢）。

为什么不能只放内存：题目 Bonus 里点到了这一点——进程一重启，Python 里的 list 就没了。
这里把消息写进 `chat_messages` 表，并且**原样保存模型返回的 assistant 消息（含 tool_calls）**
以及 tool 的执行结果，这样下一轮请求能把完整上下文交给模型。

另外还有一个"上下文窗口"的处理：只取最近 LIMIT 条消息，
避免对话变长后把模型的上下文挤爆（更讲究的做法是做摘要压缩或向量检索，见文末说明）。
"""

from __future__ import annotations

import json

import db

MAX_CONTEXT_MESSAGES = 40           # 每次最多带最近 40 条消息给模型
MAX_MESSAGES_KEPT = 200             # 单个会话最多保留 200 条（超出丢弃最旧的）


def ensure_session(user_id: int, session_id: str | None, title: str | None = None) -> str:
    """会话不存在就建一个，返回 session_id。"""
    if session_id:
        row = db.query_one("SELECT id FROM chat_sessions WHERE id=%s AND user_id=%s",
                           (session_id, user_id))
        if row:
            return session_id
    new_id = db.execute_returning_id(
        "INSERT INTO chat_sessions (user_id, title) VALUES (%s, %s)",
        (user_id, (title or "新的对话")[:60]),
    )
    return str(new_id)


def append_message(session_id: str, role: str, content: str | None = None,
                   raw: dict | None = None, tool_call_id: str | None = None) -> None:
    """写入一条消息。raw 用于保存带 tool_calls 的完整 assistant 消息。"""
    db.execute(
        "INSERT INTO chat_messages (session_id, role, content, raw, tool_call_id) "
        "VALUES (%s, %s, %s, %s, %s)",
        (int(session_id), role, content,
         json.dumps(raw, ensure_ascii=False) if raw else None, tool_call_id),
    )


def load_context(session_id: str) -> list[dict]:
    """取最近的若干条消息，还原成 OpenAI 兼容格式。"""
    rows = db.query_all(
        "SELECT role, content, raw, tool_call_id FROM chat_messages "
        "WHERE session_id=%s ORDER BY id DESC LIMIT %s",
        (int(session_id), MAX_CONTEXT_MESSAGES),
    )
    messages: list[dict] = []
    for row in reversed(rows):                    # 数据库是倒序取的，这里翻回时间顺序
        if row["raw"]:
            messages.append(json.loads(row["raw"]))     # 原样回放（含 tool_calls）
        else:
            m = {"role": row["role"], "content": row["content"]}
            if row["tool_call_id"]:
                m["tool_call_id"] = row["tool_call_id"]
            messages.append(m)
    return messages


def list_sessions(user_id: int) -> list[dict]:
    return db.query_all(
        "SELECT id, title, created_at, updated_at FROM chat_sessions "
        "WHERE user_id=%s ORDER BY id DESC LIMIT 50", (user_id,)
    )


def history(session_id: str, user_id: int) -> list[dict]:
    return db.query_all(
        "SELECT id, role, content, created_at FROM chat_messages "
        "WHERE session_id=%s AND session_id IN "
        "(SELECT id FROM chat_sessions WHERE user_id=%s) ORDER BY id", (int(session_id), user_id)
    )
