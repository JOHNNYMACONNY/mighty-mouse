# PORT-002 — Work destination validation

Both conditions started from AudioServiceApp commit `2763c8a`, excluding the
source worktree's unrelated uncommitted design-system work. They used the same
Codex/model settings, dependency tree, task, and acceptance gates. Harness alone
received the Mighty Mouse medium protocol.

Both stayed within the ten frozen paths, passed 20 Jest suites and TypeScript,
and passed the evaluator's metadata-clean production build with unchanged Git
status. Control completed in 233.596 seconds; harness took 268.538 seconds.

Blind review selected harness 4.5/5 versus control 3.75/5. Harness validated
route and repository constructor inputs, covered evidence-source URLs, detected
duplicate source links, and avoided control's potentially duplicated repository
links. Control had stronger direct rendered CTA coverage.

The exact condition commits are anchored by tags in the portfolio repository.
Raw sessions remain local because they contain local paths and agent
instructions; their hashes are published in the result files.
