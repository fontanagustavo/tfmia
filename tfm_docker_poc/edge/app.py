import os
import subprocess
import threading
import time
from collections import deque
from typing import Deque, Tuple

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

NODE_ID = os.getenv("NODE_ID", "edge")
MODEL_THRESHOLD = float(os.getenv("MODEL_THRESHOLD", "0.0"))
WINDOW_SIZE = int(os.getenv("WINDOW_SIZE", "200"))
SIMULATED_DELAY_MS = 0

app = FastAPI(title=f"Edge inference node {NODE_ID}")
lock = threading.Lock()
samples: Deque[Tuple[float, int]] = deque(maxlen=WINDOW_SIZE)

REQS = Counter("edge_requests_total", "Requests processed", ["node", "status"])
LAT = Histogram("edge_request_latency_seconds", "Inference latency", ["node"], buckets=(0.005,0.01,0.025,0.05,0.1,0.2,0.5,1.0))
ACC = Gauge("edge_model_accuracy", "Rolling model accuracy", ["node"])
THRESH = Gauge("edge_model_threshold", "Current classifier threshold", ["node"])
SAMPLES = Gauge("edge_window_samples", "Samples in rolling window", ["node"])

THRESH.labels(NODE_ID).set(MODEL_THRESHOLD)
ACC.labels(NODE_ID).set(1.0)

class InferRequest(BaseModel):
    x: float
    label: int

class NetemRequest(BaseModel):
    delay_ms: int = 0
    jitter_ms: int = 0
    loss_pct: float = 0.0


def rolling_accuracy() -> float:
    if not samples:
        return 1.0
    correct = sum((1 if x >= MODEL_THRESHOLD else 0) == y for x, y in samples)
    return correct / len(samples)

@app.get("/health")
def health():
    return {"status": "ok", "node": NODE_ID, "threshold": MODEL_THRESHOLD, "accuracy": rolling_accuracy()}

@app.post("/infer")
def infer(req: InferRequest):
    started = time.perf_counter()
    try:
        if SIMULATED_DELAY_MS > 0:
        	time.sleep(SIMULATED_DELAY_MS / 1000.0)

        prediction = 1 if req.x >= MODEL_THRESHOLD else 0
        with lock:
            samples.append((req.x, req.label))
            acc = rolling_accuracy()
            ACC.labels(NODE_ID).set(acc)
            SAMPLES.labels(NODE_ID).set(len(samples))
        REQS.labels(NODE_ID, "ok").inc()
        return {
		"node": NODE_ID, 
		"prediction": prediction, 
		"label": req.label, 
		"correct": prediction == req.label, 
		"accuracy": acc
		}
    
    except Exception as exc:
        REQS.labels(NODE_ID, "error").inc()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        LAT.labels(NODE_ID).observe(time.perf_counter() - started)

@app.post("/retrain")
def retrain():
    global MODEL_THRESHOLD
    with lock:
        if len(samples) < 20:
            raise HTTPException(status_code=409, detail="Not enough samples")
        candidates = sorted({x for x, _ in samples})
        best_t, best_acc = MODEL_THRESHOLD, -1.0
        for t in candidates:
            acc = sum((1 if x >= t else 0) == y for x, y in samples) / len(samples)
            if acc > best_acc:
                best_t, best_acc = t, acc
        MODEL_THRESHOLD = float(best_t)
        THRESH.labels(NODE_ID).set(MODEL_THRESHOLD)
        ACC.labels(NODE_ID).set(best_acc)
    return {"node": NODE_ID, "new_threshold": MODEL_THRESHOLD, "training_accuracy": best_acc, "samples": len(samples)}

@app.post("/admin/netem")
def set_netem(req: NetemRequest):
    global SIMULATED_DELAY_MS

    SIMULATED_DELAY_MS = max(0, req.delay_ms)

    return {
        "node": NODE_ID,
        "simulation": "application_delay",
        "delay_ms": SIMULATED_DELAY_MS
    }

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
