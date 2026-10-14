# JotangNote

焦糖工作室 2026 招新 · 后端方向作业仓库。

## 这个仓库里有什么

```text
JotangNote/
├── README.md                     # 仓库总体简介（本文件）
├── Notes/                        # 学习笔记（每部分的问题回答 + 学习过程）
│   ├── 开发环境.md                # Part 1：语言、IDE、两个 Hello World
│   ├── MySQL.md                  # MySQL 三问
│   ├── Redis.md                  # Redis 三问
│   ├── RabbitMQ.md               # RabbitMQ 两问
│   ├── AI-Agent.md               # AI Agent 两问
│   └── HTTP-API-JSON-HTTPS.md    # HTTP / API / JSON / HTTPS
└── Project/
    ├── requirements.txt
    ├── src/                      # 源码
    │   ├── main.py               # FastAPI 入口（认证 + 笔记接口）
    │   ├── config.py             # 配置（全部从环境变量读）
    │   ├── db.py                 # MySQL 连接池 + 建表
    │   ├── cache.py              # Redis 缓存与会话
    │   ├── mq.py                 # RabbitMQ 生产者
    │   ├── worker.py             # RabbitMQ 消费者（真正执行增删改）
    │   ├── security.py           # 密码哈希与 token
    │   └── hello_terminal.py     # 启蒙篇：终端 Hello World
    ├── tests/                    # 联调脚本（会打印完整流程，可当测试证据）
    │   ├── flow_test.py          # 注册→登录→增删改查 全流程
    │   ├── cache_test.py         # 缓存命中 / 穿透 / 击穿
    │   └── idempotent_test.py    # MQ 幂等性
    └── docs/                     # 项目说明文档（含运行截图）
        ├── 入门篇-01-MySQL笔记与用户.md
        ├── 入门篇-02-Redis缓存.md
        ├── 入门篇-03-RabbitMQ异步.md
        └── img/
```

## 进度

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 启蒙篇 | 开发环境（两个 Hello World）、常用技术栈笔记 | ✅ 完成 |
| 入门篇 | MySQL 增删改查与用户登录、Redis 缓存（含防穿透/击穿）、RabbitMQ 异步（含顺序性/幂等性） | ✅ 完成 |
| 进阶篇 | 接入 AI API、会话管理、Tool Use | 未开始 |

## 技术栈与依赖的服务

- Web 框架：**FastAPI**（Python 3.14）+ uvicorn
- 数据库：**MySQL 8.4**（本项目跑在 3307 端口——本机 3306 被 Windows 侧的 MySQL 占用了）
- 缓存 / 会话：**Redis 8**
- 消息队列：**RabbitMQ 4**
- 密码存储：PBKDF2-HMAC-SHA256 + 每用户独立盐（标准库 `hashlib`）

## 怎么把项目跑起来

```bash
# 0. 起三个后台服务（WSL 里）
sudo systemctl start mysql redis-server rabbitmq-server

# 1. 建虚拟环境、装依赖
python3 -m venv ~/venvs/jotangnote && source ~/venvs/jotangnote/bin/activate
pip install -r Project/requirements.txt

# 2. 配数据库（只需一次）
sudo mysql -e "CREATE DATABASE IF NOT EXISTS jotangnote CHARACTER SET utf8mb4;"
sudo mysql -e "CREATE USER IF NOT EXISTS 'jotang'@'127.0.0.1' IDENTIFIED BY '你的密码';"
sudo mysql -e "GRANT ALL PRIVILEGES ON jotangnote.* TO 'jotang'@'127.0.0.1';"
export JOTANG_MYSQL_PASSWORD='你的密码'      # 代码里不写密码

# 3. 起 API（表会自动创建）
cd Project/src && uvicorn main:app --host 0.0.0.0 --port 8080

# 4. 另开一个终端起消费者（异步写库靠它）
cd Project/src && python worker.py
```

浏览器访问：

- `http://localhost:8080/hello` → `Hello World From Web Application!`
- `http://localhost:8080/docs` → FastAPI 自动生成的接口文档

跑联调（三个脚本会打印每一步的状态码和响应，可直接当测试证据）：

```bash
python Project/tests/flow_test.py
python Project/tests/cache_test.py
python Project/tests/idempotent_test.py
```

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/hello` | 启蒙篇示例接口 |
| POST | `/api/auth/register` | 注册（密码加盐哈希后入库） |
| POST | `/api/auth/login` | 登录（返回 token，存 Redis） |
| GET | `/api/auth/me` | 当前登录用户 |
| POST | `/api/auth/logout` | 退出登录（删掉 Redis 里的会话） |
| POST | `/api/notes` | 新增笔记 → 投 MQ，返回 202 |
| GET | `/api/notes` | 我的笔记列表 |
| GET | `/api/notes/{id}` | 查一篇笔记（Redis 缓存旁路 + 防穿透/击穿） |
| PUT | `/api/notes/{id}` | 修改笔记 → 投 MQ，返回 202 |
| DELETE | `/api/notes/{id}` | 删除笔记（软删）→ 投 MQ，返回 202 |

> 🤖 AI 使用说明：本仓库的代码与笔记由本人使用 Hermes Agent（AI Agent）协助完成。
> 招新题允许使用 AI，所有接口、截图与测试结果均为本地实际运行所得，
> 详见 `Project/docs/` 各文件末尾的 AI 使用说明。
