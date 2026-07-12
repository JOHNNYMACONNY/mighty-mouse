# v2 Fresh Holdout and Portfolio Claim Gates

Scope: decision input for [issue #13](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/13). This note defines proposed evidence gates for public capability statements; it does not change promotion policy or make a public claim.

## Recommendation

Treat a portfolio statement as a **versioned claim receipt**, not a product-wide conclusion. A receipt binds one precisely worded claim to a Candidate/Champion, exact Model Identity and Execution Profile, corpus and evaluator digests, protocol, result, uncertainty, and expiry state. It is invalidated when any of those inputs changes or the claim holdout is exposed beyond its precommitted query budget.

This is stricter than a normal development evaluation. Repeated adaptive inspection can overfit a holdout itself ([Dwork et al.](https://arxiv.org/abs/1506.02629)); the same risk is why NIST advises keeping held-out tests private and removing solution-leaking material from agent evaluations ([NIST CAISI](https://www.nist.gov/caisi/cheating-ai-agent-evaluations/4-practices-detecting-and-preventing-evaluation-cheating)). NIST's AI RMF also calls for documented test sets, metrics, tools, uncertainty, and independent assessment ([AI RMF 1.0](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf)).

## Freshness and integrity gates

All gates are required before a result can leave the `diagnostic` tier.

1. **Quarantine.** The claim holdout is private, access-controlled, and unavailable to candidate generation, dev scoring, prompt/policy/threshold selection, failure diagnosis, and manual selection. Reveal only a terminal gate result while tuning. The existing v2 protocol already requires this separation ([protocol](v2-autoresearch-experiment-protocol.md)).
2. **Provenance and decontamination.** Freeze task source, commit, authoring date, task-family label, acceptance/evaluator digest, and corpus digest before evaluation. Check exact and near-duplicate task/fixture/solution fingerprints against training, development, and prior claim-holdout material. Missing lineage or unresolved overlap is `blocked`, not a pass; duplicate leakage can materially inflate test performance ([Barz and Denzler](https://arxiv.org/abs/1902.00423)).
3. **Precommitment.** Before either condition runs, freeze the primary outcome, protected Task Categories, minimum practical effect, non-inferiority bounds, confidence method, run budget, model/configuration, repetitions, and wording that could be earned. No task removal, metric substitution, or post-hoc threshold changes.
4. **Paired, isolated execution.** Compare Candidate and named baseline on each same task with randomized condition order, identical budget/tools, clean workspaces, executable behavior-discriminating acceptance, and independent acceptance rerun. A timeout, contamination, attestation failure, evaluator mismatch, or security failure is typed and fails the integrity gate; it is never silently rerun or counted as success.
5. **Rotation.** A claim holdout is consumed for that candidate/claim family once detailed results are disclosed, its query budget is exceeded, or any Candidate/Champion/prompt/model/evaluator/corpus input changes. Promotion after a failed holdout requires a new holdout or a formally valid reusable-holdout mechanism—not tuning on the failed one. Controlled adaptive reuse is possible only with a protocol designed for it ([Feldman and Steinke](https://proceedings.mlr.press/v65/feldman17a.html)).

## Proposed claim ladder

| Tier | Permitted wording | Required evidence | Prohibited shortcut |
| --- | --- | --- | --- |
| 0 — implementation fact | “Mighty Mouse has [named capability].” | Versioned source, executable check or smoke evidence, exact version. | Calling existence a performance or safety result. |
| 1 — scoped observation | “In a frozen [N]-task fixture corpus, exact configuration X completed A/N vs B/N.” | Existing 30-task result may qualify only with its current exploratory caveat, full numerator/denominator, baseline, and no superiority language. | “Improves agents,” “reliable,” or extrapolation to other models/repos. |
| 2 — scoped comparative claim | “For exact Model Identity X, on fresh corpus Y, Mighty Mouse improved verified completion by D pp versus baseline Z.” | One quarantined claim holdout; at least 30 paired tasks across the claim’s declared categories; exact paired analysis; 95% CI for D has lower bound above the preregistered minimum practical effect; exact McNemar p < .05 when a superiority claim is made; no protected-category lower CI below its preregistered non-inferiority bound; all integrity gates pass. | Broad model-family, production-safety, or universal cost claims. |
| 3 — replicated scope claim | “Across the named model families and task sources, the preregistered result replicated.” | Tier-2 gate independently repeated on at least three complete Model Identities spanning at least two declared Model Classes, and at least two independently authored/source-distinct fresh corpora. Each model-by-corpus cell passes its primary quality and protected-category gates; report every cell and heterogeneity, not only a pooled score. | “Works for all models/repositories.” |
| 4 — operational reliability claim | “Under the stated scope, the controller automatically rejected/rolled back verified guard failures.” | Tier-3 evidence plus adversarial/quarantine suite, independent evaluator attestation, post-promotion guard/rollback exercise, and dated monitoring window. | “Production safe,” “secure,” or “never fails.” |

The current `gemma4:e4b` 30-task result remains Tier 1: it is directionally positive but has exact McNemar p = 0.50 and explicitly does not establish superiority ([current result](../local-model-capability-results.md)).

## Statistical and replication policy

- The primary endpoint is paired verified task success. Report the paired difference, discordant pairs, exact McNemar result, and a two-sided 95% paired confidence interval. If the CI does not clear the preregistered practical-effect threshold, do not make a lift claim even when the point estimate is positive. Paired testing is the correct family for matched binary outcomes ([Dror and Reichart](https://arxiv.org/abs/1809.01448)).
- Pre-register sample-size/power calculation from the claimed minimum effect and expected discordance; “at least 30” is a floor for a narrow scoped screen, not evidence that any desired effect is detectable. Subgroups are exploratory unless separately powered.
- For nondeterministic systems, use three precommitted repetitions per task/condition (or record an enforced deterministic seed). Aggregate by a precommitted task-level rule; report per-run variance and invalid/timeout rates.
- Efficiency can be a secondary claim only after the quality and safety gates pass, with an upper confidence bound showing the preregistered cost metric is no worse (or better, if that is the claim). Never trade quality for a cheaper headline.
- Each additional public endpoint or subgroup must be predeclared and multiplicity-controlled, or called exploratory.

## Receipt states and portfolio copy

Use `diagnostic` (development only), `candidate` (blind holdout passed), `promoted` (candidate plus independent verifier signature and current inputs), `stale` (input changed, query budget exhausted, or expiry reached), and `blocked` (lineage/contamination/attestation unresolved). Portfolio copy must include the tier, scope, date, exact model/configuration, corpus size/source classes, baseline, point estimate and uncertainty, and a link to the receipt. Fresh test sets can reveal meaningful distribution shifts even when the original benchmark is strong ([Recht et al.](https://arxiv.org/abs/1902.10811)); therefore `promoted` means evidence is current for its receipt scope, not a timeless or universal property.

## Decision boundary

Adopt the gate structure and receipt vocabulary now. Choose numerical practical-effect and non-inferiority margins, query budgets, and claim-holdout expiry durations in a later protocol amendment with power analysis; the cited sources support precommitment and independence, not one universal number. Keep promotion separate: passing a portfolio gate may support a statement, while Champion activation still requires the existing machine-gated fresh-holdout, compatibility, and rollback path.
