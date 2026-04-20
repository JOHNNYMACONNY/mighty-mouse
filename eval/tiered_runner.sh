#!/bin/bash
# Mighty Mouse Tiered Runner (Optimization Gated) - Mac Compatible
# Usage: ./tiered_runner.sh <config_yaml> [num_screening_tasks]

CONFIG=${1:-configs/mighty_mouse_v1.yaml}
SCREEN_COUNT=${2:-10}
TASK_DIR="tasks/benchmark"
LOG_DIR="logs/opt"
mkdir -p "$LOG_DIR"

echo "Mighty Mouse Optimization Gate (Mac): $CONFIG"

# 1. SCREENING PHASE
echo "Phase 1: Screening ($SCREEN_COUNT random tasks)..."

# Use Python for random selection (Mac-compatible)
SELECTED_TASKS=$(ls "$TASK_DIR"/*.json | python3 -c "import sys, random; tasks=sys.stdin.readlines(); random.shuffle(tasks); print(''.join(tasks[:$SCREEN_COUNT]).strip())")

if [ -z "$SELECTED_TASKS" ]; then
    echo "Error: No tasks found in $TASK_DIR"
    exit 1
fi

TOTAL_PASS=0
for task in $SELECTED_TASKS; do
    tid=$(basename "$task" .json)
    echo "Running screen: $tid"
    bash eval/reset_workspace.sh
    python3 src/orchestrator/mighty_mouse_agent.py "$CONFIG" "$task"
    python3 eval/run_benchmark.py "$task" > "$LOG_DIR/screen_$tid.log" 2>&1
    
    if grep -q "success verified" "$LOG_DIR/screen_$tid.log"; then
        echo "PASS: $tid"
        TOTAL_PASS=$((TOTAL_PASS + 1))
    else
        echo "FAIL: $tid"
    fi
done

SCORE=$(echo "scale=2; $TOTAL_PASS * 100 / $SCREEN_COUNT" | bc)
echo "Screening Score: $SCORE%"

# 2. STRESS PHASE (Only if Screening >= 90%)
if (( $(echo "$SCORE < 90.00" | bc -l) )); then
    echo "Gating Failed: Score below 90%. Aborting stress test."
    echo "FINAL_SCORE: $SCORE"
    exit 0
fi

echo "Phase 2: Stress Test (Full 50-task suite)..."
export MAX_ROUNDS=2
bash eval/run_iteration.sh tier_1
