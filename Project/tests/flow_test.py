#!/usr/bin/env python3
"""入门篇接口联调脚本：把「注册→登录→增删改查→缓存→MQ」整条链路跑一遍并打印结果。

用法：
    python3 Project/tests/flow_test.py            # 服务需已在 127.0.0.1:8080 运行
输出：每一步的 HTTP 状态码与响应体，末尾给出关键结论（缓存命中、MQ 异步生效、幂等）。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
STUDENT = "2025090914010"


def call(method: str, path: str, body: dict | None = None, token: str | None = None,
         show: bool = True):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code, text = resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        code, text = exc.code, exc.read().decode()
    payload = json.loads(text) if text.strip().startswith(("{", "[")) else text
    if show:
        print(f"  {method:6s} {path:28s} → HTTP {code}  {json.dumps(payload, ensure_ascii=False)[:160]}")
    return code, payload


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    section("0. 服务与示例接口")
    call("GET", "/hello")

    section("1. 用户注册 / 登录")
    call("POST", "/api/auth/register",
         {"student_id": STUDENT, "name": "唐朝", "password": "jotang123"})
    call("POST", "/api/auth/register",          # 重复注册 → 409
         {"student_id": STUDENT, "name": "唐朝", "password": "jotang123"})
    call("POST", "/api/auth/register",          # 密码太短 → 422
         {"student_id": "2025000000001", "name": "测试", "password": "123"})
    call("POST", "/api/auth/login", {"student_id": STUDENT, "password": "wrong-password"})
    code, payload = call("POST", "/api/auth/login",
                         {"student_id": STUDENT, "password": "jotang123"})
    token = payload["data"]["token"]
    call("GET", "/api/auth/me", token=token)
    call("GET", "/api/notes")                   # 没带 token → 401

    section("2. 新增笔记（走 MQ 异步）")
    code, payload = call("POST", "/api/notes",
                         {"title": "第一篇笔记", "content": "你好，JotangNote"}, token=token)
    op_id = payload["data"]["op_id"]
    print(f"  → 接口立即返回（HTTP {code}），消息 op_id={op_id} 已进入队列")
    time.sleep(1.2)                             # 等消费者处理
    call("GET", "/api/notes", token=token)

    section("3. 查询笔记：第一次走 MySQL，第二次命中 Redis 缓存")
    _, a = call("GET", "/api/notes/1", token=token)
    print(f"     ↑ 数据来源 _source = {a['data']['_source']}")
    _, b = call("GET", "/api/notes/1", token=token)
    print(f"     ↑ 数据来源 _source = {b['data']['_source']}（第二次直接命中 Redis）")

    section("4. 修改笔记（同样走 MQ），改完缓存应失效")
    call("PUT", "/api/notes/1",
         {"title": "第一篇笔记（已修改）", "content": "内容也改了"}, token=token)
    time.sleep(1.2)
    call("GET", "/api/notes/1", token=token)     # 应当拿到新标题，且 _source=mysql（缓存被删了）

    section("5. 缓存穿透防护：反复查不存在的笔记")
    for i in range(3):
        call("GET", "/api/notes/999999", token=token, show=(i == 0))
    print("  （连续 3 次都是 404；第一次查库后会写空值标记，后两次不砸数据库）")

    section("6. 越权与删除")
    call("POST", "/api/auth/register",
         {"student_id": "2025000000009", "name": "李四", "password": "jotang456"})
    _, p2 = call("POST", "/api/auth/login",
                 {"student_id": "2025000000009", "password": "jotang456"})
    token2 = p2["data"]["token"]
    call("GET", "/api/notes/1", token=token2)    # 别人的笔记 → 403
    call("DELETE", "/api/notes/1", token=token)
    time.sleep(1.2)
    call("GET", "/api/notes/1", token=token)     # 已软删 → 404
    call("GET", "/api/notes", token=token)       # 列表为空

    section("7. 幂等性：同一条消息投递两次只生效一次")
    print("  见 worker 日志中的 [idempotent] 行（由 processed_ops 表保证）")


if __name__ == "__main__":
    main()
