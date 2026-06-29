# Skill Proposal: Parser/Output Discipline (S5-PARSE)

## 1. Skill Metadata
- **skill_id**: S5-PARSE
- **name**: Parser/Output Discipline
- **status**: PROPOSAL
- **trigger_tags**: ["complex-refactor", "large-file", "strict-xml"]
- **failure_categories**: ["PARSER"]

## 2. Target Failure Pattern
In high-token turns (implementing large files or complex logic), the model occasionally "leaks" XML tags or fails to properly close code blocks, triggering `Schema-Triggered Retries`. While the system recovers, it wastes budget and increases TIMEOUT risk.

## 3. Evidence Trail
- **task_001_legacy_registry_ratelimiter**: 1 PARSER failure in clean runs.
- **task_015_async_service_circuitbreaker**: 1 PARSER failure.
- **obs_task_040**: Horizon success (298s) with high implementation length, risking parser truncation.

## 4. Proposed Overlay Text
```markdown
## SKILL: Parser/Output Discipline (S5-PARSE)
To ensure machine-readable compliance in complex implementation turns:
1. **XML Symmetry**: Every `<file_content>` tag must have a matching `</file_content>` tag. Do not omit the closing tag even for large files.
2. **No Fragmentary Code**: Do not use placeholders like `// ... rest of code`. You must provide the full file content within the tags.
3. **Encoding Safety**: Ensure all special characters in code blocks are properly enclosed; do not attempt to escape XML tags manually within the code block.
4. **Final Check**: Briefly verify that the last line of your response is the closing `</root>` (or equivalent) tag.
```

## 5. Latency & Stability Risk
- **Latency Risk**: **Low**. Adds ~100 tokens.
- **Timeout Risk**: **Low**. By reducing PARSER retries (which effectively double the task latency), this skill is a net benefit to stability.
- **Estimation**: Should reduce the frequency of multi-round tasks caused by schema errors.

## 6. Write Boundary Rules
- **Strict Requirement**: Respect each task’s `expected_files` boundary.
- **Integrity**: Never modify tests, fixtures, harness files, or verifiers unless explicitly listed by the task.

## 7. Anti-Patterns
- Using `...` in code blocks.
- Nesting `<file_content>` tags.

## 8. Validation Tasks
- `task_001_legacy_registry_ratelimiter`
- `task_015_async_service_circuitbreaker`
- `task_1004_stream_adapter_retry`

## 9. Rejection Criteria
- Persistent PARSER failures despite the overlay.
- Increased latency in tasks where schema errors were not previously present.

## 10. Overlap/Conflict Risk with S1-STATE
- **S1-STATE** covers logic.
- **Conflict**: Very Low. Output hygiene is orthogonal to logic.
- **Policy**: In case of overlap, fail closed.
