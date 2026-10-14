# Redis 笔记

## 一、Redis 为什么这么快？

Redis 的查询时间通常在**微秒级**，比 MySQL 的毫秒级快一两个数量级。原因主要有五条：

1. **数据在内存里**。Redis 的主体数据放内存，读写不需要磁盘 IO。
   （MySQL 也能缓存，但它的“数据本体”在磁盘上；Redis 是内存数据库，磁盘只用来持久化。）
2. **单线程处理命令，躲开了锁和上下文切换**。命令一条条顺序执行，
   不用为并发去抢锁，也不会有多线程切换的开销。
   （现在的 Redis 用多线程只做网络读写/IO，**执行命令仍然是单线程**，这也是它“原子性”的来源。）
3. **IO 多路复用（epoll）**。一个线程用 epoll 同时盯着成千上万个连接，
   哪个连接有数据就处理哪个，不用为每个连接开线程。
4. **为场景定制的数据结构**。String / Hash / List / Set / ZSet / Bitmap / HyperLogLog……
   每种都有针对性的实现（如小数据用 listpack 紧凑存储、大数据才转哈希表/跳表），
   操作常常是 O(1) 或 O(log N)。
5. **协议和实现都刻意保持简单**。RESP 协议简单、命令执行路径短，没有 SQL 解析和优化器那一层开销。

代价要清楚：内存贵、容量有限（所以 Redis 是**缓存**不是主库），掉电有丢数据风险（靠 RDB/AOF 缓解）。

## 二、MySQL 里的一行数据，可以怎么放进 Redis 当缓存？

常见有三种存法，各有取舍：

### 1. 序列化成 JSON 字符串（最常用，我用的这种）

```python
key = f"note:{note_id}"
value = json.dumps({"id": 12, "title": "标题", "content": "正文", "updated_at": "..."}, ensure_ascii=False)
r.set(key, value, ex=300)         # 5 分钟过期
```

- **优点**：一次 GET 就能拿到整行，读多写少场景最划算；结构一目了然。
- **缺点**：想只取某个字段也得反序列化整块；原样存整行数据偏大。

### 2. 用 Hash 存字段

```python
r.hset(f"note:{note_id}", mapping={"title": "标题", "content": "正文"})
r.hget(f"note:{note_id}", "content")
```

- **优点**：可以只读/只改某个字段，节省带宽。
- **缺点**：Hash 的过期时间只能设在**整个 key** 上，不能给单个字段设过期。

### 3. 拆成结构化的多个 key（按查询需求定制）

比如“某用户最近的笔记列表”缓存成 List/ZSet：

```python
r.zadd(f"user:{uid}:notes", {str(note_id): score})   # score 用时间戳，方便按时间倒序取
r.zrevrange(f"user:{uid}:notes", 0, 19)              # 取最近 20 篇的 id
```

- **优点**：命中率比“按 id 缓存单篇”更高（列表页也能直接用）。
- **缺点**：一致性问题更复杂——新增/删除/修改笔记时都要同步维护。

**key 设计习惯**：`业务:对象:标识`（如 `note:12`、`user:3:notes`），便于排查和批量清理。
**一定要设过期时间**（`ex=`），不然内存会慢慢被垃圾数据吃满。

## 三、用 Python 怎么操作 Redis？

用官方推荐的 `redis-py`：

```bash
pip install redis
```

```python
import json
import redis

# 连接池：整个进程复用一个池，不要每次请求新建连接
pool = redis.ConnectionPool(host="127.0.0.1", port=6379, db=0, decode_responses=True)
r = redis.Redis(connection_pool=pool)

r.set("note:12", json.dumps({"title": "标题"}), ex=300)   # 写缓存，300 秒过期
print(r.get("note:12"))                                   # 读缓存 → 没有则返回 None
print(r.ttl("note:12"))                                   # 还剩多久过期
r.delete("note:12")                                       # 主动失效

# 计数器 / 原子操作（做“防缓存穿透”的空值标记也用它）
r.incr("stats:note_read:12")
r.setex("empty:note:999", 60, "1")                        # 标记“这篇笔记不存在”，60 秒
```

要点：

- `decode_responses=True` 让返回的是 `str` 而不是 `bytes`，调试时舒服很多。
- **缓存逻辑的标准三步**：先查缓存 → 没有就查数据库 → 回填缓存（入门篇的查询接口就是这么改的）。
- 数据库有写操作时，要**主动删掉对应缓存**（而不是去“更新”缓存），
  下次读会被重新回填——这样最不容易出现脏数据（这叫 Cache-Aside 策略）。
- 用 `ex=` 设过期（防止内存无限增长），用**连接池**（防止高并发下连接爆炸）。

## 四、我的学习过程记录

1. 先理解“缓存 = 数据本体之外的另一份数据，且要和本体保持一致”，
   再想清楚命中/未命中两条路径各自怎么走。
2. 用 `redis-cli` 手敲了 `SET/GET/EXPIRE/TTL/DEL`，观察 key 过期前后 `GET` 与 `TTL` 的变化。
3. 用 `redis-py` 把上面三步逻辑写成一个小函数并跑通（命中时不再查库）。
4. 顺带了解了缓存三大经典问题：**一致性 / 穿透 / 击穿**（入门篇的加分项会选一个实做），
   以及它们对应的手段（写后删缓存、空值标记或布隆过滤器、互斥锁或逻辑过期）。

> 🤖 AI 使用说明：本节内容由本人使用 Hermes Agent 协助整理，命令与示例在本地实际执行过。
