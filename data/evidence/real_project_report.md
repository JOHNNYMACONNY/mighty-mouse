# Real-Project Validation

Status: **collecting**

Every row is a paired control and harness run from the same recorded project commit, agent, model, and environment. Unfavorable results are retained.

Current paired tasks: **7/10 minimum**.

| Metric | Control | Mighty Mouse |
|---|---:|---:|
| First-try passes | 6/7 | 6/7 |
| Total retries | 1 | 1 |
| Scope violations | 0 | 0 |
| Mean duration (seconds) | 193.4 | 238.9 |
| Mean quality (1–5) | 4.14 | 4.71 |

## Per-task results

| Task | Control first pass | Harness first pass | Retries C/H | Scope C/H | Seconds C/H | Quality C/H |
|---|---:|---:|---:|---:|---:|---:|
| MM-001 | yes | yes | 0/0 | 0/0 | 139.0/200.1 | 4/5 |
| MM-002 | yes | yes | 0/0 | 0/0 | 225.5/191.6 | 4/5 |
| MM-003 | yes | yes | 0/0 | 0/0 | 154.5/167.7 | 5/4 |
| MM-004 | yes | yes | 0/0 | 0/0 | 160.3/242.4 | 4/4 |
| PORT-001 | yes | yes | 0/0 | 0/0 | 130.9/256.5 | 4/5 |
| PORT-002 | yes | yes | 0/0 | 0/0 | 233.6/268.5 | 4/5 |
| PORT-003 | no | no | 1/1 | 0/0 | 310.1/345.3 | 4/5 |

The minimum sample has not been reached; no generalized improvement claim is made.
