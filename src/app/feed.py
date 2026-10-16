"""
应用层 · 实时推送通道
--------------------
维护 WebSocket 连接集合与最新工况快照，供可视化大屏实时刷新。
注意：Starlette 不允许同一 WebSocket 的 send 与 receive 跨任务并发，
因此每个连接只持有一个 asyncio.Queue，由端点协程在同一任务内统一收发。
"""
import asyncio
import json


class Feed:
    def __init__(self):
        self.queues = set()        # 每个连接一个 asyncio.Queue
        self.latest: dict = {}     # device -> {point: {value, ts, label, unit, kind}}
        self.alarms: list = []     # 告警事件列表

    async def connect(self, ws) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.queues.add(q)
        return q

    async def disconnect(self, q):
        self.queues.discard(q)

    def broadcast(self, msg: dict):
        # 同步广播：规则链节点在同步上下文中调用，使用 put_nowait 避免跨协程 await
        data = json.dumps(msg, ensure_ascii=False)
        for q in list(self.queues):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass


feed = Feed()
