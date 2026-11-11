import os,time,requests
GATEWAY=os.getenv("GATEWAY_URL","http://gateway:8000")
EDGES={"edge1":os.getenv("EDGE1_URL","http://edge1:8000"),"edge2":os.getenv("EDGE2_URL","http://edge2:8000")}
POLL=float(os.getenv("POLL_SECONDS","2"))
FAIL_CHECKS=int(os.getenv("FAIL_CHECKS","3"))
RECOVERY_CHECKS=int(os.getenv("RECOVERY_CHECKS","3"))
MAX_INFERENCE_MS=float(os.getenv("MAX_INFERENCE_MS","120"))
MIN_SAMPLES=int(os.getenv("MIN_LATENCY_SAMPLES","5"))
fail_streak={e:0 for e in EDGES}
healthy_streak={e:0 for e in EDGES}

def gateway_state():
    r=requests.get(f"{GATEWAY}/health",timeout=2);r.raise_for_status()
    return r.json()["active"]

def route(edge,enabled):
    r=requests.post(f"{GATEWAY}/admin/route",json={"edge":edge,"active":enabled},timeout=2)
    r.raise_for_status()
    state=gateway_state()
    if state[edge] != enabled:
        raise RuntimeError(f"Gateway route not applied for {edge}")

def check(url):
    r=requests.get(f"{url}/health",timeout=1);r.raise_for_status()
    r=requests.get(f"{url}/operational-status",timeout=1);r.raise_for_status()
    d=r.json()
    # Explicit application-delay fault is a deterministic PoC signal.
    if d["configured_delay_ms"] > MAX_INFERENCE_MS:
        return False,"injected application delay"
    if d["samples"] >= MIN_SAMPLES and d["mean_latency_ms"] > MAX_INFERENCE_MS:
        return False,"high inference latency"
    return True,"healthy"

while True:
    try:
        state=gateway_state()  # synchronize with actual gateway state on every pass
        for edge,url in EDGES.items():
            try:
                ok,reason=check(url)
            except (requests.RequestException,ValueError,KeyError) as exc:
                ok,reason=False,str(exc)
            if ok:
                fail_streak[edge]=0
                healthy_streak[edge]+=1
                if not state[edge] and healthy_streak[edge]>=RECOVERY_CHECKS:
                    route(edge,True)
                    state[edge]=True
                    print(f"AIOps: restored {edge}",flush=True)
            else:
                healthy_streak[edge]=0
                fail_streak[edge]+=1
                if state[edge] and fail_streak[edge]>=FAIL_CHECKS and any(state[e] for e in EDGES if e!=edge):
                    route(edge,False)
                    state[edge]=False
                    print(f"AIOps: isolated {edge}: {reason}",flush=True)
    except (requests.RequestException,ValueError,KeyError,RuntimeError) as exc:
        print(f"AIOps: gateway/control error: {exc}",flush=True)
    time.sleep(POLL)
