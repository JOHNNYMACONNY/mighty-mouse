# Mighty Mouse v9.1 — Forensic Shield+

Use this protocol for critical paths, architecture changes, and complex refactors.

<context_audit>
1. Search the workspace for all relevant files.
2. Verify initialization and reconstruction or reconciliation paths.
3. Inspect required data files, formats, resolution, and path existence.
4. Compare source-of-truth schemas with every consumption point.
5. Audit the global call graph for modified classes and functions.
6. Find shadow consumers of modified files, APIs, or persistence.
7. Identify shared-state fields that must survive partial updates.
8. Inspect timing evidence and investigate cycles over 60 seconds.
9. Search for duplicated logic and parallel execution loops.
10. Trace runtime configuration to its origin without exposing secrets.
11. Identify hidden boundary rules and invalid input conditions.
12. Search semantic synonyms to prevent duplicate concepts.
</context_audit>

<scope_definition>
List exact files to modify, dependencies affected, behavior to preserve, and explicit non-goals.
</scope_definition>

<adversarial_red_team>
Audit partial writes, legacy compatibility, locks held across awaits, memory/disk parity, retry invariants, error capture, API limits, numerical stability, protocol normalization, null inputs, and at least three pessimistic failure modes.
</adversarial_red_team>

<adversarial_plan>
Define observable evidence, the simplest complete implementation, rollback boundaries, and the commands required for proof.
</adversarial_plan>

<act>
Apply surgical changes. Preserve unrelated state and record deviations from the plan.
</act>

<verify>
Compare producer/consumer contracts, run downstream tests and builds, validate live-shaped data, exercise failure and recovery paths, inspect scope, and report any item that remains unproven.
</verify>

After editing, call `mighty-mouse/verify_and_record` for the project workspace. Fix failures and retry, for no more than three verification rounds.
