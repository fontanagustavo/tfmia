import csv
import os
import random
import statistics
import time
from pathlib import Path

import requests

GATEWAY = os.getenv("GATEWAY_URL", "http://gateway:8000")
EDGE1 = os.getenv("EDGE1_URL", "http://edge1:8000")
DURATION = int(os.getenv("DURATION_SECONDS", "120"))
RATE = float(os.getenv("REQUESTS_PER_SECOND", "15"))
DRIFT_AT = int(os.getenv("DRIFT_AT_SECONDS", "35"))
CONGEST_AT = int(os.getenv("CONGEST_AT_SECONDS", "65"))
CONGEST_DURATION = int(os.getenv("CONGEST_DURATION_SECONDS", "25"))
OUTPUT = Path(os.getenv("OUTPUT_CSV", "/results/requests.csv"))
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

rows = []
start = time.time()
congestion_applied = False
congestion_cleared = False

while time.time() - start < DURATION:
    elapsed = time.time() - start
    true_threshold = 0.0 if elapsed < DRIFT_AT else 1.0
    x = random.gauss(true_threshold, 1.1)
    label = 1 if x >= true_threshold else 0

    if elapsed >= CONGEST_AT and not congestion_applied:
        requests.post(f"{EDGE1}/admin/netem", json={"delay_ms": 180, "jitter_ms": 30, "loss_pct": 1.0}, timeout=3)
        congestion_applied = True
        print("Traffic: congestion injected into edge1", flush=True)
    if elapsed >= CONGEST_AT + CONGEST_DURATION and congestion_applied and not congestion_cleared:
        requests.post(f"{EDGE1}/admin/netem", json={"delay_ms": 0, "jitter_ms": 0, "loss_pct": 0}, timeout=3)
        congestion_cleared = True
        print("Traffic: congestion cleared from edge1", flush=True)

    t0 = time.perf_counter()
    status, edge, correct = 0, "none", False
    try:
        r = requests.post(f"{GATEWAY}/infer", json={"x": x, "label": label}, timeout=4)
        status = r.status_code
        if r.ok:
            data = r.json()
            edge = data.get("gateway_edge", "unknown")
            correct = bool(data.get("correct", False))
    except requests.RequestException:
        status = 599
    latency_ms = (time.perf_counter() - t0) * 1000
    rows.append({"elapsed_s": round(elapsed,3), "latency_ms": round(latency_ms,3), "status": status, "edge": edge, "correct": int(correct), "drift": int(elapsed >= DRIFT_AT), "congestion": int(CONGEST_AT <= elapsed < CONGEST_AT + CONGEST_DURATION)})
    time.sleep(max(0, 1.0 / RATE))

with OUTPUT.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader(); writer.writerows(rows)

ok = [r for r in rows if r["status"] == 200]
lat = [r["latency_ms"] for r in ok]
acc = sum(r["correct"] for r in ok) / len(ok) if ok else 0
print({"requests": len(rows), "success": len(ok), "mean_latency_ms": statistics.mean(lat) if lat else None, "p95_latency_ms": sorted(lat)[int(.95*(len(lat)-1))] if lat else None, "accuracy": acc, "output": str(OUTPUT)}, flush=True)
