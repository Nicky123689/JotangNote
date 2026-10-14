"""RabbitMQ 生产者：把笔记的增删改封装成消息投递出去，接口立即返回。

消息体（JSON）：
    {"op_id": "...", "op": "create|update|delete", "note_id": 12 | null,
     "user_id": 1, "title": "...", "content": "...", "queued_at": "..."}
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pika

from config import (
    NOTE_QUEUE,
    RABBITMQ_HOST,
    RABBITMQ_PASSWORD,
    RABBITMQ_PORT,
    RABBITMQ_USER,
)


def _connect() -> pika.BlockingConnection:
    creds = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST, port=RABBITMQ_PORT, credentials=creds,
        heartbeat=30, blocked_connection_timeout=10,
    )
    return pika.BlockingConnection(params)


def publish_note_op(op: str, user_id: int, *, note_id: int | None = None,
                    title: str | None = None, content: str | None = None) -> str:
    """投递一条笔记操作消息，返回 op_id（用于幂等和查询）。"""
    op_id = uuid.uuid4().hex[:16]
    body = {
        "op_id": op_id,
        "op": op,
        "note_id": note_id,
        "user_id": user_id,
        "title": title,
        "content": content,
        "queued_at": datetime.now().isoformat(timespec="seconds"),
    }
    conn = _connect()
    try:
        ch = conn.channel()
        # 队列持久化，消息也持久化：RabbitMQ 重启后消息不丢
        ch.queue_declare(queue=NOTE_QUEUE, durable=True)
        ch.basic_publish(
            exchange="",
            routing_key=NOTE_QUEUE,
            body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,               # 2 = 消息持久化
                content_type="application/json",
                message_id=op_id,
            ),
        )
    finally:
        conn.close()
    return op_id
