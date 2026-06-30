# Real-Project Validation

Status: **collecting**

Every row is a paired control and harness run from the same recorded project commit, agent, model, and environment. Unfavorable results are retained.

Current paired tasks: **4/10 minimum**.

| Metric | Control | Mighty Mouse |
|---|---:|---:|
| First-try passes | 4/4 | 4/4 |
| Total retries | 0 | 0 |
| Scope violations | 0 | 0 |
| Mean duration (seconds) | 169.8 | 200.4 |
| Mean quality (1–5) | 4.25 | 4.50 |

## Per-task results

| Task | Control first pass | Harness first pass | Retries C/H | Scope C/H | Seconds C/H | Quality C/H |
|---|---:|---:|---:|---:|---:|---:|
| MM-001 | yes | yes | 0/0 | 0/0 | 139.0/200.1 | 4/5 |
| MM-002 | yes | yes | 0/0 | 0/0 | 225.5/191.6 | 4/5 |
| MM-003 | yes | yes | 0/0 | 0/0 | 154.5/167.7 | 5/4 |
| MM-004 | yes | yes | 0/0 | 0/0 | 160.3/242.4 | 4/4 |

The minimum sample has not been reached; no generalized improvement claim is made.
