# HTTP / API / JSON / HTTPS 笔记

## 一、HTTP 请求 & 响应

### 1. 一个标准的 HTTP 请求和响应都有哪些部分？

**请求（客户端 → 服务器）**：

```text
POST /api/notes HTTP/1.1            ← 请求行：方法 + 路径 + 协议版本
Host: localhost:8080                ← 请求头：关于这次请求的元信息
Content-Type: application/json
Authorization: Bearer <token>
Content-Length: 68
                                    ← 空行：分隔头和正文
{"title":"标题","content":"正文"}    ← 请求体（body）：真正要传的数据
```

- **请求行**：用什么方法、请求哪个资源、HTTP 版本。
- **请求头**：Host、Content-Type、Content-Length、Cookie/Authorization、User-Agent、Accept 等。
- **请求体**：只有需要带数据的方法（POST/PUT/PATCH）才有；GET 通常没有。

**响应（服务器 → 客户端）**：

```text
HTTP/1.1 201 Created                ← 状态行：版本 + 状态码 + 原因短语
Content-Type: application/json      ← 响应头
Location: /api/notes/12

{"code":0,"data":{"id":12}}         ← 响应体
```

- **状态行**：状态码告诉客户端“结果怎么样”。
- **响应头**：内容类型、长度、缓存策略（Cache-Control）、Set-Cookie 等。
- **响应体**：结果数据（HTML/JSON/图片……）。

### 2. 提交一篇刚写好的长篇笔记，用 GET 还是 POST？

**必须用 POST**（或 PUT/PATCH），理由：

1. **语义**：GET 的语义是“读取资源”，按 HTTP 规范它应当是**幂等且安全**的（多次请求不改变服务器状态）。
   提交笔记是“创建/修改”，语义上就不属于 GET。
2. **长度限制**：GET 的参数在 URL 里，URL 长度受浏览器和服务器限制（常见几 KB），
   **长篇笔记根本放不下**；POST 把数据放在请求体里，理论上没有这个限制。
3. **敏感与可读性**：URL 会出现在浏览器历史、代理日志、服务器访问日志里；
   正文放 URL 会又长又不安全。请求体不会被默认记录成 URL。
4. **编码问题**：URL 里要处理转义，长文本转义又丑又容易出错；请求体可以配合
   `Content-Type: application/json; charset=utf-8` 明确编码。

**结论**：读用 GET，写用 POST（新增）/ PUT、PATCH（整体或局部更新）/ DELETE（删除）。

### 3. HTTP 状态码是什么？`JotangNote` 里会在什么情况下用到哪些？

状态码是三位数，第一位表示类别：`2xx` 成功、`3xx` 重定向、`4xx` 客户端错误、`5xx` 服务端错误。

| 状态码 | 含义 | 在 JotangNote 里的场景 |
| --- | --- | --- |
| 200 OK | 成功 | 查询笔记详情成功 |
| 201 Created | 创建成功 | 新增笔记成功（并在 `Location` 里给出新资源地址） |
| 204 No Content | 成功但无返回体 | 删除笔记成功 |
| 400 Bad Request | 请求格式不对 | 请求体不是合法 JSON、字段类型不对 |
| 401 Unauthorized | 未认证 | 没带 token、token 过期 → 前端跳登录页 |
| 403 Forbidden | 已认证但无权限 | 登录了，但要改别人的笔记 |
| 404 Not Found | 资源不存在 | 查一篇已被删除/不存在的笔记 |
| 409 Conflict | 冲突 | 注册时学号已被占用 |
| 422 Unprocessable Entity | 参数校验不通过 | FastAPI（Pydantic）校验失败：密码太短、标题为空 |
| 429 Too Many Requests | 请求过频 | 限制刷接口（配合 Redis 计数做限流） |
| 500 Internal Server Error | 服务端异常 | 代码抛未捕获异常（如数据库连接断了） |
| 503 Service Unavailable | 服务暂不可用 | 正在重启、依赖的数据库不可用 |

**实践要点**：错误时不要一律返回 200 再在 body 里写 `{"code":-1}`——
状态码本身就是给客户端和监控用的“机器可读结论”。我们的项目里会**两者结合**：
状态码表示 HTTP 层结果，body 里的 `code` 表示业务层结果。

## 二、接口 / API

### 设计“获取某篇笔记详细内容”的接口，要考虑什么？

```text
GET /api/notes/{note_id}
Authorization: Bearer <token>
→ 200 {"code":0,"data":{"id":12,"title":"...","content":"...","created_at":"..."}}
```

要定清楚这些事：

1. **命名与风格**：资源用名词复数（`/notes`），不要在 URL 里放动词；查询参数用于过滤/分页。
2. **方法**：读取用 GET。
3. **参数怎么传**：笔记 ID 属于“定位资源”，放**路径参数**（`/notes/12`）而不是查询参数
   （`/notes?id=12`）——前者更符合 REST 语义，也便于缓存和日志统计。
4. **认证与鉴权**：需要登录（401）；并且**只能看自己的笔记**（或公开的），
   否则返回 403——这一步最容易漏，漏了就是越权漏洞。
5. **返回结构**：统一包一层 `{code, message, data}`，成功/失败结构一致，前端好处理；
   字段名、时间格式（ISO 8601）、空值怎么表示都要约定好。
6. **返回哪些字段**：详情接口返回正文；但列表接口不要返回正文（太大），
   并且要排除敏感字段（如用户密码哈希）。
7. **错误码**：404（笔记不存在）、400（id 不是数字）、401/403（没登录/没权限），各自语义明确。
8. **性能与缓存**：是否需要缓存（Redis）、热点数据的过期策略、返回体是否压缩。
9. **幂等与并发**：详情查询天然幂等；如果是更新接口，要约定并发修改怎么处理（版本号/时间戳）。
10. **文档**：接口路径、参数、响应示例写进文档（FastAPI 会自动生成 Swagger 文档）。

## 三、JSON

### 1. JSON 长什么样？

JSON 只有六种值：对象 `{}`、数组 `[]`、字符串、数字、布尔、`null`。
键必须是双引号字符串，不能有注释，不能有多余逗号。

```json
{
  "code": 0,
  "data": {
    "id": 12,
    "title": "第一篇笔记",
    "tags": ["学习", "后端"],
    "published": true,
    "deleted_at": null,
    "created_at": "2026-10-14T15:30:00+08:00"
  }
}
```

### 2. Python 里怎么互转？

```python
import json

note = {"id": 12, "title": "第一篇笔记", "tags": ["学习"], "published": True, "deleted_at": None}

# 对象 → JSON 字符串
text = json.dumps(note, ensure_ascii=False, indent=2)
print(text)

# JSON 字符串 → 对象
obj = json.loads(text)
print(obj["tags"][0])

# 读写文件
with open("note.json", "w", encoding="utf-8") as f:
    json.dump(note, f, ensure_ascii=False, indent=2)
with open("note.json", encoding="utf-8") as f:
    print(json.load(f))
```

注意点：

- `ensure_ascii=False` 才会输出中文而不是 `\u7b2c`。
- Python 的 `True/False/None` 在 JSON 里是 `true/false/null`，`dumps` 会自动转换。
- 时间对象（`datetime`）不能直接序列化，要么先转成字符串，要么自定义 `default=` 处理。
- 在 FastAPI 里这件事是**自动**做的：声明 `Pydantic` 模型，框架负责
  “请求体 JSON → Python 对象”和“Python 对象 → 响应 JSON”的双向转换与校验。

## 四、HTTPS

### HTTPS 的加密过程是怎么样的？

HTTPS = HTTP + TLS，在 HTTP 之下加了一层加密通道。一次完整的过程（简化版 TLS 1.3）：

1. **客户端打招呼（Client Hello）**：说明自己支持的 TLS 版本、加密套件，并给出一个随机数。
2. **服务器回应（Server Hello）**：选定加密套件，给出自己的随机数，并出示**证书**
   （证书里含服务器公钥、域名、有效期、以及 CA 的签名）。
3. **验证证书**：客户端用系统内置的根证书验证这张证书是不是**可信 CA 签发的**、
   域名对不对、有没有过期。验证不过就直接报错（这就是“证书不受信任”的由来）。
4. **协商出会话密钥**：
   - TLS 1.3 用 **ECDHE（临时密钥交换）**：双方各自生成临时密钥对、交换公钥，
     通过 Diffie-Hellman 计算出**同一个**共享密钥。因为用的是临时密钥，
     即使服务器的长期私钥以后泄露，也解不开过去的流量（前向保密）。
   - 这一步用到非对称加密（公钥/私钥）——它只用来**安全地协商密钥**，因为非对称加密很慢。
5. **切换成对称加密通信**：之后所有 HTTP 数据都用协商出的**会话密钥 + 对称加密**
   （如 AES-GCM/ChaCha20）加密传输，同时用 MAC/AEAD 保证完整性（防篡改）。
6. **会话复用**：短时间内重连可以复用会话票据（Session Ticket），省掉完整的握手开销。

两句话记住：

- **非对称加密只负责“安全地商量出一把钥匙”**，真正的数据用**对称加密**传（快）；
- 证书的作用是**证明“我真的是那个网站”**，防止中间人冒充。

**在 JotangNote 里的意义**：登录接口的密码、token 都属于敏感信息，
如果裸 HTTP 传输，同一个网络里的人（尤其是公共 WiFi）可以直接抓包看到。
生产环境必须上 HTTPS（用 Nginx/Caddy 配证书，或者把项目部署在带 HTTPS 的平台上）。

> 🤖 AI 使用说明：本节内容由本人使用 Hermes Agent 协助整理，其中 HTTP/JSON 部分在本地实际调用
> `/hello`、`/docs` 接口和 `json.dumps/loads` 验证过。
