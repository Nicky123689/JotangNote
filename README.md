# JotangNote

焦糖工作室 2026 招新 · 后端方向作业仓库。

## 这个仓库里有什么

```text
JotangNote/
├── README.md                 # 仓库总体简介（本文件）
├── Notes/                    # 学习笔记（每题的问题回答 + 学习过程）
│   ├── 开发环境.md            # Part 1：语言、IDE、两个 Hello World
│   ├── MySQL.md              # MySQL 三问
│   ├── Redis.md              # Redis 三问
│   ├── RabbitMQ.md           # RabbitMQ 两问
│   ├── AI-Agent.md           # AI Agent 两问
│   └── HTTP-API-JSON-HTTPS.md# HTTP / API / JSON / HTTPS
└── Project/                  # JotangNote 项目本体
    ├── requirements.txt
    ├── src/                  # 源码
    └── docs/                 # 项目说明文档（含运行截图）
```

## 目前进度

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 启蒙篇 | 开发环境（Hello World 终端 + FastAPI /hello）、常用技术栈笔记 | 已完成 |
| 入门篇 | MySQL 增删改查与登录、Redis 缓存、RabbitMQ 异步 | 进行中 |
| 进阶篇 | 接入 AI API、会话管理、Tool Use | 未开始 |

## 怎么把项目跑起来

```bash
# 1. 建虚拟环境并装依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -r Project/requirements.txt

# 2. 启动服务（默认 8080 端口）
cd Project/src
uvicorn main:app --host 0.0.0.0 --port 8080

# 3. 浏览器访问
#    http://localhost:8080/hello  → Hello World From Web Application!
#    http://localhost:8080/docs   → FastAPI 自动生成的接口文档
```

> 🤖 AI 使用说明：本仓库的代码与笔记由本人使用 Hermes Agent（AI Agent）协助完成，
> 招新题允许使用 AI，所有代码均在本地实际运行验证（见 `Project/docs/` 下截图）。
