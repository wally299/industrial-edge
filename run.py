"""
Industrial-Edge 平台入口
-------------------------
编排四层：模拟器(南向设备) -> 驱动层 -> 传输层(消息总线) -> 数据层/应用层。
参考 iot-dc3 的分层架构：driver / transport / data / application。

运行：  python run.py                 # 进程内总线，零依赖演示
       TRANSPORT=mqtt python run.py   # 接入 MQTT Broker（docker-compose 已含 EMQX）
"""
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import yaml
import uvicorn

from app.api import app, configure
from app.feed import feed
from app.rule_chain import build_default_chain
from data.storage import TimeSeriesStore
from driver.modbus_driver import ModbusDriver
from driver.simulator import DevicesSimulator
from transport.bus import MessageBus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("pymodbus").setLevel(logging.WARNING)  # 抑制协议层调试日志
log = logging.getLogger("main")


def load_config(path: str = "config/devices.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_alarms(device_cfg: dict, point_vals: dict) -> list:
    # 已迁移至 app/rule_chain.py 的 ThresholdRuleNode（ThingsBoard 式规则链）
    raise NotImplementedError("告警判定已迁移到规则链，见 rule_chain.ThresholdRuleNode")


async def app_layer(bus: MessageBus, storage: TimeSeriesStore, cfg: dict):
    """应用层：消费 metric 报文 -> 交由 Rule Chain 处理（存时序/快照/阈值/告警/推送）。"""
    chain = build_default_chain(storage, feed, cfg)

    async def on_metrics(payload: dict):
        # 统一封装为 ThingsBoard 遥测消息，进入规则链管线
        msg = {
            "type": "metrics",
            "device": payload["device"],
            "ts": payload["ts"],
            "points": payload["points"],
        }
        chain.accept(msg)

    await bus.subscribe("devices/+/metrics", on_metrics)


async def main():
    cfg = load_config()
    storage = TimeSeriesStore(path=os.path.join(os.path.dirname(__file__), "data", "iot.db"))
    transport = os.environ.get("TRANSPORT", "internal")
    bus = MessageBus(transport=transport, mqtt=cfg.get("mqtt"))
    await bus.start()

    sim = DevicesSimulator(cfg)
    await sim.start()

    driver = ModbusDriver(cfg, bus)
    await driver.start()

    await app_layer(bus, storage, cfg)
    configure(storage, cfg)

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info"))
    log.info("Industrial-Edge 平台已启动 -> http://localhost:8000")
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
