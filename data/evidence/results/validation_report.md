# Validation Report: Lean Protocol Candidate

**Generated**: 2026-05-07 10:23:25

## Recommendation: PROMOTE

| Metric | Baseline v1 | Lean Protocol | Delta |
|---|---|---|---|
| **Pass Rate** | 100.0% (15/15) | 100.0% (15/15) | - |
| **Avg Time (Success)** | 106.1s | 74.78s | 29.5% |
| **TIMEOUT Count** | 0 | 0 | - |
| **LOGIC Fails** | 0 | 0 | - |
| **Other Fails** | 0 | 0 | - |
| **Replay Gate (Tier 1)** | PASS | PASS | - |
| **Hard Tasks (Horizon)** | 2/2 | 2/2 | - |

## Success Criteria Verification
- [x] Lean pass rate >= Baseline: YES
- [x] Lean latency reduction >= 20%: YES
- [x] Tier 1 Replay Gate: PASS
- [x] No regression in Parser/Scope/Verification: PASS

## Raw Task Comparison
| Task ID | Baseline | Lean | Time Diff |
|---|---|---|---|
| task_001_legacy_registry_ratelimiter | success (114.88s) | success (87.33s) | 24.0% |
| task_002_stream_cache_validator | success (134.96s) | success (64.5s) | 52.2% |
| task_003_legacy_link_circuitbreaker | success (120.1s) | success (102.63s) | 14.5% |
| task_004_network_link_validator | success (105.24s) | success (56.81s) | 46.0% |
| task_005_network_iterator_retry | success (107.0s) | success (147.25s) | -37.6% |
| task_006_stream_composite_enricher | success (107.66s) | success (53.43s) | 50.4% |
| task_007_cloud_queue_enricher | success (90.72s) | success (56.01s) | 38.3% |
| task_008_database_link_enricher | success (84.22s) | success (53.4s) | 36.6% |
| task_009_legacy_decorator_filter | success (74.93s) | success (37.73s) | 49.6% |
| task_010_async_composite_enricher | success (99.66s) | success (68.05s) | 31.7% |
| task_011_realtime_decorator_ratelimiter | success (118.74s) | success (55.8s) | 53.0% |
| task_012_network_facade_retry | success (110.49s) | success (95.04s) | 14.0% |
| task_013_network_node_retry | success (106.46s) | success (95.15s) | 10.6% |
| task_014_legacy_store_retry | success (90.16s) | success (58.76s) | 34.8% |
| task_015_async_service_circuitbreaker | success (126.21s) | success (89.77s) | 28.9% |

---
*Note: Successful tasks only for latency deltas. Hard Reasoning Horizon tasks are task_011 and task_015.*
