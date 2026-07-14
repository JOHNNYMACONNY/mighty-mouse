# Routing-flow prototype verdict

Decision artifact for [Specify task routing and the fixed hybrid flow](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/7). This records the conclusion from the throwaway terminal prototype; it is not implementation code.

## Observed paths

- A bounded bug fix at 91% confidence routed directly to Coding.
- A feature request at 67% confidence selected Hybrid, then required an investigation-to-coding handoff before coding could start.
- An ambiguous request at 41% confidence requested an explicit Mode choice. A user override could select Hybrid, Coding, or Agentic.

## Decision

- At confidence **80% or higher**, auto-route directly to the predicted Mode.
- From **55% through 79%**, auto-route to the fixed Hybrid flow.
- Below **55%**, do not guess; require an explicit Mode selection.
- A user-selected Mode always overrides auto-routing.
- Hybrid emits a typed, persisted handoff before Coding starts: summary, constraints, acceptance checks, file scope, and risks.

## AFK research boundary

Research must run automatically in the background under the selected resource policy and yield to interactive work. Detailed scheduling, resource budgets, and preemption behavior belong to [Design AFK resource governance and preemption](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/11).
