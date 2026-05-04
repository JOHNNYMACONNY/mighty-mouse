# Task: Barrier Synchronization (task_ag26_002)

## Context
Our distributed batch processor requires all workers to finish their "setup" phase before any of them can begin the "execution" phase.

## Request
Implement `sync_work(barrier, worker_id, results_list)` in `orchestrator.py`.
1. Append `f"SETUP_DONE_{worker_id}"` to `results_list`.
2. Call `barrier.wait()`.
3. Append `f"EXEC_START_{worker_id}"` to `results_list`.

## Constraints
- ONLY modify `orchestrator.py`.
- `results_list` is a `multiprocessing.Manager().list()`.
- `barrier` is a `multiprocessing.Barrier`.

## Verification
Run `python3 test_barrier.py`. The test verified that all `SETUP_DONE` entries appear in the list before any `EXEC_START` entries.
