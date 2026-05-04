# Mighty Mouse Checklist - task_015

## Planning (Antigravity Reliability Audit)

**Goal:** Implement a robust, asynchronous Circuit Breaker pattern in `async_service.py` to prevent cascading failures when calling external services.

**1. Precision Extraction (Needle-in-the-Haystack):**
The core requirement is the state machine logic for the Circuit Breaker (Closed $\rightarrow$ Open $\rightarrow$ Half-Open). This must be implemented using `asyncio` primitives to ensure thread safety and non-blocking behavior, which is critical for mission-critical asynchronous services.

**2. Constraint Mapping:**
*   **Mandatory:** Use `async`/`await`.
*   **Mandatory:** Implement state tracking (e.g., `state`, `failure_count`, `last_failure_time`).
*   **Constraint:** Defensive coding is paramount. All state transitions must be protected by locks.
*   **Target File:** `async_service.py`.

**3. Integrity Check & Safety-First Resolution:**
*   **Potential Failure 1: Race Conditions:** Multiple concurrent tasks might attempt to check the state and transition it simultaneously.
    *   *Mitigation:* Use `asyncio.Lock` around all state-modifying operations (state checks, failure increments, state transitions).
*   **Potential Failure 2: Time Drift/Edge Cases:** The transition from Open to Half-Open must be time-gated (e.g., wait for a timeout period).
    *   *Mitigation:* Use `time.monotonic()` or `asyncio.get_event_loop().time()` to accurately track the time since the last failure, ensuring the wait period is respected.
*   **Potential Failure 3: Exception Handling:** The wrapper must distinguish between transient service failures (which count towards the threshold) and non-service-related exceptions (which should not trip the breaker).
    *   *Mitigation:* Implement a `try...except` block that specifically catches expected service exceptions and handles general exceptions separately.

**4. System Data Flow:**
*   **Input:** An asynchronous callable function (`func`) and its arguments (`*args`, `**kwargs`).
*   **Process:** The `CircuitBreaker` wrapper intercepts the call, checks the state, executes the call (if allowed), updates the state based on success/failure, and manages timeouts.
*   **Output:** The result of the wrapped function, or a specific `CircuitBreakerOpenError`.

## Activity

I will first define custom exceptions and the `CircuitBreaker` class in `async_service.py`. This class will manage the state machine logic, ensuring atomic state transitions using `asyncio.Lock`.
