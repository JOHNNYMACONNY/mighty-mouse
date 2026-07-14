# v2 Autoresearch Experiment Protocol — Research Note

Scope: decision input for ["Define the autoresearch experiment protocol"](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/9). This is the v2 planning protocol, not an implementation.

## Decision

Mighty Mouse v2 runs bounded, local **Generations**. Each Generation starts from one eligible Champion, derives a content-free research brief from structured Signals, produces a small set of immutable Candidates, compares them with that Champion on a frozen development suite, and may nominate at most one Candidate for independent fresh-holdout evaluation. The experiment controller—not a model—freezes the protocol, validates artifacts, executes comparisons, and writes the ledger.

The unit of optimization is a harness Policy, not model weights, user prompts, source repositories, or evaluator behavior. Each complete attempt is an Experiment with its own immutable evidence and terminal state of `completed`, `invalid`, or `failed`.

## Allowed mutation surface

Candidates may change only versioned, declarative Policy artifacts: prompt/protocol segments; routing thresholds and fixed-Hybrid handoff rules; tool-use ordering and retry budgets; bounded checklist/rubric configuration; and task-category routing parameters. A Candidate may add a new Policy version but cannot edit its base Champion.

Candidates may not change the controller, sandbox, evaluator, holdout corpus, tool implementation, capability probes, compatibility rules, promotion thresholds, evidence schemas, secret handling, resource governor, or their own baseline/manifest. Any out-of-surface diff is a `security_failure` and invalidates the Experiment.

## Generation inputs and frozen split

| Input | Rule |
| --- | --- |
| Base Champion | Exact Champion ID, Model Identity, and compatible Execution Profile are frozen before generation. |
| Signals | Use only the defined content-free structured receipts and aggregates; never pass prompts, source, transcripts, task output, or secrets to the generator. |
| Development suite | A versioned, frozen, access-controlled dev corpus with executable acceptance and adversarial checks. The generator receives only the research brief and mutation schema, never task solutions or held-out acceptance. |
| Fresh holdout | Separate, private, versioned tasks and adversarial cases. It is unavailable to generation, dev scoring, retry diagnosis, or manual selection. A candidate sees only typed terminal outcomes after the holdout decision. |
| Protocol manifest | Freeze corpus digests, base commit, evaluator/sandbox digests, Model Identity, Execution Profile, budgets, mutation schema, objective version, thresholds, seeds, randomization schedule, and candidate cap before work begins. |

This preserves the repository’s existing prospective-study discipline: matched conditions and frozen model/corpus/budget inputs, with no silent reuse after a manifest changes. It also matches the general practice of recording run parameters, metrics, and artifacts as one experiment record ([MLflow tracking](https://mlflow.org/docs/latest/ml/tracking/)).

## Seeds, repetitions, and comparison

The controller creates a Generation seed and derives named sub-seeds for candidate proposal, task order, condition order, and every model invocation. Sampling settings are fixed. When a provider cannot enforce a seed, the manifest records `seed_enforcement=unsupported`; the run remains reproducible only as a protocol, not bit-for-bit output, and requires the configured repeated-trial count.

For each selected Candidate, compare Candidate and Base Champion in paired, isolated workspaces on the same dev tasks, under identical Model Identity, Execution Profile, tools, and budget. Randomize and record condition order within each pair. Do not rerun a completed condition; timeout, infrastructure failure, contamination, or sandbox violation receives a typed outcome and is handled symmetrically. The evaluator must retain task-level outcomes, resource use, and Evidence Bundle hashes, rather than only a summary score. This protects against misleading nondeterministic test results, whose diagnosis depends on recording runtime conditions and resources ([Google Testing Blog](https://testing.googleblog.com/2017/04/where-do-our-flaky-tests-come-from.html)).

## Objective and decision rule

Use a fixed, lexicographic objective for each protocol version:

1. **Validity and safety:** zero unresolved security, provenance, compatibility, scope, or evaluator-integrity failures; every required task produces a typed outcome.
2. **Quality:** maximize paired verified task success, with no preregistered material regression for any protected Task Category.
3. **Efficiency:** among quality-tied candidates, minimize a preregistered normalized cost vector: wall time, model tokens, tool calls, retry rounds, and human intervention.
4. **Stability:** prefer lower variance and fewer invalid/timeout outcomes; do not trade an efficiency gain for unstable behavior.

The manifest must state the protected categories, minimum paired sample, non-inferiority margins, confidence method, and tie-break order before results exist. No post-hoc weighting, metric selection, task removal, or threshold change is permitted. If the evidence is insufficient, the Generation ends without a nominee. NIST’s AI RMF emphasizes documented test, evaluation, validation, and verification so measurement can inform traceable management decisions ([NIST AI 600-1](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)).

## Ledger and lifecycle

Write an append-only local Experiment Ledger. A Generation record links its base Champion, Signal aggregate digest, protocol manifest, Candidate IDs, each Experiment, typed outcomes, and a final `no_change` or `nominate` decision. Each Experiment stores candidate/manifest hashes, model and environment identities, task/corpus identifiers, seed schedule, tool and resource receipts, evaluator result, and pointers to restricted local Evidence Bundles.

Candidate creation is capped per Generation; a Candidate can be evaluated once per frozen manifest. Failed, invalid, or rejected Candidates remain visible in the ledger but never in user-facing Champion history. A new Generation is required after any input or protocol changes; it cannot mutate a past record.

## Overfitting controls and promotion boundary

- The generator never sees holdout tasks, acceptance code, detailed holdout failures, or per-task holdout scores.
- Development tasks, objective, and candidate cap are fixed before generation; retire or replace dev tasks only in a new corpus version.
- The controller applies an independent fresh holdout to at most the nominated dev winner. A holdout failure does not trigger tuning against that holdout; it ends the Generation or requires a new corpus/protocol version.
- Retain a quarantine/adversarial suite outside the optimization objective. Any security failure invalidates rather than merely lowers a score.
- Promotion remains a separate downstream state-machine decision. This protocol may nominate one Candidate with its Evidence Bundle; it never activates a Champion itself.

## Default v2 shape

Start with one local, single-base-Champion Generation at a time, a small fixed candidate cap, and an idle-resource schedule. Parallel or federated search, adaptive objective weights, dynamic policy graphs, and weight/adaptor mutation are explicitly outside this protocol and require separate decisions.
