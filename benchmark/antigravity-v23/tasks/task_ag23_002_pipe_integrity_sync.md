# Task: Pipe Integrity Sync (task_ag23_002)

## Context
Our multi-process architecture requires guaranteed delivery of messages between the control and worker processes.

## Request
Implement `relay_message(pipe, message)` in `relay.py`.
1. Send the `message` string through the `pipe` (use `pipe.send()`).
2. Wait for a response from the pipe (use `pipe.poll(timeout=1)` then `pipe.recv()`).
3. If the response is exactly `"ACK"`, return `True`.
4. If no response arrives within 1 second, or the response is not `"ACK"`, print `RELAY_TIMEOUT` and return `False`.

## Constraints
- ONLY modify `relay.py`.
- You MUST handle potential `EOFError` or `BrokenPipeError` gracefully by returning `False`.

## Verification
Run `python3 test_relay.py`.
