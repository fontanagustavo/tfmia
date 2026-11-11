import csv,sys
from pathlib import Path
if len(sys.argv)!=2:raise SystemExit("Usage: python scripts/validate_results.py results_v2/E0.csv")
p=Path(sys.argv[1]);rows=list(csv.DictReader(p.open()))
if not rows:raise SystemExit("FAIL: empty result file")
ok=[r for r in rows if r["status"]=="200"]
print(f"file={p} requests={len(rows)} success={len(ok)} errors={len(rows)-len(ok)}")
for edge in ("edge1","edge2"):
 print(f"{edge}={sum(r['edge']==edge for r in ok)}")
if ok:
 print(f"accuracy={sum(int(r['correct']) for r in ok)/len(ok):.4%}")
 print(f"mean_latency_ms={sum(float(r['latency_ms']) for r in ok)/len(ok):.3f}")
print("NOTE: this summary does not certify equivalence to published results or AIOps event transitions")
