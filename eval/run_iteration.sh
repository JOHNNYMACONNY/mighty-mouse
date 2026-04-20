#!/bin/bash
# Mighty Mouse Iteration Runner (v2: Multi-Round Reasoning)
TIER=${1:-tier_1}
RESUME=${RESUME:-0}
MAX_ROUNDS=${MAX_ROUNDS:-2}
CHECKPOINT="logs/session_checkpoint.json"

echo "Starting Mighty Mouse Multi-Round Optimization (Tier: $TIER, Max Rounds: $MAX_ROUNDS)..."

if [ "$RESUME" -eq 0 ]; then
    rm -f logs/benchmark_results.json
    rm -f "$CHECKPOINT"
fi

SOLVER="src/orchestrator/mighty_mouse_agent.py"
CONFIG="configs/mighty_mouse_v1.yaml"
TASK_DIR="tasks/benchmark"
mkdir -p logs

for task_file in $TASK_DIR/*.json; do
    task_id=$(basename "$task_file" .json)
    
    if [ "$RESUME" -eq 1 ] && [ -f "$CHECKPOINT" ] && grep -q "\"$task_id\"" "$CHECKPOINT"; then
        echo "Task $task_id already completed. Skipping..."
        continue
    fi

    echo "--- Executing Task: $task_id ---"
    rm -f logs/feedback.txt

    for round in $(seq 1 $MAX_ROUNDS); do
        echo "Round $round..."
        bash eval/reset_workspace.sh
        
        # If round > 1, the solver should look for logs/feedback.txt
        python3 "$SOLVER" "$CONFIG" "$task_file"
        python3 eval/run_benchmark.py "$task_file" > logs/round_output.txt 2>&1
        
        if grep -q "success verified" logs/round_output.txt; then
            echo "Task $task_id SUCCESS in round $round."
            break
        else
            echo "Task $task_id FAILED in round $round. Capturing feedback..."
            # Capture the JSON failure reason for the next round
            tail -n 20 logs/benchmark_results.json > logs/feedback.txt
        fi
    done
done

python3 src/orchestrator/analyze_failure.py
python3 eval/score_metrics.py
