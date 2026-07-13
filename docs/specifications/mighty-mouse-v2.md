# Mighty Mouse v2 — Implementation Specification and Experiment Roadmap

## Status and purpose

This is the implementation handoff for Mighty Mouse v2. It turns the resolved
Wayfinder decisions into one build order and a set of release gates. It does
not authorize implementation by itself; implementation begins in a separate
delivery effort.

**Outcome:** a local-first reliability harness that can learn bounded,
verifiable improvements to its own declarative execution Policies without
storing routine-use content or granting generated artifacts control-plane
authority.

## Product boundary

### In scope

- Coding, Agentic, and the fixed two-stage Hybrid Mode.
- Local, content-free routine Signals and local durable aggregates.
- Immutable Candidates, Generations, Experiments, Evidence Bundles, Champions,
  Pins, Previews, Promotions, Restrictions, and Rollbacks.
- Bounded local autoresearch over declarative Policy artifacts only.
- Exact Model Identity and Execution Profile compatibility.
- Machine-gated promotion, automatic restriction/rollback, and inspectable
  CLI-first history.
- Fresh, versioned evaluation and claim receipts.
- An explicit copy-only migration from eligible v1 state.
- Explicit export/import of data-only local Improvement Bundles, quarantined on
  import.

### Not in scope for v2

- Dynamic policy-graph composition beyond the fixed Hybrid flow.
- Automatic upload of daily-use data or source content.
- Federation, reputation, discovery, synchronization, or remote governance.
- Weight-adapter learning or arbitrary generated runtime code.
- Unqualified claims that all small models are viable or that Mighty Mouse
  closes a general large-model gap.

## Normative model

The glossary in [`CONTEXT.md`](../../CONTEXT.md) is canonical. In particular:

- A **Mode** is a user-facing choice; a **Policy** is a versioned internal rule
  set for a Mode.
- A **Candidate** is immutable. A **Champion** is the active Candidate for an
  explicit Scope. An **Eligible Successor** is a verified Candidate that can
  replace a Champion when no Pin prevents it.
- An **Experiment** freezes one comparison. A **Generation** records the
  bounded improvement cycle that produced Candidates. An **Evidence Bundle**
  retains the richer, experiment-specific provenance needed to reproduce it.
- A **Signal** is a content-free routine-use receipt, never a transcript or
  task-content store.
- A **Restriction** is a safety state, distinct from an ordinary quality
  regression. It makes a Champion ineligible and initiates recovery.

Every selection and state transition is scoped at least by Mode, project or
repository, and task or model class. No silent global learned default exists.

## Functional specification

### 1. Run selection and routing

1. Resolve the current Model Identity and Execution Profile before selecting a
   learned Policy.
2. Honor an explicit user Mode override unconditionally.
3. Otherwise direct-route at confidence >=80%, select fixed Hybrid at 55–79%,
   and require the user to choose a Mode below 55%.
4. Hybrid always executes Investigation then Coding. Investigation must persist
   a typed handoff containing summary, constraints, acceptance checks, file
   scope, and risks before Coding starts.
5. Select a Champion only with exact compatibility: identical artifact digest,
   required capability vector, and compatible Execution Profile. Otherwise use
   the shipped safe baseline and explain why.

### 2. Signals and learning lifecycle

Routine Signals may record only controlled Task Category and provenance,
outcome, duration, retry count, verifier category/result, bounded environment
metadata, and an optional rating. They must exclude free text, paths, source,
prompts, transcripts, secrets, and raw outputs.

Keep detailed receipts locally for 30 days, then compact them into durable
aggregates. Users can pause collection or purge it immediately. Observe mode
collects by default. Evidence-triggered, rate-limited research may propose a
small capped set of Candidates only when comparable aggregates show an
opportunity or regression.

Background Research is user-started, bounded by the selected resource policy,
and checkpoints for foreground work. A user stop remains effective across
reboots. Cloud-backed work needs a separately remembered opt-in plus explicit
cost, rate, and concurrency bounds. Foreground-contended timing is never used
for qualified efficiency claims.

### 3. Candidate and experiment controls

Candidates may modify only declarative Policy artifacts: protocol/prompt
segments, routing thresholds and the fixed-Hybrid handoff rule, tool ordering,
retry budgets, bounded checklists, and Task Category parameters. They may not
modify the controller, evaluator, sandbox, corpus, capability probes,
compatibility rules, promotion thresholds, evidence schemas, secret handling,
resource governor, or their own base manifest.

Each Generation freezes its base Champion, compatible identity/profile, Signal
aggregate, mutation budget, seeds, task/condition order, and protocol version.
The append-only Experiment Ledger records typed outcomes, Evidence Bundle
hashes, gate results, and either `no_change` or a single holdout nomination.
The objective is lexicographic: validity/safety, paired verified quality,
efficiency, then stability. A dev winner may nominate at most one Candidate to
the independent fresh holdout; holdout results never feed tuning.
The normative evaluator boundary is defined in the
[development-suite and evaluator contract](v2-development-suite-evaluator-contract.md).

### 4. Safety, promotion, and recovery

Candidates and all content that can influence them are untrusted. Run them in a
disposable OS/container-enforced sandbox with no secrets and no network by
default. The controller independently verifies mutation scope, evaluator and
corpus integrity, provenance, compatibility, promotion gates, and recovery.

Promotion requires a completed valid Experiment, exact compatibility, current
evidence, all security gates, and a successful independent fresh-holdout gate
where required. Promotion atomically preserves the prior eligible Champion.

Immediately Restrict and roll back a Champion on a verified policy violation,
provenance mismatch, secret exposure, unauthorized host access, evaluator
tampering, material identity/profile incompatibility, or reproducible
adversarial security regression. Ordinary quality regressions use normal
rollback. Restriction preserves history, stops selection and activation, and
requires a clean new Candidate and controller-owned health check before
automatic activation can resume.

Pins freeze live Champion selection only; research can continue and may produce
Eligible Successors. A Preview is an explicitly requested bounded trial that
cannot alter Champion status, a Pin, routine Signals, or the research
objective.

### 5. Local interfaces and migration

The standalone CLI owns durable state. Host integrations are thin renderers for
status, Background Research start/stop, Pin, Preview, Rollback, and Promotion
notices; they contribute to Execution Profile but cannot own policy history or
compatibility.

Normal status must show the selected Mode, reason, override control, and
Effective Policy in plain language: Project improvement, Shared improvement,
or Safe starting settings. The default history shows Promotion, Rollback,
Restriction, Pin, Preview, and user-initiated actions. Notify for changes that
affect live behavior; keep routine Signals, rejected Candidates, and ordinary
research quiet but inspectable.

v1 remains a supported frozen legacy mode. A Migration must be dry-run first,
explicitly confirmed, and copy only eligible v1 configuration/state into
independent v2 records. It must never mutate v1 files, alter v1 command
semantics, reclassify historical evidence, or silently rerun it. Declining or
failing migration leaves v1 unchanged.

### 6. Improvement Bundles

An Improvement Bundle is explicit-export, offline-capable, and data-only. Its
JCS-canonical manifest and detached signature are checked against the
receiver's local keyring. It declares exact Model Identities, Execution Profile
constraints, schema versions, capability requirements, and optional Evidence
references. No executable payload or imported authority is accepted.

Import fails closed into non-executable quarantine and creates, at most, an
untrusted local Candidate. It must independently pass local capability probes,
isolated evaluation, holdout, provenance, and promotion gates. Model Class
membership is discovery-only; it never transfers a Champion or result.

## Experiment and public-claim protocol

Historical v1 evidence is immutable and remains historical; it is not a v2
behavioral-correctness result. New evaluation uses a separately versioned,
prospective paired protocol with new frozen tasks, executable
behavior-discriminating acceptance gates, isolated worktrees from the same base
commit, matched preparation and budgets, typed `pass`/`fail`/`invalid`/`error`
outcomes, explicit contamination and AppleDouble detection, and retained hashes
for task, model, environment, transcript, diff, command output, and Evidence
Bundle. Any protocol input change creates a new version.

Every public statement needs a versioned, expiring claim receipt binding the
wording to identity, profile, corpus/evaluator digests, protocol, uncertainty,
and expiry. The claim ladder is:

1. **Tier 0:** executable implementation fact only.
2. **Tier 1:** scoped frozen-corpus observation with numerator, denominator,
   baseline, and exploratory caveat.
3. **Tier 2:** scoped comparative claim: fresh quarantined holdout, at least 30
   paired tasks, preregistered practical-effect/protected-category regression
   bounds, 95% paired CI clearing the threshold, and exact McNemar p < .05.
4. **Tier 3:** Tier 2 replicated across three exact Model Identities, two Model
   Classes, and two source-distinct fresh corpora, with heterogeneity reported.
5. **Tier 4:** Tier 3 plus adversarial/quarantine evidence, evaluator
   attestation, an exercised guard/rollback path, and a dated monitoring
   window. This never justifies absolute security or reliability claims.

The current Gemma 30-task result is Tier 1 only.

## Delivery roadmap

### Phase A — Foundations and safe baseline

Implement versioned schemas and immutable storage for all normative records;
the Model Identity/Execution Profile resolver; scope-aware safe-baseline
selection; and CLI read-only status.

**Exit gate:** model changes create a new identity; incomplete identity cannot
select or promote a learned Champion; every state record is immutable and
traceable.

### Phase B — Controlled execution and observability

Implement routing, fixed Hybrid handoff, Signal validation/redaction,
30-day-to-aggregate retention, collection pause/purge, and the CLI history.

**Exit gate:** malformed/content-bearing Signal fields are rejected; user Mode
override wins; all confidence bands route correctly; a Hybrid handoff is
persisted before Coding; status is explainable from durable records.

### Phase C — Isolated evaluation and research

Implement sandbox boundaries, mutation-surface validation, frozen experiment
ledger, paired dev evaluator, capability probes, rate/resource governance, and
Candidate generation.

**Exit gate:** out-of-surface change, network/secret access, evaluator/corpus
write, missing provenance, or incompatible profile invalidates a run; the
ledger reproduces the declared inputs; research yields at a safe foreground
checkpoint and remains stopped after user stop.

### Phase D — Promotion and recovery

Implement Eligible Successor gates, atomic Promotion, Pin, Preview,
Restriction, Rollback, controller health checks, and live-behavior notices.

**Exit gate:** Pin blocks only activation; Preview cannot mutate durable
selection; a simulated guard breach restricts and restores the prior eligible
Champion atomically; activation stays closed until controller health checks
pass.

### Phase E — Validity, migration, and bundle boundary

Implement the fresh evaluator/holdout workflow, claim receipts, dry-run-first
v1 Migration, and data-only Bundle export/import quarantine.

**Exit gate:** v1 data remains byte-for-byte unchanged by migration; a changed
protocol cannot share evidence; consumed/contaminated holdouts block claims;
unsigned, malformed, or incompatible Bundles fail closed; no imported Bundle
can activate a Champion.

### Phase F — Evidence-backed release

Run the preregistered prospective protocol and publish only claim-receipt
wording that its evidence tier permits. Release Tier 0 implementation facts
without comparative performance claims unless higher gates pass.

**Exit gate:** all release claims link to current unexpired receipts and the
appropriate reproducible Evidence Bundles.

## Required verification matrix

- Schema/property tests for immutability, scope, typed outcomes, migration
  non-mutation, and retention/redaction boundaries.
- Integration tests for confidence routing, Hybrid handoff, compatibility
  fallback, Pin/Preview/Rollback/Restriction transitions, and background
  preemption.
- Adversarial tests for prompt injection, path escape, network access, secret
  discovery, evaluator/corpus modification, malformed/unsigned Bundle import,
  provenance replay, and harmful-promotion recovery.
- Reproducibility tests that replay a frozen ledger and compare the recorded
  artifact, environment, corpus, evaluator, and Evidence Bundle identifiers.
- Fresh paired evaluation and claim-gate checks before any comparative public
  statement.

## Source decision artifacts

- [`v1 evaluator audit`](../research/v1-evaluator-audit.md)
- [`routing flow verdict`](../prototypes/routing-flow-verdict.md)
- [`autoresearch experiment protocol`](../research/v2-autoresearch-experiment-protocol.md)
- [`development-suite and evaluator contract`](v2-development-suite-evaluator-contract.md)
- [`development-suite and evaluator boundary ADR`](../adr/0001-development-suite-and-evaluator-boundary.md)
- [`promotion state-machine verdict`](../prototypes/promotion-state-machine-verdict.md)
- [`AFK resource governance verdict`](../prototypes/afk-resource-governance-verdict.md)
- [`learning modes and settings-history verdict`](../prototypes/learning-modes-settings-history-verdict.md)
- [`fresh holdout and portfolio claim gates`](../research/v2-fresh-holdout-and-portfolio-claim-gates.md)
- [`local improvement bundles`](../research/v2-local-improvement-bundles.md)
- [`self-improvement threat model`](../research/v2-self-improvement-threat-model.md)
- [`model identity and compatibility`](../research/v2-model-identity-and-compatibility.md)
