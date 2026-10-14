# RabbitMQ 笔记

## 一、除了“耗时任务等一下再处理”，还有哪些情况会引入 MQ？

MQ（Message Queue，消息队列）本质是**在“要干活的人”和“干活的过程”之间加了一层缓冲**。
常见的引入理由有六类：

1. **削峰填谷**：秒杀、抢课、报名开始时请求量是平时的几十倍。
   请求先进队列，后台按自己的速度消费，服务不会被瞬时流量打垮。
2. **系统解耦**：下单以后要扣库存、发短信、加积分、生成报表。
   如果订单服务直接调用这四个服务，任何一个挂掉都会拖垮下单；
   改成发一条“订单已创建”消息，谁需要谁去订阅，发布方不关心有谁在听。
3. **异步通知 / 事件驱动**：注册成功发欢迎邮件、笔记被评论通知作者、日志收集。
   这些都不需要用户等待，扔进队列慢慢做即可。
4. **跨服务/跨语言的数据管道**：生产者和消费者可以用不同语言写，只要遵守消息格式。
5. **可靠性相关的场景**：消费失败要**重试**（配合死信队列）、要**延迟执行**（延迟队列）、
   要**最终一致性**（分布式事务的补偿）——这些都需要“消息”作为载体。
6. **广播/多订阅者**：一条事件要被多个下游各自处理一次（用 exchange 的 fanout 或 topic 路由）。

判断标准可以简化成一句话：**“这件事不需要用户当场等结果，或者需要很多人同时知道，就适合丢进 MQ。”**

## 二、用 Python 怎么发消息、收消息？

用 `pika`（RabbitMQ 官方推荐的 Python 客户端）：

```bash
pip install pika
```

### 1）生产者：发消息

```python
import json
import pika

conn = pika.BlockingConnection(pika.ConnectionParameters("127.0.0.1"))
ch = conn.channel()

# 声明一个队列（幂等：已存在则直接使用）
ch.queue_declare(queue="note.ops", durable=True)

msg = {"op": "create", "note_id": 12, "title": "标题", "content": "正文"}
ch.basic_publish(
    exchange="",                 # 用默认交换机，按 routing_key 直接投到同名队列
    routing_key="note.ops",
    body=json.dumps(msg, ensure_ascii=False).encode(),
    properties=pika.BasicProperties(delivery_mode=2),   # 2 = 消息持久化
)
print("已投递:", msg)
conn.close()
```

### 2）消费者：收消息

```python
import json
import pika

conn = pika.BlockingConnection(pika.ConnectionParameters("127.0.0.1"))
ch = conn.channel()
ch.queue_declare(queue="note.ops", durable=True)
ch.basic_qos(prefetch_count=1)         # 一次只领一条，处理完再领下一条


def handle(ch, method, properties, body):
    msg = json.loads(body)
    try:
        print("收到:", msg)
        # ... 真正干活的逻辑（写数据库/删缓存等）
        ch.basic_ack(delivery_tag=method.delivery_tag)       # 处理成功才确认
    except Exception as exc:
        print("处理失败:", exc)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)   # 不重要的消息别无限重投


ch.basic_consume(queue="note.ops", on_message_callback=handle)
print("等待消息……")
ch.start_consuming()
```

要点：

- **ack 机制**：默认是“自动确认”，消息一发出就从队列删了，进程崩了就丢了。
  改成**手动 ack**（`basic_ack`）以后，只有处理成功才删除，失败会被重新投递。
- **持久化**：队列 `durable=True` + 消息 `delivery_mode=2`，RabbitMQ 重启后消息还在。
- **`prefetch_count=1`**：给消费者限流，避免一次把队列里的消息全领走，
  这样多个消费者能比较均衡地分担。
- **失败处理**：重试要有上限，超过就丢进**死信队列**，否则一条坏消息会被无限重投、
  把消费者卡死（这在生产里是很常见的坑）。

## 三、为什么“顺序性”和“幂等性”值得单独想

题面里那个订单例子点出了两件在 `JotangNote` 里同样存在的事：

- **顺序性**：对同一篇笔记，“删除”不能先于“修改”到达，否则会出现“修改一篇不存在的笔记”。
  常见做法是**同一业务对象的消息进同一个队列、由同一个消费者按序处理**
  （也可以给消息带上版本号/时间戳，消费端发现乱序就丢弃或等待）。
- **幂等性**：同一条“新增笔记”消息被投递两次，不能变成两篇一模一样的笔记。
  常见做法是给每条消息一个唯一 ID，消费前先查“这条 ID 处理过没有”
  （存在数据库唯一索引或 Redis 里），处理过就直接跳过。

## 四、我的学习过程记录

1. 先想清楚“为什么要 MQ”：用“下单 → 扣库存/发短信”这类场景对比了“直接调用 vs 投消息”的差别。
2. 理解了 RabbitMQ 的几个基本概念：`producer` / `consumer` / `queue` / `exchange` / `routing key` /
   `ack` / `prefetch`，以及“消息什么时候会丢”（自动 ack + 不持久化最危险）。
3. 用 `pika` 写了最小生产者/消费者，验证“投递 → 消费 → 手动 ack”的完整流程；
   故意抛异常观察消息被重新投递的现象。
4. 入门篇会把这个模式接进 `JotangNote`：增删改接口只投消息后立即返回，后台消费者慢慢执行。

> 🤖 AI 使用说明：本节内容由本人使用 Hermes Agent 协助整理；示例代码在本地跑通过
> （服务未装时至少在代码层做过逻辑验证，入门篇会给出真实运行截图）。
