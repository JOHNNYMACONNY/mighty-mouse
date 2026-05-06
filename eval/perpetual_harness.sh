#!/bin/bash
# Perpetual Harness - Self-Play Loop Launcher

echo "Starting Perpetual Harness Launcher..."
echo "The system will run continuously, self-verifying and self-escalating."

# Ensure we are in a clean state
git add -A
git commit -m "Save state before starting perpetual loop" || true

# Launch the infinite Autoresearch loop
gemini \
  --prompt "Read the autoresearch SKILL.md and /autoresearch-mighty workflow. Start immediately. 
Goal: Achieve 100% on tier_5 and then self-escalate. 
Scope: configs/prompt_segments/*, eval/verify_metric.py, eval/subagent_spawner.py, eval/evaluation_config.json, tasks/benchmark/*
Metric: Success count (higher is better).
Verify: python3 eval/verify_metric.py tier_5
Guard: python3 eval/verify_metric.py tier_1

CRITICAL: You are allowed to use 'Workflow Mutation' (writing Python worker scripts using eval/subagent_spawner.py) and 'Harness Modification' (modifying eval/verify_metric.py extend_telemetry hook) if prompt mutation gets stuck. 
Do not pause, do not ask questions, iterate forever." \
  --yolo

echo "Harness terminated."
