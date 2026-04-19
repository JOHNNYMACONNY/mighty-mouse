#!/bin/bash
# Master verification script for autoresearch loop
# Usage: ./eval/run_iteration.sh [tier]

TIER=${1:-tier_1}

echo "Starting Mighty Mouse Optimization Iteration (Tier: $TIER)..."

# 1. Run the benchmark solver
python3 eval/solve_benchmark.py "$TIER"

# 2. Score the results (Weighted)
SCORE=$(python3 eval/score_metrics.py)

echo "Iteration Score: $SCORE"

# Autoresearch expects the score as the final output
echo "$SCORE"
