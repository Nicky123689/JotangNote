"""后台消费者：从 MQ 里取消息，真正执行笔记的增删改。

设计要点（对应题目里提到的顺序性与幂等性）：
- 顺序性：单队列 + prefetch=1 + 单消费者，同一批操作按投递顺序执行；
- 幂等性：op_id 写进 processed_ops 表（主键唯一），重复投递的消息直接跳过；
- ack：处理成功才 basic_ack，失败 basic_nack(requeue=False) 不无限重投；
- 写库后主动删缓存，保证「数据库改了，缓存不落后」。
"""

from __future__ import annotations

import json
import sys

import pika

import cache
import db
from config import (
    NOTE_QUEUE,
    RABBITMQ_HOST,
    RABBITMQ_PASSWORD,
    RABBITMQ_PORT,
    RABBITMQ_USER,
)


def apply_op(msg: dict) -> int | None:
    """执行一条笔记操作，返回受影响的 note_id。"""
    op, user_id = msg["op"], msg["user_id"]
    note_id = msg.get("note_id")

    if op == "create":
        new_id = db.execute_returning_id(
            "INSERT INTO notes (user_id, title, content) VALUES (%s, %s, %s)",
            (user_id, msg["title"], msg["content"]),
        )
        return new_id

    if op == "update":
        affected = db.execute(
            "UPDATE notes SET title=%s, content=%s "
            "WHERE id=%s AND user_id=%s AND deleted_at IS NULL",
            (msg["title"], msg["content"], note_id, user_id),
        )
        return note_id if affected else None

    if op == "delete":
        affected = db.execute(
            "UPDATE notes SET deleted_at=NOW() "
            "WHERE id=%s AND user_id=%s AND deleted_at IS NULL",
            (note_id, user_id),
        )
        return note_id if affected else None

    raise ValueError(f"未知操作: {op}")


def already_processed(op_id: str) -> bool:
    row = db.query_one("SELECT op_id FROM processed_ops WHERE op_id=%s", (op_id,))
    return row is not None


def mark_processed(op_id: str, note_id: int | None, op: str) -> None:
    db.execute(
        "INSERT INTO processed_ops (op_id, note_id, op) VALUES (%s, %s, %s)",
        (op_id, note_id, op),
    )


def handle(ch, method, properties, body) -> None:
    try:
        msg = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[skip] 消息不是合法 JSON：{exc}", flush=True)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    op_id, op = msg.get("op_id"), msg.get("op")
    if already_processed(op_id):
        print(f"[idempotent] {op_id} 已处理过，跳过（说明消息被重复投递）", flush=True)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    try:
        note_id = apply_op(msg)
        mark_processed(op_id, note_id, op)
        if note_id is not None:
            cache.invalidate_note(note_id)      # 数据库改了 → 缓存失效
        print(f"[ok] {op} op_id={op_id} note_id={note_id}", flush=True)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:                     # noqa: BLE001
        print(f"[fail] {op} op_id={op_id} 出错：{exc}", flush=True)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main() -> None:
    db.ensure_schema()
    creds = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    conn = pika.BlockingConnection(
        pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT, credentials=creds)
    )
    ch = conn.channel()
    ch.queue_declare(queue=NOTE_QUEUE, durable=True)
    ch.basic_qos(prefetch_count=1)               # 一次只领一条，保证按序处理
    ch.basic_consume(queue=NOTE_QUEUE, on_message_callback=handle)
    print(f"[worker] 已启动，等待队列 {NOTE_QUEUE} 的消息……（Ctrl+C 退出）", flush=True)
    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        ch.stop_consuming()
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
