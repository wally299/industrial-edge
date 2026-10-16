"""
应用层 · RESTful API + WebSocket（借鉴 iot-dc3 应用层 / 可视化大屏）
---------------------------------------------------------------
- /api/devices            设备清单 + 最新工况
- /api/devices/{id}/history?point=&limit=  时序历史（供折线图）
- /api/alarms             当前告警
- /ws                     实时推送（指标 / 告警 / 快照）
"""
import json
import os

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.feed import feed
from data.storage import TimeSeriesStore

app = FastAPI(title="Industrial-Edge 工业互联网边缘采集平台")

storage: TimeSeriesStore = None
cfg = None
WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "web")
os.makedirs(os.path.join(WEB_DIR, "static"), exist_ok=True)
app.mount("/static", StaticFiles(directory=os.path.join(WEB_DIR, "static")), name="static")


def configure(s: TimeSeriesStore, c: dict):
    global storage, cfg
    storage = s
    cfg = c


@app.get("/api/devices")
def api_devices():
    out = []
    for d in cfg["devices"]:
        out.append({
            "id": d["id"],
            "name": d["name"],
            "points": d["points"],
            "latest": storage.latest(d["id"]) if storage else {},
        })
    return out


@app.get("/api/devices/{device_id}/history")
def api_history(device_id: str, point: str, limit: int = 200):
    if storage:
        return storage.history(device_id, point, limit)
    return []


@app.get("/api/alarms")
def api_alarms(limit: int = 50):
    return feed.alarms[-limit:]


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    q = await feed.connect(ws)
    await q.put(json.dumps({
        "type": "snapshot",
        "latest": feed.latest,
        "alarms": feed.alarms[-20:],
        "config": cfg["devices"],
    }, ensure_ascii=False))
    # 单任务发送循环：避免 Starlette 同一 WebSocket 跨任务 send/receive 冲突
    try:
        while True:
            data = await q.get()
            await ws.send_text(data)
    except Exception:
        pass
    finally:
        await feed.disconnect(q)


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))
