"""JotangNote 后端 —— 入门篇

接口一览：
    GET    /hello                     启蒙篇的示例接口
    POST   /api/auth/register         注册（同步写 MySQL，密码加盐哈希）
    POST   /api/auth/login            登录（校验密码 → 发 token 存 Redis）
    GET    /api/auth/me               当前登录用户
    POST   /api/auth/logout           退出登录
    POST   /api/notes                 新增笔记 → 投递 MQ，立即返回 202
    GET    /api/notes                 我的笔记列表
    GET    /api/notes/{note_id}       查一篇笔记（Redis 缓存旁路 + 防穿透/击穿）
    PUT    /api/notes/{note_id}       修改笔记 → 投递 MQ，立即返回 202
    DELETE /api/notes/{note_id}       删除笔记（软删）→ 投递 MQ，立即返回 202
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

import cache
import db
import mq
import security

app = FastAPI(title="JotangNote", description="焦糖工作室招新 · 后端项目", version="0.2.0")


@app.on_event("startup")
def on_startup() -> None:
    db.ensure_schema()


# ---------------------------------------------------------------- 通用响应

def ok(data=None, message: str = "ok") -> dict:
    return {"code": 0, "message": message, "data": data}


# ---------------------------------------------------------------- 数据模型

class RegisterIn(BaseModel):
    student_id: str = Field(min_length=4, max_length=32, description="学号")
    name: str = Field(min_length=1, max_length=64, description="昵称")
    password: str = Field(min_length=6, max_length=64, description="密码（至少 6 位）")


class LoginIn(BaseModel):
    student_id: str
    password: str


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=20000)


# ---------------------------------------------------------------- 认证

def current_user(authorization: str | None = Header(default=None)) -> int:
    """从 Authorization: Bearer <token> 里解析出 user_id。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    token = authorization.split(" ", 1)[1].strip()
    user_id = cache.get_session_user(token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
    return user_id


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn):
    if db.query_one("SELECT id FROM users WHERE student_id=%s", (payload.student_id,)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该学号已注册")
    salt = security.make_salt()
    user_id = db.execute_returning_id(
        "INSERT INTO users (student_id, name, password_hash, salt) VALUES (%s, %s, %s, %s)",
        (payload.student_id, payload.name, security.hash_password(payload.password, salt), salt),
    )
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=ok({"id": user_id, "student_id": payload.student_id,
                                    "name": payload.name}, "注册成功"))


@app.post("/api/auth/login")
def login(payload: LoginIn):
    row = db.query_one(
        "SELECT id, student_id, name, password_hash, salt FROM users WHERE student_id=%s",
        (payload.student_id,),
    )
    if not row or not security.verify_password(payload.password, row["salt"], row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="学号或密码不正确")
    token = security.new_token()
    cache.save_session(token, row["id"])
    return ok({"token": token, "user": {"id": row["id"], "name": row["name"]}}, "登录成功")


@app.post("/api/auth/logout")
def logout(user_id: int = Depends(current_user), authorization: str = Header(default="")):
    cache.drop_session(authorization.split(" ", 1)[1].strip())
    return ok(None, "已退出登录")


@app.get("/api/auth/me")
def me(user_id: int = Depends(current_user)):
    row = db.query_one("SELECT id, student_id, name, created_at FROM users WHERE id=%s", (user_id,))
    return ok(row)


# ---------------------------------------------------------------- 笔记

def _fetch_note(note_id: int, user_id: int) -> dict | None:
    return db.query_one(
        "SELECT id, user_id, title, content, created_at, updated_at "
        "FROM notes WHERE id=%s AND deleted_at IS NULL", (note_id,)
    )


@app.post("/api/notes", status_code=status.HTTP_202_ACCEPTED)
def create_note(payload: NoteIn, user_id: int = Depends(current_user)):
    op_id = mq.publish_note_op("create", user_id, title=payload.title, content=payload.content)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED,
                        content=ok({"op_id": op_id}, "已提交，稍后处理完成（由消费者写入数据库）"))


@app.get("/api/notes")
def list_notes(user_id: int = Depends(current_user)):
    rows = db.query_all(
        "SELECT id, title, created_at, updated_at FROM notes "
        "WHERE user_id=%s AND deleted_at IS NULL ORDER BY id DESC", (user_id,)
    )
    return ok(rows)


@app.get("/api/notes/{note_id}")
def get_note(note_id: int, user_id: int = Depends(current_user)):
    # 1) 先查缓存（Redis 命中就直接返回）
    source = "redis"
    hit, note = cache.get_cached_note(note_id)

    if not hit:
        # 2) 未命中：抢一把互斥锁再回源，避免大量请求同时砸 MySQL（防缓存击穿）
        if cache.acquire_rebuild_lock(note_id):
            try:
                note = _fetch_note(note_id, user_id)
                source = "mysql"
                if note is None:
                    cache.set_empty_mark(note_id)      # 3) 库里也没有 → 写空值标记（防缓存穿透）
                else:
                    cache.set_cached_note(note_id, note)
            finally:
                cache.release_rebuild_lock(note_id)
        else:
            # 没抢到锁：说明别的请求正在重建缓存，等一下直接用它的结果
            if cache.wait_for_cache(note_id):
                _, note = cache.get_cached_note(note_id)
                source = "redis(等别人重建)"
            else:
                note = _fetch_note(note_id, user_id)
                source = "mysql(没等到缓存)"

    if note is None:                                # 缓存里是空值标记，或库里确实没有
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="笔记不存在")
    if note["user_id"] != user_id:                  # 鉴权：只能看自己的笔记
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该笔记")

    data = dict(note)
    data["_source"] = source                        # 方便测试时看出数据来自 Redis 还是 MySQL
    return ok(data)


@app.put("/api/notes/{note_id}", status_code=status.HTTP_202_ACCEPTED)
def update_note(note_id: int, payload: NoteIn, user_id: int = Depends(current_user)):
    if not db.query_one("SELECT id FROM notes WHERE id=%s AND user_id=%s AND deleted_at IS NULL",
                        (note_id, user_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="笔记不存在或无权修改")
    op_id = mq.publish_note_op("update", user_id, note_id=note_id,
                               title=payload.title, content=payload.content)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED,
                        content=ok({"op_id": op_id}, "修改已进入队列，稍后生效"))


@app.delete("/api/notes/{note_id}", status_code=status.HTTP_202_ACCEPTED)
def delete_note(note_id: int, user_id: int = Depends(current_user)):
    if not db.query_one("SELECT id FROM notes WHERE id=%s AND user_id=%s AND deleted_at IS NULL",
                        (note_id, user_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="笔记不存在或无权删除")
    op_id = mq.publish_note_op("delete", user_id, note_id=note_id)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED,
                        content=ok({"op_id": op_id}, "删除已进入队列，稍后生效"))


# ---------------------------------------------------------------- 启蒙篇示例

@app.get("/hello", response_class=PlainTextResponse)
def hello() -> str:
    return "Hello World From Web Application!"


@app.get("/")
def index() -> dict:
    return ok({"name": "JotangNote", "stage": "入门篇", "docs": "/docs"})
