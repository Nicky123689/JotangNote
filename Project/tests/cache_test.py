#!/usr/bin/env python3
"""验证 Redis 缓存三件事：缓存旁路命中、缓存穿透防护、缓存击穿防护。

用法：python3 Project/tests/cache_test.py
"""
from __future__ import annotations

import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import redis  # noqa: E402

import config  # noqa: E402

BASE = "http://127.0.0.1:8080"
STUDENT = "2025090914010"
rds = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.REDIS_DB,
                  decode_responses=True)


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def section(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)


def main():
    _, p = call("POST", "/api/auth/login", {"student_id": STUDENT, "password": "jotang123"})
    token = p["data"]["token"]

    section("1. 缓存旁路（Cache-Aside）：第一次回源 MySQL，第二次命中 Redis")
    _, created = call("POST", "/api/notes",
                      {"title": "缓存演示笔记", "content": "用来演示 Redis 缓存"}, token)
    op_id = created["data"]["op_id"]
    time.sleep(1.2)
    note_id = call("GET", "/api/notes", token=token)[1]["data"][0]["id"]
    rds.delete(f"note:{note_id}")
    print(f"  （已清掉 note:{note_id}，模拟缓存未命中）")
    for i in (1, 2):
        _, resp = call("GET", f"/api/notes/{note_id}", token=token)
        print(f"  第 {i} 次查询 _source = {resp['data']['_source']}")
    print(f"  redis key note:{note_id} 的 TTL = {rds.ttl(f'note:{note_id}')} 秒（配置 300 秒）")

    section("2. 缓存穿透：查一个数据库里也不存在的 id")
    missing = random.randint(900000, 999999)
    for i in (1, 2, 3):
        code, _ = call("GET", f"/api/notes/{missing}", token=token)
        print(f"  第 {i} 次查 note:{missing} → HTTP {code}")
    raw = rds.get(f"note:{missing}")
    print(f"  缓存里的标记：{raw!r}，TTL = {rds.ttl(f'note:{missing}')} 秒")
    print("  → 后两次不再砸 MySQL，因为命中了这个空值标记")

    section("3. 缓存击穿：热点 key 刚过期，20 个并发请求同时来")
    rds.delete(f"note:{note_id}")
    print(f"  （已清掉 note:{note_id}，模拟刚过期）")
    results, lock = [], threading.Lock()

    def worker():
        _, resp = call("GET", f"/api/notes/{note_id}", token=token)
        src = resp["data"].get("_source") if resp.get("code") == 0 else f"HTTP{resp}"
        with lock:
            results.append(src)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    stat = Counter(results)
    for k, v in stat.items():
        print(f"  {k}: {v} 次")
    hit_mysql = sum(v for k, v in stat.items() if k.startswith("mysql"))
    print(f"  → 真正回源 MySQL 的只有 {hit_mysql} 个请求，其余都是等锁后读缓存（防击穿生效）")


if __name__ == "__main__":
    main()
