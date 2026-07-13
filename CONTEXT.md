# Mighty Mouse

Mighty Mouse is a local-first reliability harness for AI coding agents. Its improvement domain separates a user's intended way of working from the versioned rules that govern execution.

## Improvement domain

**Mode**:
The user-facing execution choice: Coding, Agentic, or the fixed Hybrid flow.
_Avoid_: Profile, workflow type

**Policy**:
A versioned internal rule set that governs execution within a Mode; it is an advanced/recovery concept, not a peer user-facing choice.
_Avoid_: Mode, preset

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

**Experiment**:
A frozen evaluation that compares one or more Candidates against a baseline under a defined protocol. Its terminal outcome is completed, invalid, or failed.
_Avoid_: Candidate, generation

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
