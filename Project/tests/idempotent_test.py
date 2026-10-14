#!/usr/bin/env python3
"""验证 MQ 的幂等性：把同一条消息（同一个 op_id）投递两次，只应生效一次。

用法：python3 Project/tests/idempotent_test.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pika  # noqa: E402

import config  # noqa: E402
import db  # noqa: E402

DUP_OP_ID = "dup-demo-0001"


def publish(body: dict) -> None:
    creds = pika.PlainCredentials(config.RABBITMQ_USER, config.RABBITMQ_PASSWORD)
    conn = pika.BlockingConnection(pika.ConnectionParameters(
        host=config.RABBITMQ_HOST, port=config.RABBITMQ_PORT, credentials=creds))
    ch = conn.channel()
    ch.queue_declare(queue=config.NOTE_QUEUE, durable=True)
    ch.basic_publish(exchange="", routing_key=config.NOTE_QUEUE,
                     body=json.dumps(body, ensure_ascii=False).encode(),
                     properties=pika.BasicProperties(delivery_mode=2, message_id=body["op_id"]))
    conn.close()


def main() -> None:
    msg = {"op_id": DUP_OP_ID, "op": "create", "note_id": None, "user_id": 1,
           "title": "重复投递测试", "content": "这条消息会被投递两次", "queued_at": "2026-10-14T15:40:00"}

    before = db.query_one("SELECT COUNT(*) AS c FROM notes WHERE title=%s", (msg["title"],))["c"]
    print(f"投递前，标题为「{msg['title']}」的笔记数：{before}")

    print("第一次投递……")
    publish(msg)
    time.sleep(1.0)
    print("第二次投递（同一个 op_id）……")
    publish(msg)
    time.sleep(1.0)

    after = db.query_one("SELECT COUNT(*) AS c FROM notes WHERE title=%s", (msg["title"],))["c"]
    print(f"投递两次后，标题为「{msg['title']}」的笔记数：{after}")
    print("结论：", "幂等生效（只写入 1 篇）" if after - before == 1 else "!!! 出现重复写入，需要检查")


if __name__ == "__main__":
    main()
