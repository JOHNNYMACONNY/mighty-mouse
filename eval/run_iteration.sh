#!/bin/bash
# Mighty Mouse Iteration Runner
TIER=${1:-tier_1}
echo "Starting Mighty Mouse Optimization Iteration (Tier: $TIER)..."

# Initial cleanup of the results file to ensure a fresh score
rm -f logs/benchmark_results.json

SOLVER="src/orchestrator/mighty_mouse_agent.py"
CONFIG="configs/mighty_mouse_v1.yaml"
TASK_DIR="tasks/benchmark"

for task in $TASK_DIR/*.json; do
    bash eval/reset_workspace.sh
    python3 "$SOLVER" "$CONFIG" "$task"
    python3 eval/run_benchmark.py "$task"
done

# Analyze Failures
python3 src/orchestrator/analyze_failure.py

# Score Extract
python3 eval/score_metrics.py
