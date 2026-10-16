# Industrial-Edge · 工业互联网边缘数据采集与可视化平台

> 面向**工业互联网 / 物联网**方向的毕业设计与实践项目。
> **融合两个开源平台的设计思想**：
> - [iot-dc3](https://github.com/pnoker/iot-dc3) 的**四层分层架构**（驱动 / 传输 / 数据 / 应用）；
> - [ThingsBoard](https://github.com/thingsboard/thingsboard) 的**领域模型**（Device / Asset、Telemetry / Attributes、Rule Chain、Dashboard，作者在校实训即使用 ThingsBoard）。
>
> 并落地 **pymodbus（Modbus 驱动）** 与 **Eclipse Paho MQTT（消息总线）**，
> 实现「工业协议采集 → 消息总线 → 时序存储 → 实时大屏」的完整链路。

---

## 一、项目简介

针对车间设备协议异构、数据难采集、监控不及时的问题，本项目搭建了一套**边缘侧数据采集与可视化平台**：

- **南向**：通过 Modbus TCP 协议接入工业设备（演示用 pymodbus 模拟器，可替换为真实 PLC/传感器）。
- **驱动层**：自研 Modbus 采集驱动，按周期轮询寄存器、还原工程量。
- **传输层**：指标经消息总线解耦上送（进程内总线 / 可切换 MQTT Broker）。
- **数据层**：时序数据落地，支持历史查询。
- **应用层**：REST API + WebSocket + ECharts 实时大屏，含阈值/故障告警。

无需真实硬件即可一键运行演示，便于学习、教学演示与二次开发。

## 二、技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 设备/驱动 | Python · pymodbus | Modbus TCP Server/Client，工业协议采集 |
| 传输 | Eclipse Paho MQTT · asyncio | 消息总线，可切换 EMQX Broker |
| 后端 | FastAPI · uvicorn | REST / WebSocket 服务 |
| 存储 | SQLite 时序表 | 可平滑替换为 InfluxDB/TimescaleDB |
| 前端 | HTML · ECharts | 实时看板、告警面板 |

## 三、快速开始

### 方式一：本地一键运行（零依赖演示）
> 推荐 Python 3.11（pymodbus 3.6.5 在该版本下最稳定）。
```bash
pip install -r requirements.txt
python run.py
# 打开 http://localhost:8000
```
平台启动后会自动运行设备模拟器并采集数据，大屏实时刷新；无需任何硬件或外部中间件。
启动后平台会自动运行设备模拟器并采集数据，大屏实时刷新。

### 方式二：Docker 生产级部署（接入真实 MQTT Broker）
```bash
docker compose up -d
# 平台 http://localhost:8000 ，EMQX 控制台 http://localhost:18083
```
此时 `TRANSPORT=mqtt`，驱动与可视化通过 EMQX 解耦，可独立扩容。

## 四、目录结构
```
industrial-edge/
├── config/devices.yaml        # 设备与采集点配置（slave/寄存器/量程）
├── src/
│   ├── driver/
│   │   ├── simulator.py       # 驱动层：Modbus TCP 设备模拟器（南向设备）
│   │   └── modbus_driver.py   # 驱动层：Modbus 采集驱动（poll → 发布）
│   ├── transport/bus.py       # 传输层：消息总线（internal / MQTT）
│   ├── data/storage.py        # 数据层：时序存储
│   ├── app/
│   │   ├── api.py             # 应用层：REST + WebSocket
│   │   ├── feed.py            # 应用层：实时推送通道（WebSocket 连接管理）
│   │   └── rule_chain.py      # 应用层：ThingsBoard 式规则链（阈值/告警/动作节点）
│   └── web/index.html         # 可视化大屏（ECharts）
├── docs/architecture.md       # 架构设计与开源融合说明
├── docker-compose.yml / Dockerfile
└── run.py                    # 平台编排入口
```

## 五、融合的开源项目
- **iot-dc3**（架构参考）：工业互联网四层（驱动/传输/数据/应用）分层模型。
- **ThingsBoard**（领域模型参考）：Device/Asset、Telemetry/Attributes、Rule Chain、Dashboard 建模思想（作者在校实训平台）。
- **pymodbus**：Modbus 协议驱动与设备模拟，BSD 许可。
- **Eclipse Paho MQTT**：MQTT 消息总线客户端，EPL/EDL 许可。
- **Apache ECharts**：实时可视化大屏，Apache-2.0 许可。

## 六、项目经历

> **工业互联网边缘数据采集与可视化平台** ｜ 独立开发 ｜ 2026
> - 融合开源工业互联网平台 **iot-dc3**（四层分层架构）与 **ThingsBoard**（Device/Telemetry/Rule Chain/Dashboard 领域模型，在校实训平台）的设计思想，设计并实现了「设备接入—消息总线—时序存储—可视化」采集平台。
> - 基于 pymodbus 开发 Modbus TCP 采集驱动，按周期轮询寄存器并还原工程量（对应 ThingsBoard 的 Device Transport 与遥测采集）；通过消息总线（进程内 / 可切换 Eclipse Paho MQTT + EMQX）解耦采集与展示。
> - 使用 FastAPI 提供 REST/WebSocket 接口，前端基于 ECharts 搭建实时大屏（对应 ThingsBoard Dashboard），实现设备工况监控与阈值/故障告警（对应 Rule Chain 规则判定）。
> - 支持 `docker-compose` 一键部署（含 EMQX），时序存储可平滑替换为 InfluxDB/TimescaleDB。
> - **技术栈**：Python · pymodbus · MQTT · FastAPI · SQLite · ECharts · Docker

## 七、可扩展方向
- 新增协议：仿照 `ModbusDriver` 实现 `xxx_driver.py`（如 OPC UA、S7），即可接入总线（iot-dc3 驱动扩展 + ThingsBoard Transport 扩展）。
- 云边协同：驱动部署在边缘网关，MQTT 上云，对应 iot-dc3 边缘计算思想与 ThingsBoard 的 MQTT 设备主通道。
- 规则引擎（已实现）：`src/app/rule_chain.py` 已实现 ThingsBoard 式节点化规则链（telemetry-filter → save-timeseries → latest-snapshot → threshold-eval → alarm-sink → push-client），新增节点即可编排。
- 资产层级：引入 Asset 概念，构建"车间→产线→设备"树，对应 ThingsBoard 的 Asset/Device 关系。

---
许可证：本项目教学示例，融合的开源组件均遵循各自开源协议（Apache-2.0 / BSD / EPL-EDL）。
