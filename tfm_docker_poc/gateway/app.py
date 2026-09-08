import os
import threading
import time
from itertools import cycle

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

EDGES = {"edge1": os.getenv("EDGE1_URL", "http://edge1:8000"), "edge2": os.getenv("EDGE2_URL", "http://edge2:8000")}
active = {name: True for name in EDGES}
lock = threading.Lock()
rr = cycle(EDGES.keys())
app = FastAPI(title="Adaptive gateway")

REQS = Counter("gateway_requests_total", "Gateway requests", ["edge", "status"])
LAT = Histogram("gateway_end_to_end_latency_seconds", "End-to-end latency", ["edge"], buckets=(0.01,0.025,0.05,0.1,0.2,0.5,1,2))
ACTIVE = Gauge("gateway_edge_active", "Whether an edge is active", ["edge"])
for name in EDGES: ACTIVE.labels(name).set(1)

class InferRequest(BaseModel):
    x: float
    label: int

class RouteUpdate(BaseModel):
    edge: str
    active: bool


def choose_edge() -> str:
    with lock:
        for _ in range(len(EDGES)):
            candidate = next(rr)
            if active[candidate]:
                return candidate
    raise HTTPException(status_code=503, detail="No active edge nodes")

@app.get("/health")
def health():
    return {"status": "ok", "active": active}

@app.post("/infer")
def infer(req: InferRequest):
    edge = choose_edge()
    started = time.perf_counter()
    try:
        response = requests.post(f"{EDGES[edge]}/infer", json=req.model_dump(), timeout=3)
        response.raise_for_status()
        REQS.labels(edge, "ok").inc()
        payload = response.json()
        payload["gateway_edge"] = edge
        return payload
    except requests.RequestException as exc:
        REQS.labels(edge, "error").inc()
        raise HTTPException(status_code=502, detail=f"{edge}: {exc}")
    finally:
        LAT.labels(edge).observe(time.perf_counter() - started)

@app.post("/admin/route")
def route(update: RouteUpdate):
    if update.edge not in EDGES:
        raise HTTPException(status_code=404, detail="Unknown edge")
    with lock:
        active[update.edge] = update.active
        ACTIVE.labels(update.edge).set(1 if update.active else 0)
    return {"active": active}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
