# MySQL 笔记

## 一、MySQL 能轻松承载多大规模的数据？

先说结论：**单表千万级行、整库 TB 级**都是 MySQL 的日常范围，而题目里说的
“数万用户 + 数十万笔记”对它来说确实是小 Case。

对比一下三种存法大概能撑到什么程度：

| 存法 | 实际能撑的量级 | 瓶颈在哪 |
| --- | --- | --- |
| TXT 记事本 | 几 MB～几十 MB 就难受了 | 每次读写都要整体加载，几个 GB 的文件常常打不开 |
| Excel 表格 | 十多万行（新版上限约 104 万行） | 全量加载到内存、每次编辑重算，稍微一动就卡 |
| MySQL | 单表千万～亿级行（配合分区/分表更大） | 主要受磁盘、内存、索引设计和 SQL 写法影响 |

参考量级（同一台普通服务器，取决于硬件和表结构）：千万行表的按主键查询仍在**毫秒级**；
亿级行的表通过索引也常在几十毫秒内返回。

## 二、MySQL 是怎么做到数据量大还能快的？

关键在于它**不是“把数据都读进来再筛”，而是把“找数据”的成本压到很低**：

1. **磁盘上的组织方式（页 + B+ 树索引）**：数据按固定大小的“页”（默认 16KB）存在磁盘上，
   主键用 **B+ 树**组织。找一个值只需沿树下降 3–4 层，每层一次磁盘读
   （几千万行的高度也只有 3～4 层），所以不需要扫描全表。
2. **索引（Index）**：给经常作为查询条件的列建索引（如 `notes.id`、`users.student_id`），
   相当于给书加了目录；代价是写入时要顺带维护索引，所以索引不是越多越好。
3. **内存缓存（InnoDB Buffer Pool）**：把热点数据页和索引页缓存在内存里，
   重复访问命中缓存时完全不碰磁盘。
4. **查询优化器**：解析 SQL 后自己决定走哪个索引、按什么顺序连接表，
   避免“明明有索引却不用”。
5. **行级锁 + 多版本并发控制（MVCC）**：读操作通常不加锁，读写可以并发，
   而不是像 Excel 那样“一个人打开，另一个人只能只读”。
6. **水平扩展手段**：数据再大可以**分区**、**分库分表**、加**只读副本**分担查询。
   （分得越细，跨分片查询越麻烦，所以通常是数据真大了才做。）

一句话：**页式存储 + B+ 树索引 + 内存缓存 + 优化器**，让它能“在亿级数据里只碰几十个页”就返回结果。

## 三、用 Python 怎么操作 MySQL？

两条路：**驱动 + SQL**（直观、贴近原理）或 **ORM**（面向对象、少写 SQL）。
我在入门篇会用到的是第一种，这里以它为主。

### 1. 直连驱动（pymysql）

```bash
pip install pymysql
```

```python
import pymysql

conn = pymysql.connect(
    host="127.0.0.1", port=3306,
    user="jotang", password="***",   # 真实项目里从环境变量读，不写进代码
    database="jotangnote", charset="utf8mb4",
)
try:
    with conn.cursor() as cur:
        # 建表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                user_id BIGINT NOT NULL,
                title VARCHAR(120) NOT NULL,
                content MEDIUMTEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_user_created (user_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        # 参数化插入（不要用字符串拼接！）
        cur.execute(
            "INSERT INTO notes (user_id, title, content) VALUES (%s, %s, %s)",
            (1, "第一篇笔记", "你好，JotangNote"),
        )
        conn.commit()          # 写操作必须提交
        # 查询
        cur.execute("SELECT id, title FROM notes WHERE user_id=%s", (1,))
        print(cur.fetchall())
finally:
    conn.close()
```

**注意点：**

- **一定要参数化**（`%s` 占位 + 参数元组）。用 f-string 拼 SQL 会直接带来 **SQL 注入**风险。
- 写操作要 `commit()`，否则连关闭时回滚，看起来“写进去了”其实是空的。
- `charset="utf8mb4"`：中文、emoji 都能存。
- 连接和游标用完要关；生产代码里用**连接池**而不是每次新建连接。

### 2. ORM 方式（SQLAlchemy，入门篇进阶时用）

```python
from sqlalchemy import create_engine, Column, BigInteger, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker

engine = create_engine("mysql+pymysql://jotang:***@127.0.0.1/jotangnote?charset=utf8mb4")
Base = declarative_base()

class Note(Base):
    __tablename__ = "notes"
    id = Column(BigInteger, primary_key=True)
    title = Column(String(120))
    content = Column(Text)

Session = sessionmaker(bind=engine)
with Session() as s:
    s.add(Note(title="第一篇笔记", content="你好"))
    s.commit()
```

ORM 的好处是表结构变成 Python 类、拼 SQL 的活由它干；坏处是“黑盒”多一点，
复杂查询仍然会写原生 SQL。

## 四、我的学习过程记录

1. 先确认本机已有的 MySQL（Windows 装了 MySQL 8.0），用 `mysql --version` 确认客户端可用。
2. 按上面第一种方式写了最小的“建表 → 插入 → 查询”脚本并实际跑通，确认中文正常（utf8mb4）。
3. 用 `EXPLAIN` 对比了一下“有索引 / 没索引”查同一张表的差别：
   没索引时 `type=ALL`（全表扫描），有索引时 `type=ref` 且 `rows` 数量大幅下降——
   这是“为什么有索引就快”的最直观证据。
4. 用 `SHOW TABLE STATUS` 看了表的引擎（InnoDB）和数据量估算。

> 🤖 AI 使用说明：本节内容由本人使用 Hermes Agent 协助整理，示例代码与结论均在本地实际验证过。
