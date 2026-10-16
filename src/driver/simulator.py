"""
驱动层 · 设备模拟器（南向设备）
-------------------------------
使用开源组件 pymodbus 启动一个 Modbus TCP Server，模拟车间里的三类工业设备
（注塑机 / 空压机 / 传送带电机）。每个设备占用一个 slave(单元地址)，持有 8 个
holding register，寄存器按工程量 / scale 编码为 16 位无符号整数。

关键设计：模拟器内部维护**工程量浮点状态 self.eng** 进行演化（漂移/故障），
仅在写入寄存器时按 [0, 65535] 钳制，避免"读回→越界钳制→正反馈"导致数值爆表。
驱动层（modbus_driver.py）以 Modbus TCP Client 身份轮询这些寄存器，
从而完整复现「工业协议采集」链路，无需真实硬件即可演示。
"""
import asyncio
import logging
import random

from pymodbus.datastore import (
    ModbusServerContext,
    ModbusSlaveContext,
    ModbusSequentialDataBlock,
)
from pymodbus.server import StartAsyncTcpServer

log = logging.getLogger("simulator")
REG_COUNT = 8
REG_MAX = 65535  # 16 位无符号寄存器上限


class DevicesSimulator:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.port = cfg["modbus"]["port"]
        self.scale = {}        # (unit, reg) -> scale
        self.eng = {}          # unit -> [float]*REG_COUNT  工程量（内部状态）
        self.values = {}       # unit -> [int]*REG_COUNT    寄存器值（对外）
        self.targets = {}      # unit -> {reg: 工程量目标}
        self.fault = {}        # unit -> 剩余故障计时
        self.context = self._build_context()
        self._drift_task = None
        self._serve_task = None

    def _build_context(self) -> ModbusServerContext:
        slaves = {}
        for d in self.cfg["devices"]:
            unit = d["slave"]
            self.values[unit] = [0] * REG_COUNT
            self.eng[unit] = [0.0] * REG_COUNT
            self.targets[unit] = {}
            self.fault[unit] = 0
            for p in d["points"]:
                if p.get("kind") == "enum":
                    continue
                self.scale[(unit, p["reg"])] = p["scale"]
                tgt = random.uniform(p.get("min", 0), p.get("max", 100))
                self.targets[unit][p["reg"]] = tgt
                self.eng[unit][p["reg"]] = tgt      # 初始即为合理工程量，演示开箱即活
            block = ModbusSequentialDataBlock(0, list(self.values[unit]))
            slaves[unit] = ModbusSlaveContext(
                hr=block, ir=block, di=block, co=block, zero_mode=True
            )
        return ModbusServerContext(slaves=slaves, single=False)

    def _write(self, unit: int, reg: int, eng: float):
        """把工程量写入寄存器（带 16 位无符号钳制）。"""
        scale = self.scale.get((unit, reg), 1)
        emax = float(REG_MAX) * scale
        if eng < 0:
            eng = 0.0
        if eng > emax:
            eng = emax
        self.eng[unit][reg] = eng
        reg_val = int(round(eng / scale))
        if reg_val < 0:
            reg_val = 0
        if reg_val > REG_MAX:
            reg_val = REG_MAX
        self.values[unit][reg] = reg_val
        try:
            self.context[unit].setValues(3, reg, [reg_val])
        except Exception as e:  # pragma: no cover
            log.debug("setValues failed: %s", e)

    async def _drift(self):
        """每秒让工程量向目标值平滑漂移，并随机触发故障，模拟真实工况。"""
        while True:
            for d in self.cfg["devices"]:
                unit = d["slave"]
                # 状态位：偶尔进入故障(2)，持续若干秒后恢复运行(1)
                if self.fault[unit] > 0:
                    self.fault[unit] -= 1
                    self._write(unit, 5, 2)
                else:
                    self._write(unit, 5, 1)
                    if random.random() < 0.01:          # 1% 概率进入故障
                        self.fault[unit] = 8

                for p in d["points"]:
                    if p.get("kind") == "enum":
                        continue
                    reg = p["reg"]
                    scale = p["scale"]
                    cur = self.eng[unit][reg]
                    tgt = self.targets[unit].get(reg, cur)
                    span = (p.get("max", 100) - p.get("min", 0)) or 1
                    nxt = cur + (tgt - cur) * 0.1 + random.uniform(-0.5, 0.5) * span * 0.02
                    if random.random() < 0.05:          # 偶尔更换目标
                        self.targets[unit][reg] = random.uniform(p.get("min", 0), p.get("max", 100))
                    self._write(unit, reg, nxt)
            await asyncio.sleep(1)

    async def start(self):
        self._drift_task = asyncio.create_task(self._drift())
        self._serve_task = asyncio.create_task(self._serve_modbus())
        log.info("Modbus TCP 模拟器已启动 :%s (slaves=%s)", self.port, list(self.values.keys()))

    async def _serve_modbus(self):
        try:
            await StartAsyncTcpServer(
                context=self.context, address=("0.0.0.0", self.port)
            )
        except Exception as e:  # pragma: no cover
            log.error("Modbus server error: %s", e)
