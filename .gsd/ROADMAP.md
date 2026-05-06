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
- [ ] Task: Embed static LiveCodeBench published scores for reference models into `eval/results/frontier_reference.json`. Implement `eval/parity_report.py` that reads the latest `benchmark_results.json`, computes pass rates by tier, and generates `eval/results/frontier_delta.md` showing: (1) local model pass rate by tier as the primary metric, (2) static LiveCodeBench reference scores clearly labeled as ceiling data only, (3) a parity score expressing local model performance as a percentage of the closest reference, and (4) a trend line across prior runs. Report generated automatically at end of each perpetual loop cycle.
- [ ] UAT: After one full loop cycle, `frontier_delta.md` is produced with accurate per-tier pass rates, static reference scores, a computed parity score, and correct framing (Mighty Mouse benchmark = source of truth; LiveCodeBench = calibration reference). The report is readable and self-contained without requiring the loop to be running.
