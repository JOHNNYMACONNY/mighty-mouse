#!/bin/bash
# Mighty Mouse Iteration Runner (with State Recovery)
TIER=${1:-tier_1}
RESUME=${RESUME:-0}
CHECKPOINT="logs/session_checkpoint.json"

echo "Starting Mighty Mouse Optimization Iteration (Tier: $TIER, Resume: $RESUME)..."

if [ "$RESUME" -eq 0 ]; then
    echo "Fresh run: clearing logs and checkpoints..."
    rm -f logs/benchmark_results.json
    rm -f "$CHECKPOINT"
fi

SOLVER="src/orchestrator/mighty_mouse_agent.py"
CONFIG="configs/mighty_mouse_v1.yaml"
TASK_DIR="tasks/benchmark"

mkdir -p logs

for task_file in $TASK_DIR/*.json; do
    task_id=$(basename "$task_file" .json)
    if [ "$RESUME" -eq 1 ] && [ -f "$CHECKPOINT" ]; then
        if grep -q "\"$task_id\"" "$CHECKPOINT"; then
            echo "Task $task_id already completed. Skipping..."
            continue
        fi
    fi
    echo "Executing Task: $task_id"
    bash eval/reset_workspace.sh
    python3 "$SOLVER" "$CONFIG" "$task_file"
    python3 eval/run_benchmark.py "$task_file"
done
python3 src/orchestrator/analyze_failure.py
python3 eval/score_metrics.py
