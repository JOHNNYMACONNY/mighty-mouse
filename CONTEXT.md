# Mighty Mouse

Mighty Mouse is a local-first reliability harness for AI coding agents. Its improvement domain separates a user's intended way of working from the versioned rules that govern execution.

## Improvement domain

**Mode**:
The user-facing execution choice: Coding, Agentic, or the fixed Hybrid flow.
_Avoid_: Profile, workflow type

**Policy**:
A versioned internal rule set that governs execution within a Mode; it is an advanced/recovery concept, not a peer user-facing choice.
_Avoid_: Mode, preset

**Policy Mutation Surface**:
The declarative, controller-enforced boundary defining which elements of a Policy a Candidate is permitted to modify, prohibiting any change to controller logic, evaluators, sandboxes, or corpora.
_Avoid_: Prompt surface, tweakable settings

**Candidate**:
An immutable proposed Policy version awaiting or undergoing evaluation for a defined Mode and scope.
_Avoid_: Draft, experiment

**Eligible Successor**:
A verified Candidate that may replace the active Champion automatically when no Pin applies and its evidence, Model Identity, and post-promotion gates remain current.
_Avoid_: Pending promotion, queued Champion

**Champion**:
The Candidate currently promoted as the active default for a defined Mode and evaluation scope.
_Avoid_: Default policy, best policy

**Restriction**:
An auditable safety state that makes a Champion ineligible for selection or reactivation after a verified guard, provenance, integrity, or security failure. It preserves history and triggers Rollback where possible.
_Avoid_: Deletion, ordinary quality regression

**Generation**:
An immutable improvement-cycle record linking one base Champion, its input Signals, Experiment settings, and the Candidates it produced.
_Avoid_: Version number, runtime session

**Protocol Manifest**:
An immutable, content-addressed declaration of one Generation's frozen inputs, including its compatible base Champion, Model Identity, Execution Profile, Signal aggregate, protocol version, budgets, seeds, task ordering, and allowed Policy mutation surface.
_Avoid_: Mutable runtime settings, Candidate payload

**Model Identity**:
An exact, immutable declaration of the target model—including provider, version digest, artifact digest, and capability vector—required to match for Policy compatibility, Candidate generation, and Promotion.
_Avoid_: Model name, LLM string, generic model class

**Execution Profile**:
The host environment execution constraints—including available tools, OS capabilities, compute bounds, and sandbox parameters—under which a Policy or Experiment runs.
_Avoid_: System environment, host settings

**Signal**:
A content-free, structured observation from routine use, such as outcome, duration, retry count, verifier category, or environment metadata. It never contains source code, prompts, transcripts, or secrets.
_Avoid_: Transcript, telemetry payload

**Background Research**:
An explicitly user-started, resource-bounded local or cloud-backed activity that turns accumulated Signals into evaluated Policy Candidates. It remains stopped after a user stop until the user starts it again, including across idle periods and reboots.
_Avoid_: Always-on optimization, idle daemon

**Task Category**:
An optional, coarse, controlled-vocabulary classification of a task used to segment Signals, policy evaluation, and live policy selection. It is either user-supplied or automatically inferred; an insufficiently confident inference falls back to `unknown`. It never contains free text, paths, source code, prompts, or task outputs.
_Avoid_: Task description, prompt summary

**Evidence Bundle**:
A local, experiment-specific provenance record that may retain the richer diagnostic material needed to reproduce a deliberate evaluation; it is separate from routine Signals.
_Avoid_: Signal, analytics event

**Fresh Holdout**:
A private, frozen, quarantined corpus used once for an independently paired claim gate. Its manifest, task digests, protocol, consumption, and terminal result bind durably to one nominated Holdout Contender and Experiment.
_Avoid_: Development Suite, reusable benchmark

**Claim Receipt**:
An immutable, expiring, evidence-bound authorization for narrowly scoped public wording. A receipt becomes stale or blocked when its inputs, identity, restrictions, freshness, or integrity no longer verify.
_Avoid_: Marketing approval, timeless result

**Quarantine**:
The non-authoritative boundary for private holdouts and imported Improvement Bundle data. Quarantined material cannot tune, promote, or activate a Policy; imported material must pass local evaluation.
_Avoid_: Trusted import, deployment channel

**Improvement Bundle**:
An explicit, signed, JCS-canonical export file containing Policy Candidates, metadata, schema versions, and optional Evidence references, which imports into non-executable Quarantine for local evaluation.
_Avoid_: Export package, shared policy zip

**Experiment**:
A frozen evaluation that compares one or more Candidates against a baseline under a defined protocol. Its terminal outcome is completed, invalid, or failed.
_Avoid_: Candidate, generation

**Experiment Ledger**:
An append-only, content-addressed record of all completed, invalid, or failed Experiment runs, including typed condition outcomes, Evidence Bundle hashes, gate results, and either no_change or a single Holdout Contender nomination.
_Avoid_: Evaluation history, test log

**Development Suite**:
A versioned, local, access-controlled corpus with executable acceptance and adversarial checks, frozen by digest in a Protocol Manifest to compare a Candidate with its base Champion. It is reproducible evaluation input, never a source of fresh-holdout evidence.
_Avoid_: Holdout, live-user corpus

**Paired Development Experiment**:
An Experiment that independently compares every Candidate in one Generation with the same base Champion on the frozen Development Suite under matched, precommitted conditions. Ordinary task failures are scored evidence; Candidate errors make that Candidate ineligible, while baseline errors, failed integrity gates, contamination, or safety failures invalidate the Experiment. It may record no change or nominate one Holdout Contender.
_Avoid_: Candidate tournament, holdout evaluation

**Holdout Contender**:
The sole Candidate, if any, nominated by a valid Paired Development Experiment for independent fresh-holdout evaluation. It is not an Eligible Successor or Champion.
_Avoid_: Winner, promoted Candidate

**Promotion**:
An auditable, machine-gated state change that makes a Candidate the Champion. A failed post-promotion guard triggers automatic rollback.
_Avoid_: Deployment, adoption

**Pin**:
An explicit user override that locks a particular Champion for a Mode and scope, preventing automatic replacement until removed.
_Avoid_: Preference, permanent default

**Preview**:
A bounded trial of a selected Candidate or prior Champion that does not change Champion status, Promotion state, or Pins.
_Avoid_: Promotion, mode switch

**Rollback**:
An auditable reversal of a Promotion to the immediately preceding eligible Champion, triggered automatically by a guard failure or manually by the user.
_Avoid_: Reset, deletion

**Scope**:
The explicit applicability boundary for a Champion, Pin, or Preview, including at least Mode, project or repository, and task or model class.
_Avoid_: Global default, implicit context

**Routing Decision**:
An immutable record of the inferred or user-selected Mode for one Scope, including its confidence, reason, Model Identity, and Execution Profile. It explains a completed run; it does not itself choose a Policy.
_Avoid_: Current Mode preference, Policy selection

**Migration**:
An explicit, dry-run-first import that creates independent v2 copies from eligible v1 configuration or state. It never mutates v1 files, changes legacy command behavior, or reinterprets historical v1 Evidence.
_Avoid_: In-place upgrade, automatic conversion

**Host Integration**:
A thin, host-specific adapter (CLI, MCP client, skill, rules, or plugin) that invokes the local Mighty Mouse core and renders its state. It may contribute to the recorded Execution Profile, but it does not own Candidates, Champions, Pins, Evidence Bundles, or Rollbacks.
_Avoid_: Separate improvement system, portable behavior guarantee

**Integration Surface**:
The compact host-facing controls and notices: current status, Background Research start/stop, Pin, Preview, Rollback, and Promotion notification. Detailed Evidence Bundles, full history, and advanced recovery remain in the standalone CLI and future TUI.
_Avoid_: Full per-host settings console, a separate history

**Effective Policy**:
The Policy that Mighty Mouse will use for the current task after evaluating the current Mode, Scope, Model Identity, and Execution Profile. The user sees it in plain language as a project improvement, shared improvement, or safe starting settings, with a short reason and a path to the underlying record.
_Avoid_: Hidden active configuration, unexplained default

**Policy Engine**:
A deep module with a compact public interface (`select_policy`, `record_signal`, `promote_candidate`, `get_status`, `pin`, `preview`, `rollback`) that encapsulates state persistence, policy resolution, restriction enforcement, user control actions, and promotion gates.
_Avoid_: Raw state store, state manager, policy router

Policy selection ownership: `PolicyEngine.select_policy` owns canonical selection semantics and uses private store record queries only for persistence. `ImmutableStateStore.select_policy` remains temporary compatibility adapter. `PolicyLifecycle` and `resolve_effective_policy` retain legacy pass-rate and degradation semantics and remain unsafe to contract until separately migrated without output drift.

Status projection ownership: `mighty_mouse.v2.status.build_status_document` serves as canonical status projection seam. `PolicyEngine.get_status` and `status_document` remain compatibility adapters; CLI and HostAdapter render or forward the canonical document, while MCP currently exposes no status tool.

**Policy Mutation Engine**:
A deep module with a minimal public interface (`mutate_candidate`) that applies versioned policy mutations to a Candidate governed strictly by the Policy Mutation Surface.
_Avoid_: Scatter-gather prompt tweak scripts, unstructured prompt edits

Mutation ownership: `eval.policy_mutation_engine.PolicyMutationEngine` owns canonical typed Candidate mutation and mutation generation. `eval.mutation_cycle.MutationCycleCoordinator` owns the bounded legacy mutation transaction: typed/legacy analysis selection, timeout and generation handling, Policy Mutation Surface authorization, segment reads/writes, current/replay thresholds, restoration, decision mapping, and mutation-log invocation. `eval.mutation_engine.MutationEngine` remains a compatibility/default-resolution adapter with public signatures and direct imports preserved. `AutoresearchCycle` and higher loops retain benchmark, verification, telemetry, runner-lock, and repetition ownership; direct legacy calls may omit a Policy Mutation Surface until that compatibility contract is separately migrated.

Signal telemetry ownership: `mighty_mouse.v2.telemetry.SignalTelemetry` owns lifecycle-backed Signal construction, emission, and aggregate queries. `SignalAggregator` and `TelemetryAggregator` remain compatibility facades; `_LegacyStoreSignalTelemetry` remains an internal raw-`ImmutableStateStore` fallback for legacy callers and tests. `SignalLifecycle.collect` remains the already-constructed Signal persistence adapter. `eval/perpetual_loop.py` legacy `metric_telemetry.json` remains a separate evaluator metric format and stays outside v2 Signal migration.

Autoresearch cycle ownership: `eval.autoresearch_cycle.AutoresearchCycle` owns one bounded benchmark, verification, telemetry, Signal, threshold, mutation, state-save, and parity-report cycle. `AutoresearchLoop.build_cycle` and `run_single_cycle` remain compatibility adapters; `run_forever` and `autoresearch_harness` own repetition and entry-point lock scope. Policy selection and status projection remain external canonical seams because existing cycle behavior does not call either directly. Benchmark subprocesses, the no-adapter benchmark-summary verifier fallback, fixed legacy loop Signal metadata/scope, legacy `execute_mutation_cycle`, metric telemetry, parity subprocess, and runner lock remain intentionally outside contraction. Loop callers pass an explicit Policy Mutation Surface; direct legacy mutation calls may omit one until their compatibility contract is separately migrated.

**Autoresearch Harness**:
The autonomous evaluation driver enforcing single-instance process locking and managing the Fail -> Mutate, Pass -> Expand candidate iteration loop.
_Avoid_: Uncoordinated background loops, unverified background runners

**Verifier Seam**:
The external execution boundary through which all candidates and policies undergo empirical, deterministic testing.
_Avoid_: Internal state inspections, unverified mock assertions

**Output Coverage Recovery**:
A bounded agent retry path that detects missing task-declared expected files after response parsing, requests only missing file blocks, and records whether recovery succeeds or remains disallowed.
_Avoid_: Schema retry, parser success, unrestricted rewrite
