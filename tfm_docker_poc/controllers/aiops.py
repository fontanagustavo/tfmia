import os
import time
import requests

GATEWAY = os.getenv("GATEWAY_URL", "http://gateway:8000")
EDGES = {"edge1": os.getenv("EDGE1_URL", "http://edge1:8000"), "edge2": os.getenv("EDGE2_URL", "http://edge2:8000")}
MAX_HEALTH_SECONDS = float(os.getenv("MAX_HEALTH_SECONDS", "0.08"))
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "2"))
RECOVERY_CHECKS = int(os.getenv("RECOVERY_CHECKS", "3"))
healthy_streak = {e: 0 for e in EDGES}
state = {e: True for e in EDGES}

while True:
    for edge, url in EDGES.items():
        start = time.perf_counter()
        ok = False
        try:
            r = requests.get(f"{url}/health", timeout=1)
            r.raise_for_status()
            elapsed = time.perf_counter() - start
            ok = elapsed <= MAX_HEALTH_SECONDS
        except requests.RequestException:
            elapsed = 999
        if ok:
            healthy_streak[edge] += 1
            if not state[edge] and healthy_streak[edge] >= RECOVERY_CHECKS:
                requests.post(f"{GATEWAY}/admin/route", json={"edge": edge, "active": True}, timeout=2)
                state[edge] = True
                print(f"AIOps: restored {edge}; health latency={elapsed:.3f}s", flush=True)
        else:
            healthy_streak[edge] = 0
            if state[edge] and any(state[e] for e in state if e != edge):
                requests.post(f"{GATEWAY}/admin/route", json={"edge": edge, "active": False}, timeout=2)
                state[edge] = False
                print(f"AIOps: isolated {edge}; health latency={elapsed:.3f}s", flush=True)
    time.sleep(POLL_SECONDS)
