# Skill Proposal: Surgical Multi-File Coordination (S3-MULTI)

## 1. Skill Metadata
- **skill_id**: S3-MULTI
- **name**: Surgical Multi-File Coordination
- **status**: PROPOSAL
- **trigger_tags**: ["multi-file", "cross-module", "adapter-pattern"]
- **failure_categories**: ["SCOPE", "ADHERENCE"]

## 2. Target Failure Pattern
The model frequently "drops" secondary files when a task requires modifications across multiple modules (e.g., updating an interface in `abc.py` and its implementation in `impl.py`). This leads to SCOPE failures where the implementation is incomplete or broken imports are introduced.

## 3. Evidence Trail
- **task_008_database_link_enricher**: Failed with PARSER/SCOPE issues when attempting to sync interface changes.
- **task_039_network_service_enricher**: Horizon success (274s) with heavy token churn during multi-file attempts.
- **obs_task_002**: TIMEOUT in Phase 51 where the model struggled to reconcile multiple file dependencies.

## 4. Proposed Overlay Text
```markdown
## SKILL: Surgical Multi-File Coordination (S3-MULTI)
When the task requires modifying multiple files:
1. **Dependency First**: Identify and modify the "Source of Truth" (Interfaces, Base Classes, Schemas) before updating consumers.
2. **Import Verification**: Every time you modify a function signature, immediately scan for and update all `import` statements in the other listed files.
3. **Atomic Writes**: Ensure every file listed in `expected_files` is addressed in your output, even if only for minor import alignment.
4. **Consistency Pass**: Verify that variable names and method signatures match EXACTLY across the file boundaries.
```

## 5. Latency & Stability Risk
- **Latency Risk**: **Medium**. Adds ~150 tokens to the prompt.
- **Timeout Risk**: **Medium**. Handling multiple files naturally increases token counts, which can push the model closer to the 300s wall.
- **Estimation**: May increase latency for multi-file tasks but should significantly reduce SCOPE/ADHERENCE retries by ensuring first-pass consistency.

## 6. Write Boundary Rules
- **Strict Requirement**: Respect each task’s `expected_files` boundary.
- **Integrity**: Never modify tests, fixtures, harness files, or verifiers unless explicitly listed by the task.

## 7. Anti-Patterns
- Modifying a file NOT listed in the task's `expected_files` (SCOPE violation).
- Updating an implementation without aligning its interface/base-class.

## 8. Validation Tasks
- `task_008_database_link_enricher`
- `task_039_network_service_enricher`
- `task_048_database_proxy_transformer`

## 9. Rejection Criteria
- Increase in SCOPE regressions.
- Increased timeout frequency on tasks with >2 target files.

## 10. Overlap/Conflict Risk with S1-STATE
- **S1-STATE** covers stateful logic.
- **Conflict**: Low. S3-MULTI is structural; S1-STATE is logical.
- **Policy**: In case of overlap, fail closed.
