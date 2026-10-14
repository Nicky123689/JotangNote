"""给 AI 用的工具（Tool / Function Calling）。

现在只有一个工具：**根据笔记 ID 查询笔记全文**。
关键点：
1. schema 要按接口文档的格式写清楚（名字、描述、参数类型），模型靠描述决定什么时候用它；
2. 执行时**必须再检查权限**——不能让 AI（或提示词注入）通过工具去读别人的笔记。
"""

from __future__ import annotations

import json

import db

# 放在请求体里的工具清单
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_note",
            "description": "根据笔记 ID 查询当前用户自己的某篇笔记全文（包含标题和正文）。"
                           "当用户要求总结、改写、精简某篇笔记，或提到某篇笔记的内容时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "integer",
                        "description": "笔记 ID（数字），可以在用户消息或笔记列表中找到",
                    }
                },
                "required": ["note_id"],
            },
        },
    }
]


def query_note(user_id: int, note_id: int) -> dict:
    """真正执行查询：只允许查自己的、未删除的笔记。"""
    row = db.query_one(
        "SELECT id, title, content, created_at, updated_at FROM notes "
        "WHERE id=%s AND user_id=%s AND deleted_at IS NULL",
        (note_id, user_id),
    )
    if row is None:
        return {"error": "没有找到这篇笔记（可能不存在，或者不属于当前用户）"}
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def run_tool(name: str, arguments: str, user_id: int) -> str:
    """按模型给的函数名和参数执行工具，返回给模型的字符串结果。"""
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return json.dumps({"error": f"参数不是合法 JSON：{arguments}"}, ensure_ascii=False)

    if name == "query_note":
        try:
            note_id = int(args.get("note_id"))
        except (TypeError, ValueError):
            return json.dumps({"error": "note_id 必须是整数"}, ensure_ascii=False)
        return json.dumps(query_note(user_id, note_id), ensure_ascii=False)

    return json.dumps({"error": f"未知工具：{name}"}, ensure_ascii=False)
