"""AI 客户端：调用 DeepSeek 的 OpenAI 兼容接口（也可以换成 MiMo 等任何兼容服务）。

- API key 只从环境变量读，**绝不写进代码或提交**（DEEPSEEK_API_KEY / JOTANG_AI_API_KEY）；
- 支持 tools（Function Calling）：把 tool 的 schema 放进请求体，模型会返回 tool_calls。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_BASE = os.environ.get("JOTANG_AI_BASE", "https://api.deepseek.com")
API_MODEL = os.environ.get("JOTANG_AI_MODEL", "deepseek-chat")
API_KEY = os.environ.get("JOTANG_AI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
TIMEOUT = int(os.environ.get("JOTANG_AI_TIMEOUT", 90))


class AIError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(API_KEY)


def chat(messages: list[dict], tools: list[dict] | None = None,
         temperature: float = 0.7, max_tokens: int = 1024) -> dict:
    """发一次对话请求，返回模型返回的 message 对象（可能含 tool_calls）。"""
    if not API_KEY:
        raise AIError("未配置 API key：请设置环境变量 JOTANG_AI_API_KEY（或 DEEPSEEK_API_KEY）")

    body: dict = {
        "model": API_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"      # 让模型自己决定要不要调用工具

    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise AIError(f"AI 接口返回 HTTP {exc.code}：{detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise AIError(f"调用 AI 接口失败：{exc}") from exc

    return payload["choices"][0]["message"]
