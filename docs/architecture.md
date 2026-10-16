# 架构设计（融合 iot-dc3 分层模型 + ThingsBoard 领域模型）

本项目并非简单堆砌开源库，而是**融合了两个工业互联网开源平台的设计思想**，落地为一个可运行的轻量子集：

- **iot-dc3（pnoker/iot-dc3，Apache-2.0）** —— 提供**分层架构**思想（驱动层 / 传输层 / 数据层 / 应用层），解决"系统怎么分层、协议怎么接入"。
- **ThingsBoard（thingsboard/thingsboard，Apache-2.0）** —— 提供**领域模型**思想（Device / Asset、Telemetry / Attributes、Rule Chain、Dashboard），解决"设备与数据怎么建模、怎么处理、怎么呈现"。

> 说明：作者在校实训即使用 ThingsBoard 进行设备接入与仪表盘开发，因此本项目在"平台内核理解"上以 ThingsBoard 的领域模型为骨架，在"工程分层"上参考 iot-dc3 的四层模型，二者互补。

## 一、分层架构图（iot-dc3 思想）

```
┌──────────────────────────────────────────────────────────────────┐
│                        应用层 (Application)                       │
│   可视化大屏 (ECharts)  ·  REST API  ·  WebSocket 实时推送  · 告警 │
│   （对应 ThingsBoard 的 Dashboard / 规则链动作输出）              │
└───────────────────────────────┬──────────────────────────────────┘
                                 │ subscribe
┌───────────────────────────────┴──────────────────────────────────┐
│           传输层 (Transport) —— 消息总线（解耦关键）              │
│   进程内 asyncio 总线  /  可切换 Eclipse Paho MQTT → EMQX Broker  │
│   （对应 iot-dc3 内部消息代理 / ThingsBoard 的 MQTT Transport）   │
└───────────────────────────────┬──────────────────────────────────┘
                                 │ publish  metric 报文
┌───────────────────────────────┴──────────────────────────────────┐
│                     驱动层 (Driver)                               │
│   ModbusDriver：基于 pymodbus 的 Modbus TCP Client，            │
│   按 poll_interval 轮询 holding register，还原工程量             │
│   （对应 iot-dc3 的「驱动 SDK」/ ThingsBoard 的 Device Transport）│
└───────────────────────────────┬──────────────────────────────────┘
                                 │ Modbus TCP
┌───────────────────────────────┴──────────────────────────────────┐
│               南向设备 (Device) —— DevicesSimulator              │
│  基于 pymodbus 的 Modbus TCP Server，模拟注塑机/空压机/电机      │
│   真实场景可替换为 PLC、传感器、网关等物理设备                    │
└──────────────────────────────────────────────────────────────────┘

数据层 (Data)：metric 报文经应用层消费后，由 TimeSeriesStore 落地到
SQLite 时序表（生产可替换为 InfluxDB / TimescaleDB，即 iot-dc3 默认，
也对应 ThingsBoard 的遥测时序存储）。
```

## 二、领域模型映射（ThingsBoard 思想）

| ThingsBoard 概念 | 本项目对应实现 | 说明 |
|---|---|---|
| **Device（设备）** | `config/devices.yaml` 中 `devices[*]` | 每台设备有 id、name、协议、采集点 |
| **Asset（资产）** | 设备分组 / 车间逻辑分组 | 可扩展为"车间→产线→设备"层级 |
| **Telemetry（遥测）** | 各采集点实时值 `latest` | 随采集周期刷新，存时序库 |
| **Attributes（属性）** | 设备静态配置（量程、单位、告警阈值） | 变更频率低 |
| **Rule Chain（规则链）** | `src/app/rule_chain.py`（节点化管线：filter→save→snapshot→threshold→alarm→push） | 已实现，新增节点即可编排 |
| **Dashboard（仪表盘）** | `src/web/index.html`（ECharts） | 实时大屏 + 告警面板 |

## 三、本项目模块 ↔ 双平台对照

| 本项目模块 | iot-dc3 视角 | ThingsBoard 视角 |
|---|---|---|
| `driver/modbus_driver.py` | 驱动 SDK 的一种实现 | Device Transport（Modbus 协议适配） |
| `transport/bus.py` | 内部消息代理（MQTT/RabbitMQ/Kafka） | MQTT Transport（设备遥测上送通道） |
| `data/storage.py` | 默认时序存储 | 遥测时序存储（Telemetry DAO） |
| `app/api.py` + `feed.py` + `rule_chain.py` | 应用层接口 + 规则链 | REST API + WebSocket 实时推送 + Rule Chain 处理管线 |
| `web/index.html` | 应用层可视化 | Dashboard（可视化组件） |
| `config/devices.yaml` | 设备/协议配置 | Device Profile / 资产建模 |

## 四、融合的开源项目

| 开源项目 | 角色 | 许可 |
|---|---|---|
| [iot-dc3](https://github.com/pnoker/iot-dc3) | 架构参考（工业互联网四层模型） | Apache-2.0 |
| [ThingsBoard](https://github.com/thingsboard/thingsboard) | 领域模型参考（Device/Telemetry/Rule Chain/Dashboard） | Apache-2.0 |
| [pymodbus](https://github.com/pymodbus-dev/pymodbus) | Modbus TCP 驱动 / 设备模拟器 | BSD-3 |
| [Eclipse Paho MQTT](https://github.com/eclipse-paho/paho.mqtt.python) | MQTT 消息总线客户端 | EPL/EDL |
| [ECharts](https://github.com/apache/echarts) | 可视化大屏 | Apache-2.0 |

## 五、可扩展点（面试可讲）

- **新增设备协议**：仿照 `ModbusDriver` 写一个 `xxx_driver.py`（如 OPC UA、S7），实现 `poll → publish` 即可接入总线（iot-dc3 的驱动扩展 + ThingsBoard 的 Transport 扩展）。
- **横向扩展**：把 `transport` 切到 MQTT，驱动与可视化可分布部署；iot-dc3 用 RabbitMQ/Kafka 同理，ThingsBoard 也以 MQTT 为设备主通道。
- **规则引擎（已实现）**：`rule_chain.py` 已实现 ThingsBoard 式节点化规则链（telemetry-filter → save-timeseries → latest-snapshot → threshold-eval → alarm-sink → push-client）。新增节点（如 Script 清洗、关联资产联动）只需实现 `RuleNode.process` 并加入 `build_default_chain` 即可。
- **时序库升级**：替换 `TimeSeriesStore` 后端为 InfluxDB，无需改动上层。
- **资产层级**：引入 Asset 概念，构建"车间→产线→设备"树，对应 ThingsBoard 的 Asset/Device 关系。
