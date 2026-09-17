#!/usr/bin/env bash
# Local API server with hot reload. Loads .env first.
set -euo pipefail

set -a
[ -f .env ] && source .env
set +a

# With New Relic (optional):
# NEW_RELIC_CONFIG_FILE=newrelic.ini newrelic-admin run-program uvicorn main:app --host 0.0.0.0 --port 8011 --reload
uvicorn main:app --host 0.0.0.0 --port 8011 --reload
