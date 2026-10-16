"""
驱动层 · Modbus TCP 采集驱动
----------------------------
借鉴 iot-dc3「驱动 SDK」思想：驱动连接物理设备（这里是模拟器），按 poll_interval
轮询 holding register，将原始寄存器值还原为工程量，统一封装为 metric 报文，
通过消息总线（transport 层）上送，供数据层与应用层消费。

新增一种协议驱动 = 在 iot-dc3 里写一个 driver。本项目的 Modbus 驱动即此类。
"""
import asyncio
import logging
import time

from pymodbus.client import AsyncModbusTcpClient

log = logging.getLogger("driver")


class ModbusDriver:
    def __init__(self, cfg: dict, bus):
        self.cfg = cfg
        self.bus = bus
        self.host = cfg["modbus"]["host"]
        self.port = cfg["modbus"]["port"]
        self.tasks = []

    async def _poll_device(self, d: dict):
        unit = d["slave"]
        client = AsyncModbusTcpClient(host=self.host, port=self.port)
        await client.connect()
        if not client.connected:
            log.warning("设备 %s 连接失败，将自动重试", d["id"])
        n = self.cfg["modbus"].get("register_count", 8)
        while True:
            try:
                if not client.connected:
                    await client.connect()
                rr = await client.read_holding_registers(0, n, slave=unit)
                if rr is not None and not rr.isError():
                    regs = rr.registers
                    points = []
                    for p in d["points"]:
                        raw = regs[p["reg"]]
                        if p.get("kind") == "enum":
                            value = int(raw)
                        else:
                            value = round(raw * p.get("scale", 1), 3)
                        points.append({
                            "name": p["name"],
                            "label": p["label"],
                            "unit": p.get("unit", ""),
                            "value": value,
                            "kind": p.get("kind", "number"),
                        })
                    await self.bus.publish(
                        f"devices/{d['id']}/metrics",
                        {
                            "device": d["id"],
                            "name": d["name"],
                            "ts": int(time.time() * 1000),
                            "points": points,
                        },
                    )
                else:
                    log.warning("设备 %s 读寄存器失败", d["id"])
            except Exception as e:
                log.warning("设备 %s 采集异常: %s", d["id"], e)
                try:
                    await client.connect()
                except Exception:
                    pass
            await asyncio.sleep(d.get("poll_interval", 2))

    async def start(self):
        for d in self.cfg["devices"]:
            self.tasks.append(asyncio.create_task(self._poll_device(d)))
        log.info("Modbus 驱动已启动，采集 %d 台设备", len(self.cfg["devices"]))
