"""MySQL 连接与建表。

- 用连接池（DBUtils 的 PooledDB）而不是每次新建连接；
- 所有 SQL 一律参数化，避免 SQL 注入；
- 建表语句集中在 ensure_schema() 里，服务启动时执行（幂等）。
"""

from __future__ import annotations

import pymysql
from dbutils.pooled_db import PooledDB

from config import (
    MYSQL_DB,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
)

_pool: PooledDB | None = None


def get_pool() -> PooledDB:
    global _pool
    if _pool is None:
        _pool = PooledDB(
            creator=pymysql,
            maxconnections=10,
            mincached=1,
            blocking=True,
            ping=1,
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
            charset="utf8mb4",
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )
    return _pool


def query_all(sql: str, args: tuple = ()) -> list[dict]:
    conn = get_pool().connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()
    finally:
        conn.close()


def query_one(sql: str, args: tuple = ()) -> dict | None:
    rows = query_all(sql, args)
    return rows[0] if rows else None


def execute(sql: str, args: tuple = ()) -> int:
    """执行写操作，返回受影响行数。"""
    conn = get_pool().connection()
    try:
        with conn.cursor() as cur:
            affected = cur.execute(sql, args)
        conn.commit()
        return affected
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_returning_id(sql: str, args: tuple = ()) -> int:
    """插入并返回自增主键（给同步路径用，比如注册）。"""
    conn = get_pool().connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            new_id = cur.lastrowid
        conn.commit()
        return int(new_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = [
    # 用户表
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        student_id VARCHAR(32) NOT NULL UNIQUE COMMENT '学号，登录用',
        name VARCHAR(64) NOT NULL COMMENT '昵称',
        password_hash VARCHAR(255) NOT NULL COMMENT 'PBKDF2 哈希，绝不存明文',
        salt VARCHAR(64) NOT NULL COMMENT '每个用户独立的盐',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_users_student_id (student_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表'
    """,
    # 笔记表
    """
    CREATE TABLE IF NOT EXISTS notes (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL COMMENT '作者',
        title VARCHAR(120) NOT NULL,
        content MEDIUMTEXT NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        deleted_at DATETIME NULL COMMENT '软删除时间，NULL 表示未删除',
        INDEX idx_notes_user_deleted (user_id, deleted_at),
        INDEX idx_notes_created (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='笔记表'
    """,
    # 已处理消息表：MQ 幂等性用（消息重复投递时不会重复执行）
    """
    CREATE TABLE IF NOT EXISTS processed_ops (
        op_id VARCHAR(64) PRIMARY KEY COMMENT '消息唯一 ID',
        note_id BIGINT NULL,
        op VARCHAR(16) NOT NULL,
        processed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='已处理的 MQ 消息（幂等性保证）'
    """,
]


def ensure_schema() -> None:
    for ddl in SCHEMA:
        execute(ddl)
