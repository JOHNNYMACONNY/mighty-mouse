# Milestone 14 Requirements: Perpetual Self-Play — Gemma 4 Reliability Research

## Milestone Thesis

> Can a small local model (`gemma4:e4b`) become meaningfully more reliable when wrapped in the right autonomous research harness?

Reliability here means not just passing tests, but doing so with correct scope, honest verification, no regressions, minimal retries, and parseable output. The harness — not the model — is the research subject.

## Scope Constraints

- **Primary model**: `gemma4:e4b` via Ollama (local, zero API cost)
- **No model switching in this milestone** — multi-model support is deferred to a future milestone
- **No external API calls for evaluation** — LiveCodeBench used as static reference ceiling only
- **Portability-ready outputs** — winning prompt configs, telemetry schemas, and benchmark artifacts must be clean enough to export to another runtime later

## Research Axes

Measure how much reliability improvement can be extracted from `gemma4:e4b` through:

1. **Protocol design** — harness structure, XML constraints, phase gates, self-correction
2. **Prompt mutation** — targeted, hypothesis-driven, reversible, segment-level changes
3. **Adversarial verification** — multi-dimensional failure detection beyond pass/fail
4. **Test-time compute** — multi-variation sampling before committing output
5. **Continuous telemetry** — persistent, structured, multi-dimensional tracking across the full loop

---

## Requirement 1: Perpetual Autonomous Loop

The loop must run unattended for hours or days without human intervention.

- Tier escalation is **results-driven**: ≥90% pass rate on current tier → escalate; <50% → trigger mutation cycle
- Circuit breaker: if 3+ consecutive mutation cycles produce no measurable improvement → drop one tier and re-ground before escalating again
- All loop state persists across restarts — no progress lost if the process is killed
- Implemented as a **Python daemon** (`eval/perpetual_loop.py`), not a shell script calling the Gemini CLI
- The daemon reads `logs/metric_telemetry.json` to make all escalation/mutation decisions
- A human can review logs and interrupt at any time, but the loop never blocks waiting for human input

---

## Requirement 2: Multi-Dimensional Reliability Metrics

The loop must optimize for **real reliability**, not just higher pass rate. All dimensions must be tracked. Never improve one at the expense of another.

### Primary Metrics

| Metric | Description |
|---|---|
| Task pass rate | Per-tier and cumulative |
| Tier reached | Highest tier cleared at ≥90% |
| First-pass success rate | Tasks passed on first attempt |
| Retry count | Average retries per task |
| Runtime per successful task | Latency efficiency |

### Failure Taxonomy (7 Categories)

| Category | Definition |
|---|---|
| `SCOPE` | Wrong files created, extra files written, expected files missing |
| `ADHERENCE` | Violated explicit constraint (no-imports, line limits, immutable signatures) |
| `LOGIC` | Tests failed, incorrect or incomplete implementation |
| `VERIFICATION` | Claimed success without sufficient evidence; fake pass |
| `REGRESSION` | Fixed target issue but broke existing behavior |
| `EFFICIENCY` | Success required excessive retries, tool use, or context bloat |
| `PARSER` | Output could not be safely parsed or applied by the harness |

### Secondary Metrics

- Unnecessary file edits (modifying files not in `expected_files`)
- False success rate (verification_claimed=true but sandbox test fails)
- Schema error rate (malformed XML/markdown blocks)

All metrics written to `logs/metric_telemetry.json` (append-mode) after every run.

---

## Requirement 3: Prompt Mutation Protocol

Each mutation must be:

- **Targeted** — addresses a specific failure category from the taxonomy
- **Minimal** — changes the smallest possible surface in a single `prompt_segments/` file
- **Reversible** — old segment preserved; new segment is a candidate only until promoted
- **Hypothesis-driven** — records the specific bet being made before running

### Mutation Record Schema

Each mutation written to `logs/mutation_log.jsonl`:

```json
{
  "timestamp": "...",
  "failure_category": "SCOPE",
  "segment_changed": "constraints.txt",
  "hypothesis": "Adding explicit anti-ghost-file wording will reduce file-creation scope drift",
  "before": { "pass_rate": 0.72, "scope_violations": 4, "verification_failures": 1 },
  "after":  { "pass_rate": 0.79, "scope_violations": 1, "verification_failures": 1 },
  "replay_tiers_tested": ["tier_3", "tier_5"],
  "decision": "PROMOTE"
}
```

### Promotion Criteria — ALL must be satisfied

A candidate prompt mutation is only promoted to the frozen config when:

1. Pass rate improves OR holds steady (does not decrease)
2. SCOPE violations do not increase
3. VERIFICATION failures do not increase
4. REGRESSION failures do not increase
5. Retry count does not increase materially (>10% increase = regression)
6. Passes replay test against at least 2 prior tiers (anti-overfitting gate)

If any criterion fails → REJECT and log the failure reason. The previous frozen segment is restored.

---

## Requirement 4: Benchmark Reference Integration

- **Source of truth**: Mighty Mouse's own tiered benchmark suite (constraint-following, no-regression edits, verification honesty, recovery, protocol adherence)
- **Reference ceiling**: Published LiveCodeBench scores embedded as static data — not recalculated, not used for promotion decisions
- `eval/results/frontier_delta.md` generated at the end of each major loop cycle showing:
  - Local model pass rate by tier (live, from our benchmark)
  - Published LiveCodeBench scores for reference models (static, clearly labeled)
  - "Parity score": local model performance as a percentage of the closest published reference
  - Trend line: parity score across previous runs to show gap closure

The report framing must make clear that the Mighty Mouse benchmark suite is the measurement instrument, and LiveCodeBench is a calibration reference only.

---

## Requirement 5: Portability-Ready Artifacts

At milestone close, the following must be clean, versioned, and exportable:

| Artifact | Location | Purpose |
|---|---|---|
| Winning prompt config | `configs/prompt_segments/` + YAML | Primary research output |
| Telemetry schema | `logs/metric_telemetry.json` | Replay and analysis |
| Mutation log | `logs/mutation_log.jsonl` | Full research audit trail |
| Benchmark suite | `tasks/benchmark/` + reset scripts | Portable eval suite |
| Parity report | `eval/results/frontier_delta.md` | Exportable reference comparison |

These artifacts must be self-contained enough to be dropped into a different runtime or orchestrator and produce a meaningful baseline evaluation without modification.

---

## Out of Scope (This Milestone)

- Multi-model switching or model registry
- External API evaluation (Claude, GPT, Gemini)
- Runtime adapter or callable specialist integration
- IDE or slash-command distribution
- Evaluation against SWE-bench or other repo-scale benchmarks

---

## Constraints

- `gemma4:e4b` is the only model used — no substitutions
- No external API calls during the loop
- Verification remains deterministic (test scripts via sandbox, not model self-assessment)
- Sandbox isolation from Phase 31 must remain active throughout
- Simulation mode must remain disabled for all benchmark claims
