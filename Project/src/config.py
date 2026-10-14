"""集中读取配置。真实项目里这些值从环境变量来，绝不写进代码或提交到仓库。"""

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# ---- MySQL ----
MYSQL_HOST = os.environ.get("JOTANG_MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = _int("JOTANG_MYSQL_PORT", 3307)          # 本机 3306 被 Windows 侧的 MySQL 占用，见 Notes/开发环境.md
MYSQL_USER = os.environ.get("JOTANG_MYSQL_USER", "jotang")
# 注意：密码**不写默认值**，必须由环境变量提供（避免把口令提交进仓库）
MYSQL_PASSWORD = os.environ.get("JOTANG_MYSQL_PASSWORD", "")
MYSQL_DB = os.environ.get("JOTANG_MYSQL_DB", "jotangnote")

# ---- Redis ----
REDIS_HOST = os.environ.get("JOTANG_REDIS_HOST", "127.0.0.1")
REDIS_PORT = _int("JOTANG_REDIS_PORT", 6379)
REDIS_DB = _int("JOTANG_REDIS_DB", 0)

# ---- RabbitMQ ----
RABBITMQ_HOST = os.environ.get("JOTANG_RABBITMQ_HOST", "127.0.0.1")
RABBITMQ_PORT = _int("JOTANG_RABBITMQ_PORT", 5672)
RABBITMQ_USER = os.environ.get("JOTANG_RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.environ.get("JOTANG_RABBITMQ_PASSWORD", "guest")
NOTE_QUEUE = os.environ.get("JOTANG_NOTE_QUEUE", "note.ops")

# ---- 缓存策略 ----
NOTE_CACHE_TTL = _int("JOTANG_NOTE_CACHE_TTL", 300)      # 笔记缓存 5 分钟
EMPTY_CACHE_TTL = _int("JOTANG_EMPTY_CACHE_TTL", 60)     # 防穿透的空值标记 60 秒
LOCK_TTL = _int("JOTANG_LOCK_TTL", 5)                    # 防击穿的互斥锁 5 秒
