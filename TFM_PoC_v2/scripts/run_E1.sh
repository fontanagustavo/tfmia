#!/usr/bin/env bash
set -euo pipefail
exec "$(dirname "$0")/run_scenario.sh" E1
python3 scripts/validate_results.py results_v2/E1.csv