import os
import threading
import time
from collections import deque
from statistics import mean
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

NODE_ID = os.getenv("NODE_ID", "edge")
MODEL_THRESHOLD = float(os.getenv("MODEL_THRESHOLD", "0"))
WINDOW_SIZE = int(os.getenv("WINDOW_SIZE", "200"))
SIMULATED_DELAY_MS = 0
MODEL_VERSION = 0
lock = threading.RLock()
samples = deque(maxlen=WINDOW_SIZE)
latencies = deque(maxlen=100)  # (monotonic timestamp, milliseconds)
app = FastAPI(title=f"Edge inference node {NODE_ID} - v2")
REQS = Counter("edge_requests_total", "Requests processed", ["node", "status"])
LAT = Histogram("edge_request_latency_seconds", "Inference latency", ["node"], buckets=(.005,.01,.025,.05,.1,.2,.5,1.0))
ACC = Gauge("edge_model_accuracy", "Rolling model accuracy", ["node"])
THRESH = Gauge("edge_model_threshold", "Classifier threshold", ["node"])
SAMPLES = Gauge("edge_window_samples", "Samples in window", ["node"])
THRESH.labels(NODE_ID).set(MODEL_THRESHOLD)

class InferRequest(BaseModel):
    x: float
    label: int = Field(ge=0, le=1)
class DelayRequest(BaseModel):
    delay_ms: int = Field(default=0, ge=0, le=10000)
    jitter_ms: int = 0
    loss_pct: float = 0

def rolling_accuracy():
    if not samples:
        return 1.0
    return sum(int((x >= MODEL_THRESHOLD) == bool(y)) for x,y in samples) / len(samples)

@app.get("/health")
def health():
    with lock:
        return {"status":"ok", "node":NODE_ID,"threshold":MODEL_THRESHOLD,"accuracy":rolling_accuracy(),"samples":len(samples),"model_version":MODEL_VERSION}

@app.get("/operational-status")
def operational_status():
    with lock:
        now=time.monotonic()
        recent=[ms for ts,ms in latencies if now-ts <= 10]
        return {"node":NODE_ID,"samples":len(recent),"mean_latency_ms":mean(recent) if recent else None,
                "configured_delay_ms":SIMULATED_DELAY_MS,"simulation":"application_delay"}

@app.post("/infer")
def infer(req:InferRequest):
    started=time.perf_counter()
    try:
        with lock:
            delay=SIMULATED_DELAY_MS
            threshold=MODEL_THRESHOLD
        if delay:
            time.sleep(delay/1000)
        pred=int(req.x >= threshold)
        with lock:
            samples.append((req.x,req.label))
            acc=rolling_accuracy()
            ACC.labels(NODE_ID).set(acc)
            SAMPLES.labels(NODE_ID).set(len(samples))
        REQS.labels(NODE_ID,"ok").inc()
        return {"node":NODE_ID,"prediction":pred,"label":req.label,"correct":pred==req.label,"accuracy":acc}
    except Exception as exc:
        REQS.labels(NODE_ID,"error").inc()
        raise HTTPException(status_code=500,detail=str(exc))
    finally:
        elapsed=time.perf_counter()-started
        LAT.labels(NODE_ID).observe(elapsed)
        with lock:
            latencies.append((time.monotonic(),elapsed*1000))

@app.post("/retrain")
def retrain():
    global MODEL_THRESHOLD,MODEL_VERSION
    with lock:
        dataset=list(samples)
        if len(dataset)<40:
            raise HTTPException(status_code=409,detail="Need at least 40 labeled samples for train/holdout")
        train=dataset[::2]
        holdout=dataset[1::2]
        candidates=sorted({x for x,_ in train})
        def accuracy(threshold,rows):
            return sum(int((x>=threshold)==bool(y)) for x,y in rows)/len(rows)
        best_t=max(candidates,key=lambda t:accuracy(t,train))
        train_acc=accuracy(best_t,train)
        evaluation_acc=accuracy(best_t,holdout)
        old_eval=accuracy(MODEL_THRESHOLD,holdout)
        # A new model is only deployed if holdout accuracy is not worse.
        deployed=evaluation_acc >= old_eval
        if deployed:
            MODEL_THRESHOLD=float(best_t)
            MODEL_VERSION+=1
            THRESH.labels(NODE_ID).set(MODEL_THRESHOLD)
        ACC.labels(NODE_ID).set(rolling_accuracy())
        return {"node":NODE_ID,"new_threshold":MODEL_THRESHOLD,"candidate_threshold":float(best_t),
                "training_accuracy":train_acc,"evaluation_accuracy":evaluation_acc,
                "previous_evaluation_accuracy":old_eval,"deployed":deployed,
                "model_version":MODEL_VERSION,"training_samples":len(train),"evaluation_samples":len(holdout)}

@app.post("/admin/netem")
def set_delay(req:DelayRequest):
    global SIMULATED_DELAY_MS
    if req.jitter_ms or req.loss_pct:
        raise HTTPException(status_code=422,detail="v2 supports application delay only; jitter/loss are not implemented")
    with lock:
        SIMULATED_DELAY_MS=req.delay_ms
        latencies.clear()  # avoid stale samples after recovery
    return {"node":NODE_ID,"simulation":"application_delay","delay_ms":SIMULATED_DELAY_MS}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
