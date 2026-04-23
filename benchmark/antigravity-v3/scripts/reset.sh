#!/bin/bash
# Reset script for Antigravity v3
# Usage: ./reset.sh <task_id>

TASK_ID=$1
BASE_DIR="/Volumes/YBF_Storage/Projects/mighty_mouse/benchmark/antigravity-v3"
RUN_DIR="${BASE_DIR}/runs/${TASK_ID}"

if [ -z "$TASK_ID" ]; then
    echo "Usage: ./reset.sh <task_id>"
    exit 1
fi

echo "Resetting workspace for ${TASK_ID}..."
rm -rf "${RUN_DIR}"
mkdir -p "${RUN_DIR}"
cp -r "${BASE_DIR}/fixtures/${TASK_ID}/." "${RUN_DIR}/"

echo "Done. Workspace ready at ${RUN_DIR}"
