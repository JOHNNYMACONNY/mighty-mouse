# Promotion Notes: Lean Protocol (Phase 36)

**Date**: 2026-05-07
**Status**: PROMOTED to Production (v2.0.0)

## Summary
The Lean Protocol has been promoted as the primary production configuration for the Mighty Mouse research harness. This decision is based on the Phase 36 Validation Pass results, which demonstrated significant efficiency gains without any loss of reliability.

## Validation Results (Phase 36)
- **Trials**: 30 (15 Baseline, 15 Lean)
- **Pass Rate**: 100.0% (Lean) vs 100.0% (Baseline)
- **Latency Reduction**: **29.5% average speedup** on successful tasks.
- **Replay Gate**: 100% success on Tier 1 (5/5).
- **Reasoning Horizon**: 
    - Passed both Hard tasks (`task_011`, `task_015`).
    - Speedup on `task_011`: **53.0%**.
- **Safety Audit**: PASS. Deferred reasoning strategy preserves mandatory formats and scope discipline.

## Traceability
- **Historical Baseline**: `configs/mighty_mouse_v1_baseline_pre_lean.yaml`
- **Promoted Config**: `configs/mighty_mouse_v2_lean.yaml`
- **Validation Report**: `eval/results/validation_report.md`

## Deferred Tasks
- **Decomposition-First**: Remains deferred to Phase 37. Identified "Implementation Invalid / Parser Contract Failure" during Phase 35 spike. Requires output schema standardization before re-evaluation.

## Post-Promotion Status
- **Perpetual Loop**: ACTIVE. Restarted with `configs/mighty_mouse_v2_lean.yaml`.
- **Smoke Cycle**: **PASSED**. Confirmed 100% success on Tier 1 (5/5). System has successfully escalated to `tier_overnight`.
- **Telemetry**: Verified. Metrics correctly capturing `v2_lean` performance deltas.

## Efficiency Watchlist
- **task_005_network_iterator_retry**: Observed a -37.6% latency regression under Lean (107s vs 147s). While not a blocker, this task should be monitored in future cycles to determine if it represents a systematic reasoning-loop edge case for the compressed protocol.
