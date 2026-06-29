# Roadmap: Project Mighty Mouse

- [v1.0 Milestone Archive](milestones/v1.0-ROADMAP.md) - Established baseline, autoresearch optimization, multi-task scaling, and native IDE integration.
- [v13 Milestone Archive](milestones/v13-ROADMAP.md) - Deterministic Sandbox Execution.
- [v14 Requirements](milestones/v14-REQUIREMENTS.md) - Perpetual Self-Play: Gemma 4 Reliability Research.

## Milestone 6: Autonomous Agentic Scaling [x]

**Goal**: Expand the capabilities of Gemini 3 Flash by mutating the IDE-native prompt and automatically escalating benchmark difficulty when success is reached.

### Phase 13: IDE-Native Autoresearch Loop [x]
- [x] Task: Adapt the `/autoresearch` workflow to mutate a portable IDE prompt block (e.g., `mighty-antigravity-frozen.md`) instead of external orchestrator scripts. Focus mutations on advanced reasoning strategies (reflection, scratchpads).
- [x] UAT: The autoresearch loop successfully mutates the prompt and tests it against the current benchmark pack natively in the IDE.

### Phase 14: Autonomous Benchmark Escalation [x]
- [x] Task: Implement the "Pass -> Expand" logic within the autoresearch loop. When a prompt clears a benchmark pack perfectly, the loop must write a new, harder benchmark pack (Pack N+1) to test complex agentic abilities.
- [x] UAT: Upon achieving a 100% pass rate, the agent automatically creates a harder benchmark pack with rigorous test scripts and no fake confirmation.

### Phase 15: Extended Optimization Run [x]
- [x] Task: Execute the expanded autoresearch loop, specifically targeting Gemini 3 Flash.
- [x] UAT: The loop produced a FROZEN IDE-native prompt (`mighty-antigravity-native.md`) and 3 tiers of challenging benchmark packs (v1-test, v2-refactor, v3-statemachine).

## Milestone 7: Flashpoint Hardening & Reliability [x]

**Goal**: Stress-test the Flashpoint (XML-optimized) variant to ensure its "frozen" state is truly robust across multiple autonomous re-executions.

### Phase 16: Flashpoint Reliability Stress Test [x]
- [x] Task: Reset benchmark fixtures for Packs 13, 14, and 15 to their initial buggy states. Execute the Flashpoint harness against these packs using the `/autoresearch:flashpoint` workflow.
- [x] UAT: All 3 packs (v13, v14, v15) achieve a 100% pass rate in a single autonomous run without further prompt mutation.

### Phase 17: Full Regression Coverage & Milestone Archiving [x]
- [x] Task: Complete the restoration of all remaining V14 and V15 benchmark fixtures. Run a final, unattended regression pass across the entire Milestone 7 suite (V13-V15).
- [x] UAT: 100% pass rate across the full 15-task suite. Generate the final V7 Milestone Audit and archive.

## Milestone 8: The Unified Harness & Skill Packaging [x]

**Goal**: Consolidate the "Flashpoint" (XML) and "Native" variants into a single, high-performance Unified Harness and package it as a portable Antigravity Skill. **Strictly Native execution; no external APIs.**

### Phase 18: Harness Harmonization [x]
- [x] Task: Merge the rigid XML structural constraints of Flashpoint with the advanced reasoning strategies (reflection, state tracking) of the Native prompt to create the "Unified Mighty Mouse" harness.
- [x] UAT: The Unified harness clears the entire 15-task regression suite (V13-V15) with 100% success using ONLY native IDE subagents.

### Phase 19: Adversarial Drift Stress Test (Tier 16) [x]
- [x] Task: Create the most difficult benchmark pack yet (Tier 16 - Multi-turn state drift) and verify the Unified harness can solve it natively. This tests the "Unified" reasoning under stochastic pressure without any external APIs.
- [x] UAT: 100% success on the Tier 16 pack using strictly native execution.

### Phase 20: Skill Packaging & Distribution [x]
- [x] Task: Formalize Mighty Mouse as a standard `.agents/skills/mighty-mouse/` directory. Create a `SKILL.md` and associated verification artifacts.
- [x] UAT: A clean agent can resolve a V14-level task using the Mighty Mouse skill natively.
## Milestone 9: Post-Mighty Evolution & Scale [x]

**Goal**: Extend the Unified Harness reliability beyond the Milestone 8 baseline by conquering the highest-order adversarial tiers (17-20).

### Phase 21: Adversarial Security & Integrity (Tier 17) [x]
- [x] Task: Expand the suite to Tier 17, focusing on permission escalation, state poisoning, and unsafe deserialization.
- [x] UAT: 100% pass rate on Tier 17 using the Unified Harness.

### Phase 22: Systemic Cascades (Tier 18) [x]
- [x] Task: Expand the suite to Tier 18, focusing on cascading type changes and multi-layer configuration propagation.
- [x] UAT: 100% pass rate on Tier 18.

### Phase 23: Transactional Integrity (Tier 19) [x]
- [x] Task: Expand the suite to Tier 19, focusing on distributed state sync and atomic rollback mechanisms.
- [x] UAT: 100% pass rate on Tier 19.

### Phase 24: The Final Frontier (Tier 20) [x]
- [x] Task: Finalize the suite with Tier 20, focusing on resilient retry-fallback strategies and runtime monkey-patching of protected dependencies.
- [x] UAT: 100% pass rate on Tier 20. 
- [x] Milestone Audit: Complete a full regression pass across Tiers 18-20.
## Milestone 10: Advanced Architectural Reliability (Tiers 21-25) [x]

**Goal**: Push the Unified Harness to the absolute limit by resolving complex architectural patterns, metaprogramming collisions, and runtime security audits.

### Phase 25: Advanced Patterns (Tier 21) [x]
- [x] Task: Expand the suite to Tier 21, focusing on circular dependency resolution and global state context management.
- [x] UAT: 100% pass rate on Tier 21 using the Unified Harness.

### Phase 26: Metaprogramming & Scoping (Tier 22) [x]
- [x] Task: Expand the suite to Tier 22, focusing on dynamic getattr fallbacks and instance-level decorator scoping.
- [x] UAT: 100% pass rate on Tier 22.

### Phase 27: Concurrency & IPC (Tier 23) [x]
- [x] Task: Expand the suite to Tier 23, focusing on safe file locking with retries and synchronized Pipe relays.
- [x] UAT: 100% pass rate on Tier 23.

### Phase 28: Security & Introspection (Tiers 24-25) [x]
- [x] Task: Finalize the research cycle with Tiers 24 and 25, focusing on restricted execution sandboxes, metaclass validation, and bytecode-level purity auditing.
- [x] UAT: 100% pass rate on Tiers 24-25.
- [x] Final Project Audit: Complete a full regression pass across Tiers 21-25 and freeze the repository.

## Milestone 11: Performance & Telemetry Hardening [x]

**Goal**: Promote parallel execution as the primary path, consolidate comprehensive telemetry, and implement schema drift detection.

### Phase 29: Performance & Telemetry Hardening [x]
- [x] Task: Harden `gemini_client.py` telemetry, refactor `solve_benchmark.py` delegation, and implement Schema Drift detection in `ResponseParser`.
- [x] UAT: `python3 eval/solve_benchmark.py --parallel` produces a `benchmark_results.json` with accurate token counts, latency, and explicit schema error logging.

## Milestone 12: Self-Healing & Agentic Autonomy [x]

**Goal**: Implement a "Self-Correction" loop where the agent detects its own errors and automatically iterates without user intervention.

### Phase 30: Self-Healing Implementation [x]
- [x] Task: Implement "Schema-Triggered Retries" in `mighty_mouse_agent.py`. If a `schema_error` is detected, the agent should automatically re-prompt itself with a "Correction Fragment".
- [x] UAT: The agent successfully recovers from an initial malformed response and produces valid code blocks in a secondary autonomous pass.



## Milestone 14: Perpetual Self-Play — Gemma 4 Reliability Research [ ]

**Goal**: Determine how much coding reliability can be extracted from `gemma4:e4b` through autonomous protocol design, prompt mutation, adversarial verification, and test-time compute — without changing the model.

**Thesis**: Can a small local model become meaningfully more reliable when wrapped in the right autonomous research harness?

**Model**: `gemma4:e4b` via Ollama (local only, no API cost). Multi-model switching deferred.

**See**: [v14-REQUIREMENTS.md](milestones/v14-REQUIREMENTS.md) for full spec.

### Phase 32: Perpetual Autonomous Loop [ ]
- [ ] Task: Replace `eval/perpetual_harness.sh` with a Python daemon `eval/perpetual_loop.py`. The daemon reads `logs/metric_telemetry.json` to make results-driven escalation decisions (>=90% pass rate -> escalate tier; <50% -> trigger mutation cycle). Implements adaptive patience circuit breaker (3 consecutive failing mutation cycles -> drop one tier). All loop state persists across process restarts. No dependency on the Gemini CLI.
- [ ] UAT: `python3 eval/perpetual_loop.py` runs for 30 minutes unattended, correctly escalates one tier on >=90% pass, triggers a mutation cycle on sub-50% performance, and writes continuous structured telemetry to `logs/metric_telemetry.json` without crashing or requiring human input.

### Phase 33: Multi-Dimensional Failure Taxonomy & Prompt Mutation Engine [ ]
- [ ] Task: Expand `analyze_failure.py` to the full 7-category taxonomy: SCOPE, ADHERENCE, LOGIC, VERIFICATION, REGRESSION, EFFICIENCY, PARSER. Implement `eval/mutation_engine.py` that reads failure categories, selects the dominant failure mode, generates a targeted minimal mutation to a single `configs/prompt_segments/` file, records the full hypothesis, runs before/after comparison across all metric dimensions, enforces multi-dimensional promotion criteria (all dimensions must hold), includes replay testing against 2 prior tiers as the anti-overfitting gate, and logs each mutation decision to `logs/mutation_log.jsonl`.
- [ ] UAT: Starting from a deliberately degraded prompt config, `mutation_engine.py` correctly identifies the dominant failure category, generates a targeted mutation, runs the full comparison, and produces a complete mutation record in `logs/mutation_log.jsonl` with a PROMOTE/REJECT/HOLD decision and rationale. The promoted candidate must pass the 2-tier replay gate.

### Phase 34: Benchmark Reference Integration & Parity Report [ ]
- [ ] Task: Embed static LiveCodeBench published scores for reference models into `eval/results/frontier_reference.json`. Implement `eval/parity_report.py` that reads the latest `benchmark_results.json`, computes pass rates by tier, and generates `eval/results/frontier_delta.md`.
- [ ] UAT: After one full loop cycle, `frontier_delta.md` is produced with accurate per-tier pass rates and static reference scores.

## Milestone 15 (v15.0): Skill Lifecycle & Multi-Skill Orchestration [ ]

**Goal**: Implement modular reasoning "Skills" that can be auto-injected based on task tags, managed through a formal lifecycle (DRAFT -> CANDIDATE -> ACTIVE), and protected by a robust conflict policy.

### Phases
- [x] Phase 62: S2-STREAM ACTIVE_NARROW Promotion
- [x] Phase 63: Multi-Skill Active Observation
- [x] Phase 64: Harness Stability Diagnosis
- [x] Phase 65: Concurrency Control Implementation
- [x] Phase 66: Reliability Rerun
- [x] Phase 67: Local Runtime Hygiene & Ollama Readiness Gate
- [x] Phase 68: Reduced-Concurrency Multi-Skill Observation Rerun
- [x] Phase 69: Controlled Autoresearch Optimization Loop v1
- [x] Phase 70: Task Metadata Restoration Wave
- [x] Phase 71: Prompt/Delete Contract Hardening
- [x] Phase 72: Controlled Autoresearch Expansion v2
- [x] Phase 73: Delete Protocol Format Precision Patch
- [x] Phase 74: Controlled Autoresearch Proposal Mining v3
- [x] Phase 75: Expected File Coverage Recovery Planning
- [x] Phase 76: Output Coverage Recovery Implementation
- [ ] Phase 77: Production Rollout

### Phase 62: S2-STREAM ACTIVE_NARROW Promotion [x]
- [x] Task: Promote S2-STREAM to ACTIVE status with `narrow` activation mode. Implement the "Fail-Closed" conflict policy in `mighty_mouse_agent.py` to prevent skill stacking.
- [x] UAT: Verified registry update and manual conflict tests.

### Phase 63: Multi-Skill Active Observation [x]
- [x] Task: Observe S1-STATE and S2-STREAM under normal harness behavior using an observation suite of 12 tagged tasks. Validate routing accuracy and conflict rejection.
- [x] UAT: ✅ QUALIFIED. Routing accuracy verified (100% on completed runs). Conflict policy enforcement verified on `obs_task_conflict_01`. **CAVEAT**: 41% timeout rate identified; runtime stability not validated.

### Phase 64: Harness Stability Diagnosis (Sequential Sweep & Isolation Audit) [x]
- [x] Task: Diagnose the root cause of the 300s timeouts observed in Phase 63. Investigate model latency (Ollama), token overhead of multi-skill prompts, and orchestrator bottlenecks.
- [x] UAT: Timeout rate reduced to <10% for baseline observation tasks.

### Phase 65: Concurrency Control Implementation (Patch run_parallel.py) [x]
- [x] Task: Patch `run_parallel.py` to support `MAX_WORKERS` overrides via CLI/ENV. Implement dynamic worker scaling based on provider (Ollama vs Gemini).
- [x] UAT: Multi-skill observation suite passes with `MAX_WORKERS=1` (sequential) on local Ollama without triggering 300s timeout spikes. Telemetry verified in `benchmark_results.json`.

### Phase 67: Local Runtime Hygiene & Ollama Readiness Gate [x]
- [x] Create automated readiness gate (`eval/diagnose_runtime.py`)
- [x] Perform safe process cleanup and provider restart
- [x] Verify system memory and swap health
- [x] Validate model responsiveness (repeated prompts + smoke task)
- [x] Status: **PASS**

### Phase 68: Reduced-Concurrency Multi-Skill Observation Rerun [x]
| Phase | Category | Description | Status | Report |
| :--- | :--- | :--- | :--- | :--- |
| 68 | Reliability | Reduced-concurrency observation rerun | ✅ PASS | [Report](file:///Volumes/YBF_Storage/Projects/mighty_mouse/eval/results/observation/phase_68/PHASE_68_OBSERVATION_REPORT.md) |
- [x] Task: Execute the Phase 63 multi-skill observation suite with controlled, single-worker concurrency (`--max-workers 1`) to validate that the timeout issues are resolved and that the router and conflict policies maintain 100% accuracy.
- [x] UAT: ✅ PASS. 100% routing accuracy across 12 tasks with zero 300s timeout spikes. (Caveat: One non-routing SCOPE failure noted).
- [x] Artifact: [Phase 68 Report](file:///Volumes/YBF_Storage/Projects/mighty_mouse/eval/results/observation/phase_68/PHASE_68_OBSERVATION_REPORT.md)

### Phase 69: Controlled Autoresearch Optimization Loop v1 [ ]
| Phase | Category | Description | Status | Report |
| :--- | :--- | :--- | :--- | :--- |
| 69 | Autoresearch | Controlled Optimization Loop v1 | ✅ COMPLETE | [Proposals](file:///Volumes/YBF_Storage/Projects/mighty_mouse/eval/results/autoresearch/phase_69/PHASE_69_PROPOSALS.md) |
- [x] Task: Execute a one-shot mining pass to identify recurring failure patterns (SCOPE) and metadata gaps. Focus on the "ghost-file" handling logic.
- [x] UAT: ✅ PASS. Identified 407 tasks with missing `deletable_files` metadata. Root cause of Phase 68 SCOPE failure isolated to metadata gaps and prompt ambiguity.

### Phase 70: Task Metadata Restoration Wave [x]
| Phase | Category | Description | Status | Report |
| :--- | :--- | :--- | :--- | :--- |
| 70 | Remediation | Task Metadata Restoration Wave | ✅ COMPLETE | [Report](file:///Volumes/YBF_Storage/Projects/mighty_mouse/eval/results/autoresearch/phase_70/PHASE_70_REMEDIATION_REPORT.md) |
- [x] Task: Bulk remediate 407 tasks with missing `deletable_files` metadata.
- [x] UAT: ✅ PASS (Metadata Authorization). Note: End-to-end task_1010 smoke still failed (SCOPE) because the agent did not use the `delete:path` protocol; this will be addressed in Phase 71.

### Phase 71: Prompt/Delete Contract Hardening [x]
| Phase | Category | Description | Status | Report |
| :--- | :--- | :--- | :--- | :--- |
| 71 | Hardening | Prompt/Delete Contract Hardening | ✅ COMPLETE | [Report](file:///Volumes/YBF_Storage/Projects/mighty_mouse/eval/results/autoresearch/phase_71/PHASE_71_DELETE_CONTRACT_REPORT.md) |
- [x] Task: Patch `mighty_mouse_agent.py` to support `delete:path` protocol and forbid fake deletions via comments.
- [x] UAT: ✅ PASS. Task 1010 successfully emitted `delete:obsolete_shim.py` and cleared SCOPE. Regression suite 100% stable.
187: 
188: ### Phase 72: Controlled Autoresearch Expansion v2 [x]
189: | Phase | Category | Description | Status | Report |
190: | :--- | :--- | :--- | :--- | :--- |
191: | 72 | Autoresearch | Controlled Autoresearch Expansion v2 | ✅ PASS | [Report](file:///Volumes/YBF_Storage/Projects/mighty_mouse/eval/results/autoresearch/phase_72/PHASE_72_EXECUTION_REPORT.md) |
192: - [x] Task: Execute a controlled benchmark/mining pass to identify remaining failure patterns after Phase 70/71 fixes.
193: - [x] UAT: ✅ PASS. Stage A (Stability) and Stage B (Expansion) achieved 100% success rate after Phase 73 patch.
- [x] Decision: `PHASE_72_EXPANSION_QUALIFIED`. Ready for Phase 74 Proposal Mining.

### Phase 73: Delete Protocol Format Precision Patch [x]
| Phase | Category | Description | Status | Report |
| :--- | :--- | :--- | :--- | :--- |
| 73 | Hardening | Delete Protocol Format Precision Patch | ✅ COMPLETE | [Report](file:///Volumes/YBF_Storage/Projects/mighty_mouse/eval/results/autoresearch/phase_73/PHASE_73_DELETE_FORMAT_PRECISION_REPORT.md) |
- [x] Task: Harden FORMAT_REMINDER to eliminate python:delete: hallucinations and enforce internal newlines.
- [x] UAT: ✅ PASS. Targeted smoke tests (1045, 1010) achieved 100% adherence. Conflict policy stable.
- [x] Decision: DELETE_FORMAT_PRECISION_PATCH_COMPLETE. System ready for expansion.

### Phase 74: Controlled Autoresearch Proposal Mining v3 [x]
| Phase | Category | Description | Status | Report |
| :--- | :--- | :--- | :--- | :--- |
| 74 | Autoresearch | Controlled Autoresearch Proposal Mining v3 | ✅ COMPLETE | [Report](file:///Volumes/YBF_Storage/Projects/mighty_mouse/eval/results/autoresearch/phase_74/PHASE_74_EXECUTION_REPORT.md) |
- [x] Task: Execute Stage A (Sentinel) and Stage B (Expansion) to generate autoresearch proposals.
- [x] UAT: ✅ PASS. Total 43 tasks executed with a 42/43 pass rate (97.7%). Single failure confirmed as transient model variance.
- [x] Decision: `PHASE_74_COMPLETE_PROPOSALS_READY`. System ready for Phase 75.

### Phase 75: Expected File Coverage Recovery Planning [x]
| Phase | Category | Description | Status | Report |
| :--- | :--- | :--- | :--- | :--- |
| 75 | Planning | Expected File Coverage Recovery Planning | ✅ COMPLETE | [Plan](file:///Volumes/YBF_Storage/Projects/mighty_mouse/eval/results/autoresearch/phase_75/PHASE_75_EXPECTED_FILE_COVERAGE_PLAN.md) |
- [x] Task: Design an output coverage fix plan to automatically detect and recover omitted expected files via targeted reprompting.
- [x] Constraints: Scoped prototype/planning only. No core run-loop mutation.
- [x] Decision: `READY_FOR_PHASE_76_OUTPUT_COVERAGE_PROTOTYPE`.

### Phase 76: Output Coverage Recovery Implementation [x]
| Phase | Category | Description | Status | Report |
| :--- | :--- | :--- | :--- | :--- |
| 76 | Prototype | Output Coverage Recovery Implementation | ✅ PASS | [Report](file:///Volumes/YBF_Storage/Projects/mighty_mouse/eval/results/autoresearch/phase_76/PHASE_76_OUTPUT_COVERAGE_PROTOTYPE_REPORT.md) |
- [x] Task: Mutate `mighty_mouse_agent.py` to include the `CoverageDetector` and recovery loop.
- [x] Constraints: Must be gated, telemetry-rich, one-retry-max, and validated against `task_1005` plus negative controls. No broad production rollout. No parser changes. No uncontrolled reprompt loop.
- [x] Decision: `PHASE_76_PROTOTYPE_COMPLETE`.

### Phase 77: Prototype Qualification & Integration Hardening [x]
- [x] Task: Qualify the Phase 76 output coverage recovery prototype using staged local Gemma/Ollama benchmark evidence.
- [x] UAT: 30/30 clean passes across Stage A and Stage B; 0 recovered; 0 failed; no timeout/schema/parser/workspace regressions.
- [x] Decision: PHASE_77_CLOSED_READY_FOR_PHASE_78_DECISION.
- [x] Constraint: Phase 76 recovery remains prototype-only until Phase 78 decision. No production rollout occurred.
-
