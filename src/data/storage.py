"""
数据层 · 时序存储（借鉴 iot-dc3 数据层）
--------------------------------------
负责设备时序数据的落库与查询。演示用 SQLite 时序表，生产可替换为
InfluxDB / TimescaleDB（iot-dc3 默认 TimescaleDB）。提供 latest / history 接口。
"""
import os
import sqlite3
import time


class TimeSeriesStore:
    def __init__(self, path: str = "data/iot.db"):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init()

    def _init(self):
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS metrics(
                   ts INTEGER, device TEXT, point TEXT, value REAL)"""
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_metrics_dp ON metrics(device, point, ts)"
        )
        self.conn.commit()

    def add(self, device: str, point: str, value: float, ts: int = None):
        ts = ts or int(time.time() * 1000)
        self.conn.execute(
            "INSERT INTO metrics(ts, device, point, value) VALUES(?,?,?,?)",
            (ts, device, point, value),
        )
        self.conn.commit()

    def latest(self, device: str) -> dict:
        cur = self.conn.execute(
            "SELECT point, value, ts FROM metrics WHERE device=? AND ts=("
            "SELECT MAX(ts) FROM metrics WHERE device=?)",
            (device, device),
        )
        return {row[0]: {"value": row[1], "ts": row[2]} for row in cur.fetchall()}

    def history(self, device: str, point: str, limit: int = 200) -> list:
        cur = self.conn.execute(
            "SELECT ts, value FROM metrics WHERE device=? AND point=? "
            "ORDER BY ts DESC LIMIT ?",
            (device, point, limit),
        )
        return [{"ts": r[0], "value": r[1]} for r in reversed(cur.fetchall())]

    def close(self):
        self.conn.close()
