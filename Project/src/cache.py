"""Redis：笔记查询缓存 + 登录会话。

这里实现了三个经典的缓存处理：
1. 缓存旁路（Cache-Aside）：先查缓存 → 未命中查 MySQL → 回填缓存；
2. 缓存穿透：查到「数据库里也没有」时，写一个短暂的空值标记，避免反复砸数据库；
3. 缓存击穿：热门 key 过期瞬间，用 Redis 的 SET NX 抢一把互斥锁，只让一个请求去查库。
"""

from __future__ import annotations

import json
import time

import redis

from config import (
    EMPTY_CACHE_TTL,
    LOCK_TTL,
    NOTE_CACHE_TTL,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
)

_pool = redis.ConnectionPool(
    host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True
)


def client() -> redis.Redis:
    return redis.Redis(connection_pool=_pool)


# ---------------- 笔记缓存 ----------------

def note_key(note_id: int) -> str:
    return f"note:{note_id}"


def get_cached_note(note_id: int):
    """返回 (命中?, 笔记)。空值标记命中时返回 (True, None)。"""
    raw = client().get(note_key(note_id))
    if raw is None:
        return False, None
    if raw == "__EMPTY__":
        return True, None          # 命中的是「不存在」的标记
    return True, json.loads(raw)


def set_cached_note(note_id: int, note: dict) -> None:
    client().set(note_key(note_id), json.dumps(note, ensure_ascii=False, default=str),
                 ex=NOTE_CACHE_TTL)


def set_empty_mark(note_id: int) -> None:
    """防穿透：数据库里也没有，就在缓存里插一个短暂的空值标记。"""
    client().set(note_key(note_id), "__EMPTY__", ex=EMPTY_CACHE_TTL)


def invalidate_note(note_id: int) -> None:
    """写操作后删缓存（Cache-Aside 的标准做法：改数据库，然后让缓存失效）。"""
    client().delete(note_key(note_id))


def acquire_rebuild_lock(note_id: int) -> bool:
    """防击穿：只让一个请求去重建缓存，其余请求稍后重试缓存。"""
    return bool(client().set(f"lock:note:{note_id}", "1", nx=True, ex=LOCK_TTL))


def release_rebuild_lock(note_id: int) -> None:
    client().delete(f"lock:note:{note_id}")


def wait_for_cache(note_id: int, timeout: float = 2.0) -> bool:
    """等别的请求把缓存建好。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hit, _ = get_cached_note(note_id)
        if hit:
            return True
        time.sleep(0.05)
    return False


# ---------------- 登录会话 ----------------

def save_session(token: str, user_id: int, ttl: int = 7 * 24 * 3600) -> None:
    client().set(f"session:{token}", user_id, ex=ttl)


def get_session_user(token: str):
    value = client().get(f"session:{token}")
    return int(value) if value else None


def drop_session(token: str) -> None:
    client().delete(f"session:{token}")
