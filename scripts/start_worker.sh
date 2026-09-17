#!/usr/bin/env bash
# Taskiq worker for the "items" queue. One script per queue; copy and edit
# BROKER/TASKS_MODULE when you add a new broker in src/taskiq_brokers.py.
set -euo pipefail

set -a
[ -f .env ] && source .env
set +a

BROKER="${BROKER:-src.taskiq_brokers:items_broker}"
TASKS_MODULE="${TASKS_MODULE:-src.items.tasks}"

taskiq worker \
    --workers "${WORKERS:-2}" \
    --max-async-tasks "${MAX_ASYNC_TASKS:-50}" \
    --ack-type when_received \
    "$BROKER" \
    "$TASKS_MODULE"
