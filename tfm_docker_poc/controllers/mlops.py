import os
import time
from datetime import datetime, timezone

import mlflow
import requests

EDGES = {
    "edge1": os.getenv("EDGE1_URL", "http://edge1:8000"),
    "edge2": os.getenv("EDGE2_URL", "http://edge2:8000"),
}
MIN_ACCURACY = float(os.getenv("MIN_ACCURACY", "0.78"))
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "5"))
COOLDOWN = float(os.getenv("RETRAIN_COOLDOWN_SECONDS", "20"))
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "tfm-mlops-drift")
last_retrain = {edge: 0.0 for edge in EDGES}


def wait_for_mlflow() -> None:
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            response = requests.get(f"{MLFLOW_URI}/health", timeout=2)
            if response.ok:
                return
        except requests.RequestException:
            pass
        print("MLOps: waiting for MLflow...", flush=True)
        time.sleep(2)
    raise RuntimeError("MLflow was not ready after 120 seconds")


mlflow.set_tracking_uri(MLFLOW_URI)
wait_for_mlflow()
mlflow.set_experiment(EXPERIMENT_NAME)

run_name = f"monitoring-session-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
with mlflow.start_run(run_name=run_name) as monitoring_run:
    mlflow.set_tag("component", "mlops-controller")
    mlflow.set_tag("purpose", "continuous drift monitoring")
    mlflow.log_param("min_accuracy", MIN_ACCURACY)
    mlflow.log_param("poll_seconds", POLL_SECONDS)
    print(f"MLOps: monitoring run started: {monitoring_run.info.run_id}", flush=True)

    step = 0
    while True:
        for edge, url in EDGES.items():
            try:
                response = requests.get(f"{url}/health", timeout=2)
                response.raise_for_status()
                health = response.json()
                accuracy = float(health["accuracy"])
                threshold = float(health["threshold"])

                mlflow.log_metric(f"{edge}_accuracy", accuracy, step=step)
                mlflow.log_metric(f"{edge}_threshold", threshold, step=step)

                if accuracy < MIN_ACCURACY and time.time() - last_retrain[edge] > COOLDOWN:
                    before = accuracy
                    result = requests.post(f"{url}/retrain", timeout=10)
                    if result.ok:
                        data = result.json()
                        after = float(data["training_accuracy"])
                        mlflow.log_metric(f"{edge}_retrain_accuracy_before", before, step=step)
                        mlflow.log_metric(f"{edge}_retrain_accuracy_after", after, step=step)
                        mlflow.log_metric(f"{edge}_retrain_new_threshold", float(data["new_threshold"]), step=step)
                        mlflow.set_tag(f"{edge}_last_retrain_status", "success")
                        print(f"MLOps: retrained {edge}: {data}", flush=True)
                    else:
                        mlflow.set_tag(f"{edge}_last_retrain_status", f"failed:{result.status_code}")
                        print(f"MLOps: retrain failed for {edge}: {result.text}", flush=True)
                    last_retrain[edge] = time.time()
            except Exception as exc:
                mlflow.set_tag(f"{edge}_last_error", str(exc)[:250])
                print(f"MLOps: error checking {edge}: {exc}", flush=True)
        step += 1
        time.sleep(POLL_SECONDS)
