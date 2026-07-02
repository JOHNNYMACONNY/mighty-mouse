# Real-Project Validation

Status: **collecting**

Every row is a paired control and harness run from the same recorded project commit, agent, model, and environment. Unfavorable results are retained.

Current paired tasks: **9/10 minimum**.

| Metric | Control | Mighty Mouse |
|---|---:|---:|
| First-try passes | 6/9 | 6/9 |
| Total retries | 3 | 3 |
| Scope violations | 0 | 0 |
| Mean duration (seconds) | 250.9 | 287.3 |
| Mean quality (1–5) | 4.22 | 4.67 |

## Per-task results

| Task | Control first pass | Harness first pass | Retries C/H | Scope C/H | Seconds C/H | Quality C/H |
|---|---:|---:|---:|---:|---:|---:|
| AUDIO-001 | no | no | 1/1 | 0/0 | 428.6/459.7 | 4/5 |
| MM-001 | yes | yes | 0/0 | 0/0 | 139.0/200.1 | 4/5 |
| MM-002 | yes | yes | 0/0 | 0/0 | 225.5/191.6 | 4/5 |
| MM-003 | yes | yes | 0/0 | 0/0 | 154.5/167.7 | 5/4 |
| MM-004 | yes | yes | 0/0 | 0/0 | 160.3/242.4 | 4/4 |
| PORT-001 | yes | yes | 0/0 | 0/0 | 130.9/256.5 | 4/5 |
| PORT-002 | yes | yes | 0/0 | 0/0 | 233.6/268.5 | 4/5 |
| PORT-003 | no | no | 1/1 | 0/0 | 310.1/345.3 | 4/5 |
| SOCIAL-001 | no | no | 1/1 | 0/0 | 475.5/454.0 | 5/4 |

The minimum sample has not been reached; no generalized improvement claim is made.
