#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results

echo "Starting infrastructure..."
docker compose up -d --build edge1 edge2 gateway mlflow mlops-controller aiops-controller prometheus grafana

echo "Waiting for services to become ready..."
for url in http://localhost:8080/health http://localhost:5000/health http://localhost:9090/-/ready http://localhost:3000/api/health; do
  echo "Checking $url"
  for _ in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  curl -fsS "$url" >/dev/null
 done

echo "Starting traffic generator..."
docker compose run --rm traffic-generator

echo
 echo "Experiment completed."
echo "Results: results/requests.csv"
echo "Grafana: http://localhost:3000 (admin/admin)"
echo "Prometheus targets: http://localhost:9090/targets"
echo "MLflow: http://localhost:5000"
echo
 echo "Useful logs:"
echo "  docker compose logs -f mlops-controller aiops-controller"
