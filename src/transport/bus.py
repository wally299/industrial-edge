"""
传输层 · 消息总线（借鉴 iot-dc3 内部消息代理）
---------------------------------------------
驱动层采集到的 metric 不直接写库，而是发布到消息总线，数据层/应用层订阅消费。
这样驱动、存储、可视化三者解耦，可水平扩展（iot-dc3 用 RabbitMQ/Kafka/MQTT）。

- transport="internal"：进程内 asyncio 总线，零依赖即可运行演示。
- transport="mqtt"     ：接入开源 MQTT Broker（EMQX / Mosquitto），使用 Eclipse
                          Paho 客户端，与生产部署一致（docker-compose 已内置 EMQX）。
"""
import asyncio
import json
import logging
from typing import Awaitable, Callable, Dict, List

log = logging.getLogger("bus")


def _match(topic: str, pattern: str) -> bool:
    """支持 MQTT 风格通配符：'+' 单层，'#' 多层。"""
    t = topic.split("/")
    p = pattern.split("/")
    for i, seg in enumerate(p):
        if seg == "#":
            return True
        if i >= len(t):
            return False
        if seg != "+" and seg != t[i]:
            return False
    return len(t) == len(p)


class MessageBus:
    def __init__(self, transport: str = "internal", mqtt: dict = None):
        self.transport = transport
        self.mqtt_cfg = mqtt or {}
        self._subscribers: Dict[str, List[Callable]] = {}
        self._mqtt_client = None
        self._loop = None

    async def start(self):
        self._loop = asyncio.get_event_loop()
        if self.transport == "mqtt":
            await self._start_mqtt()

    async def _start_mqtt(self):
        from paho.mqtt.client import Client, CallbackAPIVersion

        cfg = self.mqtt_cfg
        self._mqtt_client = Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id="industrial-edge",
        )
        if cfg.get("username"):
            self._mqtt_client.username_pw_set(cfg["username"], cfg.get("password", ""))
        topic_root = cfg.get("topic_root", "devices/#")

        def on_connect(client, userdata, flags, reason_code, properties=None):
            client.subscribe(topic_root)
            log.info("已连接 MQTT Broker %s:%s", cfg.get("host"), cfg.get("port"))

        self._mqtt_client.on_connect = on_connect
        self._mqtt_client.on_message = self._on_mqtt_message
        self._mqtt_client.connect_async(cfg.get("host", "127.0.0.1"), int(cfg.get("port", 1883)), 60)
        self._mqtt_client.loop_start()

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            return
        for pattern, cbs in self._subscribers.items():
            if _match(msg.topic, pattern):
                for cb in cbs:
                    if asyncio.iscoroutinefunction(cb):
                        asyncio.run_coroutine_threadsafe(cb(payload), self._loop)
                    else:
                        cb(payload)

    async def publish(self, topic: str, payload: dict):
        if self.transport == "mqtt" and self._mqtt_client:
            self._mqtt_client.publish(topic, json.dumps(payload, ensure_ascii=False))
            return
        # internal：直接回调匹配的订阅者
        for pattern, cbs in self._subscribers.items():
            if _match(topic, pattern):
                for cb in cbs:
                    if asyncio.iscoroutinefunction(cb):
                        asyncio.create_task(cb(payload))
                    else:
                        cb(payload)

    async def subscribe(self, topic: str, callback: Callable):
        self._subscribers.setdefault(topic, []).append(callback)
        if self.transport == "mqtt" and self._mqtt_client:
            self._mqtt_client.subscribe(topic)
