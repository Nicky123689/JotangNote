#!/usr/bin/env python3
"""进阶篇联调：/chat 接口 + 会话管理 + Tool Use。

用法：python3 Project/tests/chat_test.py
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
STUDENT = "2025090914010"


def call(method, path, body=None, token=None, quiet=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def section(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


def main():
    _, p = call("POST", "/api/auth/login", {"student_id": STUDENT, "password": "jotang123"})
    token = p["data"]["token"]

    section("1. 准备一篇笔记（给 Tool 用）")
    call("POST", "/api/notes", {
        "title": "读《代码整洁之道》",
        "content": ("今天读了《代码整洁之道》。作者反复强调：命名要准确，函数要短小，"
                    "注释要解释为什么而不是做什么。我打算下周把项目里那几个超长函数拆开，"
                    "并且把 temp、data 这类含糊的变量名改掉。"),
    }, token=token)
    time.sleep(1.2)
    notes = call("GET", "/api/notes", token=token)[1]["data"]
    note_id = notes[0]["id"]
    print(f"  已创建笔记 #{note_id}：{notes[0]['title']}")

    section("2. 第一次对话（无工具调用）")
    code, r = call("POST", "/api/chat", {"message": "你好，请用一句话介绍你自己"}, token=token)
    session = r["data"]["session_id"]
    print(f"  HTTP {code} | session_id = {session}")
    print(f"  AI：{r['data']['reply']}")

    section("3. 会话管理：第二句直接问“我刚才说了什么”")
    _, r2 = call("POST", "/api/chat",
                 {"message": "我刚才那句话说了什么？", "session_id": session}, token=token)
    print(f"  AI：{r2['data']['reply']}")
    print("  → 能答上来就说明历史消息被带进上下文了（AI 自己是没有记忆的）")

    section("4. Tool Use：让它总结那篇笔记（用户看不到中间的 JSON）")
    _, r3 = call("POST", "/api/chat",
                 {"message": f"帮我总结一下第 {note_id} 号笔记的重点，用三行以内",
                  "session_id": session, "debug": True}, token=token)
    print(f"  AI：{r3['data']['reply']}")
    print("  ---- 工具调用轨迹（debug 才返回，正常对话里用户看不到）----")
    for t in r3["data"].get("tool_trace") or []:
        print(f"  第{t['round']}轮 调用 {t['tool']}({t['arguments']})")
        print(f"        返回：{t['result_preview'][:120]}…")

    section("5. 会话持久化：把历史从数据库读出来（进程重启也不会丢）")
    _, h = call("GET", f"/api/chat/sessions/{session}", token=token)
    for m in h["data"]:
        content = (m["content"] or "")[:60].replace("\n", " ")
        print(f"  [{m['role']:9s}] {content}")
    _, s = call("GET", "/api/chat/sessions", token=token)
    print(f"  该用户的会话数：{len(s['data'])}")


if __name__ == "__main__":
    main()
