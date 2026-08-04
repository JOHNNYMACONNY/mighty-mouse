"""Shared single-instance lock for all Autoresearch Harness adapters."""

from __future__ import annotations

import fcntl
import logging
import os
from pathlib import Path
import signal
import subprocess
import time

logger = logging.getLogger(__name__)
LOCK_FILE_PATH = Path("logs/eval_runner.lock")


class SingleInstanceLockError(RuntimeError):
    """Raised when another evaluation runner owns the Harness lock."""


def _lock_is_held(lock_path: Path) -> bool:
    if not lock_path.exists():
        return False
    with lock_path.open("a+", encoding="utf-8") as file:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(file, fcntl.LOCK_UN)
    return False


def terminate_stale_runners(lock_path: Path = LOCK_FILE_PATH) -> None:
    """Inspect and terminate stale runner processes before acquiring the lock."""
    current_pid = os.getpid()
    parent_pid = os.getppid()
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SingleInstanceLockError("Runner process inspection failed") from exc
    if result.returncode != 0:
        raise SingleInstanceLockError(
            f"Runner process inspection returned {result.returncode}"
        )
    lock_held = _lock_is_held(lock_path)
    lock_owner = None
    if lock_path.exists():
        try:
            lock_owner = int(lock_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            lock_owner = None
    for line in result.stdout.splitlines():
        if not any(
            name in line
            for name in ("perpetual_loop.py", "solve_benchmark.py", "autoresearch_harness.py")
        ):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        if pid in {current_pid, parent_pid} or "pytest" in line or "test_" in line:
            continue
        if lock_held and pid == lock_owner:
            logger.info("Preserving active evaluation runner PID %s", pid)
            continue
        try:
            logger.warning("Terminating stale evaluation runner PID %s", pid)
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.3)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            os.kill(pid, signal.SIGKILL)
        except (OSError, ProcessLookupError) as exc:
            logger.warning("Could not terminate stale runner PID %s: %s", pid, exc)


class SingleInstanceLock:
    """Process-held advisory lock shared by every Harness entry point."""

    def __init__(self, lock_path: Path = LOCK_FILE_PATH):
        self.lock_path = Path(lock_path)
        self._fp = None

    def __enter__(self):
        terminate_stale_runners(self.lock_path)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fp.seek(0)
            self._fp.truncate()
            self._fp.write(str(os.getpid()))
            self._fp.flush()
        except OSError as exc:
            self._fp.close()
            self._fp = None
            raise SingleInstanceLockError(f"Another evaluation runner owns {self.lock_path}") from exc
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._fp is None:
            return
        try:
            fcntl.flock(self._fp, fcntl.LOCK_UN)
            self._fp.close()
            if self.lock_path.exists():
                self.lock_path.unlink()
        except OSError as exc:
            logger.warning("Error releasing %s: %s", self.lock_path, exc)
        finally:
            self._fp = None
