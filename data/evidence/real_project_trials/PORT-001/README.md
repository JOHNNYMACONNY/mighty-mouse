# PORT-001 — Portfolio repository hygiene

Both conditions started from AudioServiceApp commit `ccea5b2`, excluding the
source worktree's unrelated uncommitted design-system work. They used the same
Codex/model settings, dependency tree, task, and acceptance gates. Harness alone
received the Mighty Mouse medium protocol.

Both removed exactly 242 reproducible tracked artifacts, preserved all 20
intentional `output/` evidence files, passed 19 Jest suites/57 tests, and passed
the evaluator's metadata-clean neutral build with unchanged Git status. Neither
violated scope. Control completed in 130.939 seconds; harness took 256.544
seconds. Blind review selected harness 4.7/5 versus control 4.5/5 for its stronger
evidence-presence check.

Plain builds in the external-volume worktrees were initially blocked by ignored
AppleDouble source sidecars and absent Supabase variables. The evaluator applied
the same neutral sidecar removal and inert build-time values to both conditions;
no candidate source was changed for that environment issue.

The exact condition commits are anchored by tags in the portfolio repository.
Raw sessions remain local because they contain local paths and agent
instructions; their hashes are published in the result files.
