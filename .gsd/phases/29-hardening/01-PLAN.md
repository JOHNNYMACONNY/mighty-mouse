# Plan: Phase 29 - Performance & Telemetry Hardening

## Objective
Promote `run_parallel.py` to the primary execution path and consolidate token/latency metrics into the benchmark results.

## Context
- `eval/run_parallel.py`: Current parallel runner.
- `eval/solve_benchmark.py`: Sequential runner (to be updated).
- `src/orchestrator/gemini_client.py`: Needs token tracking.
- `src/orchestrator/mighty_mouse_agent.py`: Needs metadata update.

## Tasks

### 1. Telemetry Capture [auto]
- **Action**: Modify `gemini_client.py` to capture token counts from API responses and store them in `self.last_metadata`.
- **Verify**: Run a simulation task and check `logs/last_agent_run.json` for `usage` fields.

### 2. Parallel Integration [auto]
- **Action**: Update `solve_benchmark.py` to support `--parallel` and delegate to `run_parallel.main()`.
- **Verify**: `python3 eval/solve_benchmark.py --parallel --tier tier_1` should execute tasks in parallel.

### 3. Metric Consolidation [auto]
- **Action**: Update `run_parallel.py` to aggregate token counts and latency into the final `benchmark_results.json`.
- **Verify**: Check `logs/benchmark_results.json` for top-level `summary` and per-task `usage` metrics.

### 4. Schema Resilience [auto]
- **Action**: Update `ResponseParser` and `mighty_mouse_agent.py` to detect and log "No files found" errors.
- **Verify**: Mock an empty XML response and verify the reason in `benchmark_results.json` is "Schema Error: No files found".
