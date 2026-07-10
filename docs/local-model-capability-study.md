# Local-Model Capability Study

Status: **prospective protocol draft — no scored runs may begin until this document and a held-out corpus manifest are frozen in Git**

## Product thesis

Mighty Mouse exists to make small, locally operated models more viable for coding and agentic work. The primary question is not whether a frontier model behaves differently with the harness. It is whether the harness measurably improves a small local model and closes part of the capability gap between that model and a stronger reference model.

The first target is the locally installed `gemma4:e4b` model: Gemma 4 architecture, 8B parameters, Q4_K_M quantization. Results from this target must not be generalized to every local or small model.

## Questions

1. **Harness lift:** Does Gemma with Mighty Mouse complete more unseen, verifiable tasks than the same Gemma model without Mighty Mouse?
2. **Gap closure:** How much of the completion-rate gap between raw Gemma and a larger reference model does Mighty Mouse close?
3. **Operating cost:** What changes in elapsed time, model tokens, tool calls, retry rounds, and human interventions?
4. **Task fit:** Are gains concentrated in particular complexity levels or in coding versus agentic tasks?

## Conditions

Every scored task has three isolated conditions from the same repository snapshot:

| Condition | Model | Orchestration |
| --- | --- | --- |
| `gemma_raw` | `gemma4:e4b` | Minimal neutral agent loop; no Mighty Mouse protocol, decomposition, verification feedback, or recovery policy |
| `gemma_mighty_mouse` | `gemma4:e4b` | Mighty Mouse protocol, decomposition, project-native verification feedback, and bounded recovery |
| `reference_raw` | Frozen larger model | The same minimal neutral agent loop used by `gemma_raw` |

The reference model and version must be frozen before the scored corpus begins. It is a comparison anchor, not a claim that all large models perform identically.

## Fairness invariants

- All three conditions receive the same task brief, base commit, initial repository files, tool definitions, network policy, and acceptance commands.
- The two Gemma conditions use the same Ollama model digest and sampling settings.
- All conditions receive the same maximum wall time, context limit, output-token limit, tool-call limit, and maximum number of model turns.
- Each condition may inspect files, search text, write bounded patches, and run allowlisted project commands through the same tool implementation.
- Mighty Mouse may choose how to spend the shared budget; it may not receive a larger budget.
- Acceptance tests remain hidden from the model when they represent held-out behavior. Public project tests visible in the repository remain visible to every condition.
- Conditions run in isolated disposable worktrees. No condition may inspect another condition's transcript, diff, verifier output, or workspace.
- Order is randomized and recorded per task. Cache state and model warm-up are normalized before timed measurement.
- A failed, slower, or unfavorable Mighty Mouse result is retained.
- Pilot tasks, previously completed tasks, historical synthetic tasks, and tasks used to tune prompts are excluded from the scored corpus.

## Agent runtime requirement

The study requires a genuine tool-using loop. A one-shot response parser that writes fenced code blocks is insufficient evidence for agentic capability.

The shared runtime must expose a small, auditable tool surface:

1. `list_files` within the workspace
2. `read_file` with byte and path limits
3. `search_text` within the workspace
4. `apply_patch` or an equivalently bounded file-edit operation
5. `run_check` for allowlisted test, lint, typecheck, and build commands
6. `finish` with a structured result

Every tool call, result, token count, model turn, file mutation, and command execution must be recorded. Paths may not escape the disposable workspace. Shell strings from the model may not be executed directly.

## Corpus

The full scored corpus contains at least **30 unseen tasks**:

- 15 coding tasks: bug fixes, bounded features, refactors, test additions, and cross-file changes.
- 15 agentic tasks: repository investigation, failure diagnosis, multi-step tool use, stateful workflow repair, and evidence-backed completion.
- At least 10 low-, 10 medium-, and 10 high-complexity tasks under a frozen rubric.
- Tasks span at least three repositories and at least two implementation languages.
- Every task has executable acceptance commands and explicit allowed paths.

Task selection and acceptance criteria are frozen before scored execution. If a task becomes invalid, the reason is recorded and a prospectively authored replacement is added; a completed task is never substituted.

The held-out task bundle is stored outside this public repository. Its `corpus.json` records each task's relative path, category, complexity, repository, and implementation language. The runner validates the 15/15 category split, 10/10/10 complexity split, and three-repository/two-language minimum before contacting a model; it records the corpus digest in every run manifest. Only the final evidence manifest and redacted results are published.

## Pilot gate

Before freezing the scored corpus, run exactly three unscored pilot tasks—one low, one medium, and one high complexity—to verify:

- all conditions receive equivalent tools and budgets;
- workspaces remain isolated;
- acceptance checks detect deliberately incorrect implementations;
- transcripts and metrics are complete;
- timeout and crash recovery are deterministic;
- the runner can resume without silently rerunning completed conditions.

Any prompt, runner, rubric, or budget change after the pilot requires a new protocol version. No tuning is allowed after scored execution begins.

## Scored execution

`python -m eval.run_local_model_study --corpus /private/corpus.json --output-dir /private/run --reference-model gpt-oss:20b` runs the three conditions on isolated workspaces. The command can resume only when the existing study manifest exactly matches the frozen corpus digest, model digests, seed, and budget. Completed condition result files are reused; they are never silently rerun.

## Outcomes

### Primary

**Verified task completion rate**: the condition passes every frozen acceptance command with no disallowed file changes or manual repair.

### Secondary

- first-attempt verified completion;
- completion after bounded recovery;
- human interventions;
- scope violations;
- wall-clock duration;
- prompt, completion, and total tokens;
- tool calls and failed tool calls;
- verification rounds;
- blind maintainability score on passing solutions;
- local compute peak memory and energy proxy where measurement is reliable.

## Analysis

For paired binary outcomes, report task-level results and paired confidence intervals. Use McNemar's test for the primary `gemma_raw` versus `gemma_mighty_mouse` comparison when the discordant-pair count is sufficient; otherwise report the exact paired result without a superiority claim.

Define completion-rate gap closure as:

```text
(Gemma+MM completion rate - raw Gemma completion rate)
----------------------------------------------------------------
(reference completion rate - raw Gemma completion rate)
```

Report this value only when the reference completion rate is greater than raw Gemma. Cap neither negative results nor values above 100%; explain both. Also report absolute percentage-point differences so the ratio cannot hide a small denominator.

Break results down by coding versus agentic tasks and by frozen complexity level. Treat subgroup results as exploratory unless the corpus is expanded and powered for them.

## Claim gate

Mighty Mouse may be described as improving this Gemma configuration only if the scored evidence shows a meaningful positive paired completion difference and the uncertainty is reported. “Closes the small-model gap” requires a positive gap-closure result on the frozen corpus.

No result from this study alone supports claims about all small models, all repositories, production safety, or universal cost savings.

## Relationship to existing evidence

- The historical 15-task Gemma corpus remains a synthetic latency experiment with permissive tests and a ceiling effect.
- The completed 10-task GPT-5.5 study remains evidence about harness behavior on one frontier-model workflow, not the primary product-thesis test.
- Neither dataset is pooled into the new primary analysis.

## Required artifacts

- frozen protocol commit and model digests;
- task manifests and repository base commits;
- environment and dependency fingerprint;
- randomized condition order;
- raw model transcripts and tool events;
- before/after diffs and file-scope audit;
- acceptance-command output;
- per-condition resource and timing metrics;
- machine-readable aggregate results;
- human-readable report with unfavorable outcomes retained;
- SHA-256 manifest covering the complete evidence bundle.
