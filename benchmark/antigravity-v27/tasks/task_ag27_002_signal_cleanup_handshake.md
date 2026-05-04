# Task: Signal Cleanup Handshake (task_ag27_002)

## Context
Our long-running worker processes need a way to perform an orderly shutdown when requested by the orchestrator.

## Request
Implement `setup_signal_handler()` in `worker.py`.
1. It must register a handler for the `signal.SIGUSR1` signal.
2. The handler should:
    - Set the global variable `TERMINATE_REQUESTED` to `True`.
    - Print `"CLEANUP_INITIATED"`.
3. The function `setup_signal_handler()` should also initialize `TERMINATE_REQUESTED = False`.

## Constraints
- ONLY modify `worker.py`.
- You MUST use the `signal` module.

## Verification
Run `python3 test_signals.py`.
