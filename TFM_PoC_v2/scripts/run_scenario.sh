#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
SCENARIO="${1:-E0}"
case "$SCENARIO" in E0|E1|E2) ;; *) echo "Usage: $0 E0|E1|E2" >&2; exit 2;; esac
export SCENARIO
mkdir -p results_v2
# Preserve any existing output rather than overwrite it.
if [ -e "results_v2/${SCENARIO}.csv" ]; then
  echo "Refusing to overwrite results_v2/${SCENARIO}.csv; archive or rename it first" >&2
  exit 1
fi
# Only the v2 project is affected; -v clears stateful monitoring/model volumes.
docker compose down -v --remove-orphans
docker compose up -d --build edge1 edge2 gateway mlflow prometheus grafana
if [ "$SCENARIO" = E1 ]; then
  docker compose up -d mlops-controller
else
  docker compose stop mlops-controller >/dev/null 2>&1 || true
fi
if [ "$SCENARIO" = E2 ]; then
  docker compose up -d aiops-controller
else
  docker compose stop aiops-controller >/dev/null 2>&1 || true
fi
for url in http://localhost:8080/health http://localhost:5000/health; do
  ready=0
  for i in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then ready=1; break; fi
    sleep 2
  done
  if [ "$ready" != 1 ]; then echo "Not ready: $url" >&2; exit 1; fi
done
mkdir -p "results_v2/logs_${SCENARIO}"
docker compose config > "results_v2/logs_${SCENARIO}/compose.resolved.yaml"
docker compose run --rm traffic-generator
docker compose logs --no-color > "results_v2/logs_${SCENARIO}/docker.log"
echo "Finished $SCENARIO: results_v2/${SCENARIO}.csv"
