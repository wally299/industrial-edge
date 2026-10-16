"""
应用层 · ThingsBoard 式规则链（Rule Chain）
------------------------------------------
借鉴 ThingsBoard 的领域模型：设备遥测（Telemetry）进入 Rule Chain 后，
依次流经多个 Rule Node，由节点完成「过滤 → 存时序 → 更新最新值 → 阈值判定 → 产生告警 → 推送前端」。

本项目实现一个轻量但结构完整（节点化、可扩展）的规则链引擎，对应 ThingsBoard 的节点编排能力：
- RuleNode          节点基类，process(msg)->list，返回向下游传递的 0..n 条消息
- TelemetryFilterNode  消息类型过滤（对应 Message Type Filter）
- SaveTsNode        保存遥测时序（对应 Save Timeseries）
- SnapshotNode      更新最新值快照（对应 Latest Telemetry）
- ThresholdRuleNode 阈值/故障判定（对应 Script/Filter 节点，产出告警消息）
- AlarmRuleNode     告警落库（对应 Create Alarm 节点）
- PushRuleNode      广播给前端（对应 WebSocket/REST 动作节点）
"""
import logging

log = logging.getLogger("rulechain")


class RuleNode:
    """规则链节点基类。process 接收一条消息，返回向下游传递的 0..n 条消息。"""

    def __init__(self, name: str):
        self.name = name

    def process(self, msg: dict) -> list:
        raise NotImplementedError

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.name}>"


class TelemetryFilterNode(RuleNode):
    """消息类型过滤：只放行遥测（metrics）消息，其它丢弃。"""

    def __init__(self):
        super().__init__("telemetry-filter")

    def process(self, msg: dict) -> list:
        return [msg] if msg.get("type") == "metrics" else []


class SaveTsNode(RuleNode):
    """保存遥测时序（对应 ThingsBoard 的 Save Timeseries 节点）。"""

    def __init__(self, storage):
        super().__init__("save-timeseries")
        self.storage = storage

    def process(self, msg: dict) -> list:
        ts = msg.get("ts")
        for pt in msg.get("points", []):
            self.storage.add(msg["device"], pt["name"], pt["value"], ts)
        return [msg]


class SnapshotNode(RuleNode):
    """更新最新值快照（对应 ThingsBoard 的 Latest Telemetry 节点）。"""

    def __init__(self, feed):
        super().__init__("latest-snapshot")
        self.feed = feed

    def process(self, msg: dict) -> list:
        prev = self.feed.latest.setdefault(msg["device"], {})
        for pt in msg.get("points", []):
            prev[pt["name"]] = {
                "value": pt["value"], "ts": msg.get("ts"),
                "label": pt.get("label"), "unit": pt.get("unit", ""),
                "kind": pt.get("kind", "number"),
            }
        return [msg]


class ThresholdRuleNode(RuleNode):
    """阈值/故障判定（对应 ThingsBoard 的 Script/Filter 节点）。
    依据设备 profile 的 min/max 与 enum 故障位，产出告警消息并随原消息继续向下传递。"""

    def __init__(self, devices_by_id: dict):
        super().__init__("threshold-eval")
        self.devices_by_id = devices_by_id

    def process(self, msg: dict) -> list:
        device_id = msg["device"]
        dcfg = self.devices_by_id.get(device_id, {})
        point_vals = {pt["name"]: pt["value"] for pt in msg.get("points", [])}
        alarms = []
        for p in dcfg.get("points", []):
            name = p["name"]
            if name not in point_vals:
                continue
            v = point_vals[name]
            if p.get("kind") == "enum":
                if v == 2:
                    alarms.append({"level": "critical",
                                   "msg": f"{dcfg['name']} {p['label']}故障"})
            else:
                lo, hi = p.get("min"), p.get("max")
                if lo is not None and v < lo:
                    alarms.append({"level": "warn",
                                   "msg": f"{dcfg['name']} {p['label']}低于下限 {lo}{p.get('unit', '')}"})
                if hi is not None and v > hi:
                    alarms.append({"level": "warn",
                                   "msg": f"{dcfg['name']} {p['label']}高于上限 {hi}{p.get('unit', '')}"})
        if alarms:
            return [msg, {"type": "alarm", "device": device_id,
                          "ts": msg.get("ts"), "alarms": alarms}]
        return [msg]


class AlarmRuleNode(RuleNode):
    """告警处理节点（对应 ThingsBoard 的 Create Alarm 节点）：将告警落库并裁剪长度。"""

    def __init__(self, feed):
        super().__init__("alarm-sink")
        self.feed = feed

    def process(self, msg: dict) -> list:
        alarms = msg.get("alarms", [])
        for a in alarms:
            a["device"] = msg["device"]
            a["ts"] = msg.get("ts")
            self.feed.alarms.append(a)
        if alarms:
            self.feed.alarms = self.feed.alarms[-100:]
        return [msg]


class PushRuleNode(RuleNode):
    """动作节点（对应 ThingsBoard 的 WebSocket/REST 动作节点）：广播给前端大屏。"""

    def __init__(self, feed):
        super().__init__("push-client")
        self.feed = feed

    def process(self, msg: dict) -> list:
        if msg.get("type") == "alarm":
            self.feed.broadcast({"type": "alarm", "alarms": msg["alarms"]})
        else:
            self.feed.broadcast({
                "type": "metrics", "device": msg["device"],
                "points": msg.get("points", []), "ts": msg.get("ts"),
            })
        return []


class RuleChain:
    """规则链：按 `nodes` 顺序串联，msg 逐节点流动；任一节点返回空列表则链路终止。"""

    def __init__(self, nodes: list):
        self.nodes = nodes

    def accept(self, msg: dict):
        current = [msg]
        for node in self.nodes:
            nxt = []
            for m in current:
                try:
                    out = node.process(m)
                except Exception as e:
                    log.warning("规则节点 %s 处理异常: %s", node.name, e)
                    continue
                if isinstance(out, list):
                    nxt.extend(out)
                elif out:
                    nxt.append(out)
            current = nxt
            if not current:
                break


def build_default_chain(storage, feed, cfg: dict) -> RuleChain:
    """构建默认规则链：与 ThingsBoard 典型遥测处理管线一致。"""
    devices_by_id = {d["id"]: d for d in cfg["devices"]}
    return RuleChain([
        TelemetryFilterNode(),
        SaveTsNode(storage),
        SnapshotNode(feed),
        ThresholdRuleNode(devices_by_id),
        AlarmRuleNode(feed),
        PushRuleNode(feed),
    ])
