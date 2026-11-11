import csv,os,random,statistics,time
from pathlib import Path
import requests
GATEWAY=os.getenv("GATEWAY_URL","http://gateway:8000")
EDGE1=os.getenv("EDGE1_URL","http://edge1:8000")
SCENARIO=os.getenv("SCENARIO","E0").upper()
if SCENARIO not in {"E0","E1","E2"}:
    raise ValueError("SCENARIO must be E0, E1 or E2")
SEED=int(os.getenv("RANDOM_SEED","42"));rng=random.Random(SEED)
DURATION=float(os.getenv("DURATION_SECONDS","120"))
RATE=float(os.getenv("REQUESTS_PER_SECOND","15"))
if RATE<=0:raise ValueError("RATE must be positive")
DRIFT_AT=float(os.getenv("DRIFT_AT_SECONDS","35"))
CONGEST_AT=float(os.getenv("CONGEST_AT_SECONDS","35"))
CONGEST_DURATION=float(os.getenv("CONGEST_DURATION_SECONDS","25"))
OUTPUT=Path(os.getenv("OUTPUT_CSV",f"/results/{SCENARIO.lower()}.csv"))
OUTPUT.parent.mkdir(parents=True,exist_ok=True)
rows=[];start=time.monotonic();next_send=start;congested=False
try:
    while True:
        now=time.monotonic();elapsed=now-start
        if elapsed>=DURATION:break
        if now<next_send:time.sleep(next_send-now)
        now=time.monotonic();elapsed=now-start
        if elapsed>=DURATION:break
        if SCENARIO=="E2":
            if elapsed>=CONGEST_AT and not congested and elapsed<CONGEST_AT+CONGEST_DURATION:
                r=requests.post(f"{EDGE1}/admin/netem",json={"delay_ms":180},timeout=3);r.raise_for_status();congested=True
                print("Traffic: injected 180ms application delay",flush=True)
            if congested and elapsed>=CONGEST_AT+CONGEST_DURATION:
                r=requests.post(f"{EDGE1}/admin/netem",json={"delay_ms":0},timeout=3);r.raise_for_status();congested=False
                print("Traffic: cleared application delay",flush=True)
        drift=SCENARIO=="E1" and elapsed>=DRIFT_AT
        true_threshold=1.0 if drift else 0.0
        x=rng.gauss(true_threshold,1.1)
        label=int(x>=true_threshold)
        t0=time.perf_counter();status=599;edge="none";correct=False
        try:
            r=requests.post(f"{GATEWAY}/infer",json={"x":x,"label":label},timeout=4)
            status=r.status_code
            if r.ok:
                d=r.json();edge=d.get("gateway_edge","unknown");correct=bool(d.get("correct",False))
        except requests.RequestException:
            pass
        latency_ms=(time.perf_counter()-t0)*1000
        rows.append({"elapsed_s":round(elapsed,3),"latency_ms":round(latency_ms,3),"status":status,
                     "edge":edge,"correct":int(correct),"drift":int(drift),
                     "congestion":int(SCENARIO=="E2" and CONGEST_AT<=elapsed<CONGEST_AT+CONGEST_DURATION)})
        next_send+=1.0/RATE
        # A synchronous client cannot catch up by sending overlapping requests.
        if next_send<time.monotonic():next_send=time.monotonic()
finally:
    if SCENARIO=="E2" and congested:
        try:requests.post(f"{EDGE1}/admin/netem",json={"delay_ms":0},timeout=3).raise_for_status()
        except requests.RequestException as exc:print(f"WARNING: could not clear delay: {exc}",flush=True)
fields=["elapsed_s","latency_ms","status","edge","correct","drift","congestion"]
with OUTPUT.open("w",newline="") as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
ok=[r for r in rows if r["status"]==200];lat=sorted(r["latency_ms"] for r in ok)
print({"scenario":SCENARIO,"seed":SEED,"requests":len(rows),"success":len(ok),
       "mean_latency_ms":statistics.mean(lat) if lat else None,
       "p95_latency_ms":lat[int(.95*(len(lat)-1))] if lat else None,
       "accuracy":sum(r["correct"] for r in ok)/len(ok) if ok else None,
       "output":str(OUTPUT)},flush=True)
