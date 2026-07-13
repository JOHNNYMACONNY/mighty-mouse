# v2 Development Suite and Evaluator Contract

Scope: frozen planning contract for [issue #23](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/23). This defines the evaluator boundary for a bounded, local improvement loop; it does not implement it or authorize promotion.

## Product outcome

After a user starts Background Research, Mighty Mouse may evaluate the immutable Candidates from one frozen Generation against its base Champion. The user sees one plain-language outcome: **No change**, **Evaluation could not be trusted**, or **One candidate is awaiting an independent check**. The technical ledger and Evidence Bundles remain available on demand; the user never has to select metrics, worktrees, seeds, or task order.

The evaluator improves the harness recursively only through versioned Policy Candidates. It never changes model weights, the evaluator, the sandbox, corpus contents, capability probes, compatibility rules, promotion rules, or the Protocol Manifest.

## Corpus boundary

The operational Development Suite is a versioned, local, access-controlled corpus. Each task has a stable identifier, Task Category, executable behavior-discriminating acceptance, adversarial checks, source/provenance metadata, and a corpus digest. A Protocol Manifest freezes that digest before Candidate generation. Repository fixtures may test evaluator behavior but must be synthetic and insufficient to represent the operational suite.

The Fresh Holdout is a separately versioned, private corpus. It is unavailable to Candidate generation, development scoring, failure diagnosis, retry selection, and manual selection. This evaluator receives no holdout task, acceptance, score, or detailed result; it can only emit one Holdout Contender identifier for the later independent gate.

## Frozen request

Before scored work, the controller validates and records:

- the Generation, base Champion, every Candidate, Scope, exact Model Identity, compatible Execution Profile, and allowed Policy mutation surface;
- the base workspace commit and digest, Development Suite digest, evaluator and sandbox digests, preparation and budget digests, protocol/objective version, protected Task Categories, repetitions, seed schedule, and balanced condition-order schedule;
- capability probes, sandbox isolation, corpus/provenance integrity, and attestation that Candidates cannot alter evaluator-owned artifacts.

Any mismatch, missing digest, contamination finding, security failure, failed required probe, or failed sandbox check invalidates the Experiment before a nomination is possible. A changed input requires a new Generation and Protocol Manifest; no completed condition is silently rerun.

## Paired execution

The controller evaluates every Candidate independently against the same base Champion. For every Candidate, task, and precommitted repetition, it creates separate disposable worktrees from one verified base snapshot; applies matched preparation, Model Identity, Execution Profile, tools, budget, and seed; and follows the recorded randomized condition order. Candidate and Champion conditions cannot share a mutable workspace, output, cache, or preparation artifact.

The controller owns task material, acceptance execution, and Evidence Bundle creation. The Policy runner receives only the condition inputs needed to perform the task. Runs are sequential for one Generation by default, so background research remains resource-bounded and foreground work can preempt it; parallel evaluation requires a later resource-governance decision.

## Typed outcomes and terminal states

Every condition records exactly one typed result: `pass`, `fail`, `invalid`, or `error`. `timeout` is an `error` with a machine-readable reason, rather than a fifth success-like category. Each result links to immutable Evidence Bundle hashes that capture the manifest digest, task identifier, workspace/base digest, Model Identity, Execution Profile, condition order, seed, resource receipts, acceptance result, and redacted diagnostic provenance.

- `fail` means the condition completed and did not meet acceptance. It is normal scored evidence.
- `error` means the condition could not complete because of infrastructure, runtime, or timeout failure. A Candidate with an error is ineligible; an error in the base Champion fails the Experiment and prevents nomination.
- `invalid` means comparison integrity is broken, including contamination, safety, attestation, evaluator, compatibility, scope, or sandbox failure. Any such result invalidates the Experiment and prevents nomination.

An Experiment terminal state is `completed`, `failed`, or `invalid`. A completed Experiment may still end in `no_change`; a failed or invalid Experiment always ends in `no_change` and is visible in the ledger without entering Champion history.

## Decision rule

The controller applies a fixed, lexicographic rule declared in the Protocol Manifest:

1. Validity and safety: only Candidates from a completed valid Experiment are eligible.
2. Paired verified quality: a Candidate must have strictly more accepted paired task outcomes than the base Champion and no regression in any precommitted protected Task Category.
3. Efficiency: among quality-tied eligible Candidates, prefer lower precommitted normalized cost (wall time, model tokens, tool calls, and retry rounds).
4. Stability: then prefer lower invalid/error/timeout rate and lower outcome variance across repetitions.
5. Deterministic final tie: if all declared criteria tie, record `no_change`; never manufacture a winner from Candidate ID or arrival order.

The Experiment Ledger appends the full ranking inputs and records either `no_change` or exactly one Holdout Contender. A Generation is permanently limited to one nomination across all its Experiments. Holdout results cannot alter development ranking or generate a retry; they proceed only to the independent fresh-holdout workflow.

## Required verification

End-to-end evaluator tests must demonstrate: all Candidates receive matched isolated comparisons; a valid global winner; no change on a quality tie or protected-category regression; Candidate error ineligibility; base error failure; invalidation on contamination or gate failure; immutable Evidence Bundle linkage; prohibition of a second nomination; and absence of any holdout input from this API. Contract fixtures must also prove that a timeout is recorded as an `error` reason and that user-facing status never claims promotion or a validated improvement.
