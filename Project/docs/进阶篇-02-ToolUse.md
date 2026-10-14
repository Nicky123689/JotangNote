# 进阶篇 02 · 自己搓一个 Tool 给 AI 用（Tool Use / Function Calling）

> 这一节让 AI 能**自己决定**去读用户的某篇笔记，再基于真实内容回答——
> 也就是题目里说的 Tool Use；用户全程只看到最终回答，看不到中间的 JSON。

## 一、机制：一次对话其实可能来回两趟

```text
用户：帮我总结第 5 号笔记
        │
        ▼
① 请求里带上 tools 清单（query_note 的 schema）
        │
        ▼
② 模型不回文本，而是返回  tool_calls: [{id, function:{name:"query_note", arguments:'{"note_id":5}'}}]
        │
        ▼
③ 我们的代码真的去数据库查这篇笔记（并检查是不是他自己的）
        │
        ▼
④ 把结果作为一条 role=tool 的消息回喂给模型（带上 tool_call_id 对应）
        │
        ▼
⑤ 模型这次给出**最终回答**（总结），保存进会话，返回给用户
```

“用户看不见中间过程”是我们自己保证的：接口只在最后返回 `reply`；
中间那条 `tool_calls` 和 `tool` 结果只进会话历史（所以也要求“计入上下文”——本项目就存在 `chat_messages` 表里）。

## 二、工具 schema（`Project/src/tools.py`）

```python
TOOLS = [{
    "type": "function",
    "function": {
        "name": "query_note",
        "description": "根据笔记 ID 查询当前用户自己的某篇笔记全文（包含标题和正文）。"
                       "当用户要求总结、改写、精简某篇笔记，或提到某篇笔记的内容时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "note_id": {"type": "integer", "description": "笔记 ID（数字）"}
            },
            "required": ["note_id"],
        },
    },
}]
```

**描述写得好不好，直接决定模型会不会正确调用它**：要写清“这个工具做什么”（查笔记全文）、
“什么时候用”（用户要总结/改写/提到笔记内容时）、参数是什么类型。
不写“什么时候用”，模型可能选择自己编一段内容而不去查。

## 三、执行工具时的两个重点

```python
def query_note(user_id: int, note_id: int) -> dict:
    row = db.query_one(
        "SELECT id, title, content, created_at, updated_at FROM notes "
        "WHERE id=%s AND user_id=%s AND deleted_at IS NULL", (note_id, user_id))
    if row is None:
        return {"error": "没有找到这篇笔记（可能不存在，或者不属于当前用户）"}
    return {...}
```

1. **权限必须由后端再判一次**：`user_id=%s` 这个条件来自登录态，不是模型给的。
   模型（或恶意提示词）可能会要求读别人的笔记，服务端必须挡住——**不能把鉴权交给模型**。
2. **出错也要回给模型**：查不到就返回 `{"error": ...}`，模型会据此告诉用户“没找到这篇笔记”，
   而不是自己瞎编。

## 四、功能使用流程（含截图）

`Project/tests/chat_test.py` 第 4 步（打开 `debug` 才返回轨迹，正常聊天用户看不到）：

- 用户说：“帮我总结一下第 5 号笔记的重点，用三行以内”
- 后台轨迹：第 1 轮调用 `query_note({"note_id": 5})`，返回笔记全文；
- 用户看到的是：总结后的三行要点（没有 JSON）。

![Tool Use 测试与轨迹](img/jj-chat-test.png)

前端页面上同一次对话的样子（用户只看到最终回答）：

![前端页面里的工具调用结果](img/jj-ui-chat.png)

## 五、测试过程与结果

| 用例 | 期望 | 实际 |
| --- | --- | --- |
| 请求体带 tools schema | 模型按需返回 tool_calls | ✅ `query_note({"note_id": 5})` |
| 解析 tool_calls 并执行 | 真去数据库查 | ✅ 返回笔记全文（title/content） |
| 回喂结果让模型总结 | 模型基于真实内容回答 | ✅ 总结出的要点与笔记内容一致 |
| 用户看不到中间 JSON | 只返回 reply | ✅ 接口响应里只有 `reply`（轨迹仅在 debug 时返回） |
| 工具调用计入上下文 | 历史里能看到 assistant(tool_calls) 与 tool 消息 | ✅ 见 `chat_messages` 表 |
| 越权调用 | 只能查自己的笔记 | ✅ SQL 里强制 `user_id=%s` |

数据库里能看到完整的调用痕迹：

```bash
$ mysql -h127.0.0.1 -P3307 -ujotang -p jotangnote \
    -e "SELECT id,role,LEFT(IFNULL(content,raw),50) c FROM chat_messages WHERE session_id=1 ORDER BY id;"
# assistant 行的 raw 列里就是那一串 tool_calls，tool 行是工具返回的笔记全文
```

## 六、我的理解

- **Tool Use 的本质是“模型只负责决定调用哪个函数、参数是什么”，执行永远在我们手里**。
  这也解释了为什么 Agent 危险与否取决于我们给了它什么工具、有没有权限校验。
- **工具描述是接口的一部分**：schema 写得含糊，模型就会乱调或干脆不调。
- **别把鉴权交给模型**：模型可以做决策，但“能不能访问这条数据”必须由后端根据登录态判断。
- 下一步可以加的工具有：`search_notes(keyword)`（按关键词找笔记）、`create_note(title, content)`（让 AI 帮你记一笔），
  甚至 `delete_note`——不过写操作最好加一道“向用户确认”的流程。

> 🤖 AI 使用说明：本节代码与文字由本人使用 Hermes Agent 协助完成，工具调用轨迹与截图均为本地真实运行结果。
