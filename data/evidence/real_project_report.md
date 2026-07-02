# Real-Project Validation

Status: **complete**

Every row is a paired control and harness run from the same recorded project commit, agent, model, and environment. Unfavorable results are retained.

Current paired tasks: **10/10 minimum**.

| Metric | Control | Mighty Mouse |
|---|---:|---:|
| First-try passes | 6/10 | 6/10 |
| Total retries | 6 | 4 |
| Scope violations | 0 | 0 |
| Mean duration (seconds) | 5596.4 | 5628.6 |
| Median duration (seconds) | 229.5 | 262.5 |
| Mean quality (1–5) | 4.30 | 4.60 |

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
| VIDEO-001 | no | no | 3/1 | 0/0 | 53706.5/53700.5 | 5/4 |

## Conclusion

**No generalized improvement was demonstrated.** First-try pass rate was tied, and Mighty Mouse was slower on both raw mean and median duration. The harness used fewer retries and received higher mean blind-review quality, so the result is mixed rather than evidence of a universal gain.

- Blind-review quality favored Mighty Mouse on 6 tasks, control on 3, with 1 tie(s).
- Mighty Mouse completed faster on 3/10 paired tasks.
- Retry totals were 6 control versus 4 Mighty Mouse.
- Duration outlier(s) beyond the frozen per-condition timeout: VIDEO-001. Raw mean duration retains these wall-clock values; median duration is shown so the outlier cannot silently dominate interpretation.
