# Task: Mmap Buffer Sync (task_ag28_001)

## Context
Our high-frequency trading simulator uses memory-mapped files for low-latency communication. We need a way to synchronize access without the overhead of OS-level locks.

## Request
Implement `write_data(mm, data)` and `read_data(mm)` in `mmap_comms.py`.
1. The first byte of the mmap (`mm[0]`) is the status flag.
2. `write_data`:
    - Wait until `mm[0] == 0`.
    - Set `mm[0] = 1`.
    - Write the `data` (string) starting from offset 1.
    - Set `mm[0] = 2`.
3. `read_data`:
    - Wait until `mm[0] == 2`.
    - Read the data from offset 1 (until the first null byte).
    - Set `mm[0] = 0`.
    - Return the data.

## Constraints
- ONLY modify `mmap_comms.py`.
- Assume the buffer is large enough for the data.
- Use `mm.seek(0)` and `mm.write()` or direct indexing.

## Verification
Run `python3 test_mmap.py`.
