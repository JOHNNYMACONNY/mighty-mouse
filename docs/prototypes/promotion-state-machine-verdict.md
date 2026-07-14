# Promotion-state machine verdict

Decision artifact for [Define autonomous promotion, history, and rollback](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/10). The interactive prototype that informed this verdict has been deleted; this document is the durable outcome.

## Goal

Make recursive self-improvement automatic and quiet for ordinary users: learn from normal harness use, research while the computer is idle, and apply only verified improvements without disrupting active work.

## State model

- A **Candidate** becomes an **Eligible Successor** only after the frozen experiment protocol, fresh holdout, Model Identity, and machine gates pass.
- A **Promotion** atomically makes that Eligible Successor the **Champion** for its Scope and preserves the prior eligible Champion for Rollback.
- A **Pin** freezes only live Champion selection for its Scope. Idle research and candidate evaluation continue. A verified Candidate waits as an Eligible Successor; when the Pin is removed, a fresh gate check may promote it automatically.
- A **Preview** is an explicitly requested, bounded trial. It never changes Champion selection, Promotion state, Pin state, routine Signals, or the autonomous research objective. Its diagnostics belong only in its local Evidence Bundle.
- A verified post-Promotion guard failure creates a **Restriction**, rolls back automatically to the preceding eligible Champion, prevents re-promotion of the restricted Candidate, and pauses automatic activation for that Scope.
- While activation is paused, low-risk Signal collection and sandboxed research continue from the restored Champion. A controller-owned health check automatically reopens activation; a user may still use a manual recovery control.

## User experience

The default experience exposes no experiment controls. The user sees only a compact improvement history: Promotion, Rollback/Restriction, Pin, Preview, and an Undo/Rollback control. Rejected Candidates, raw experiments, and routine Signals remain internal unless the user opens advanced recovery details.

Normal Coding and Agentic use provides local, content-free Signals. The idle scheduler runs bounded research under the chosen resource policy and yields immediately to interactive work. No background candidate is allowed to interrupt a task or bypass the machine-gated Promotion path.

## Boundary

This verdict defines promotion and user-visible recovery behavior. [Design AFK resource governance and preemption](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/11) specifies idle detection, budgets, and preemption; the existing structured-Signal decision specifies the privacy boundary; implementation remains outside this map.
