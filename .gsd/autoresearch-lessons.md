# Autoresearch Lessons: Batch 1 Prompt Optimization

## Failure Mode Analysis (Tier 1 Complex Tasks)

### 1. Structural Blindness (Task 08: Multi-File API)
- **Problem**: Lower-tier models often lose context when switching between files, resulting in mismatched signatures.
- **Pattern**: `ImportError` or `TypeError` due to incomplete refactoring.
- **Mitigation**: Planning segment must enforce a **Dependency Map** before the first file write.

### 2. Instruction Saturation (Task 09: Robust Math)
- **Problem**: When faced with 3+ distinct constraints (ZeroDiv, Types, Whitespace), models often "drop" the least emphasized one.
- **Pattern**: `safe_divide` handles division but ignores input sanitization.
- **Mitigation**: Verification segment must require a **Constraint Checklist** mapped 1:1 to the prompt instructions.

### 3. Constraint Leakage (Task 10: Constraint Compliance)
- **Problem**: Defaulting to standard libraries (e.g., `import base64`) despite negative constraints.
- **Pattern**: Success in logic, but FAIL on UAT due to "Banned Module" detection.
- **Mitigation**: Discipline segment must explicitly enforce a **No-Imports Policy** for restricted tasks.

## Heuristic Optimizer State
- **Iteration 1-3**: Stagnant Score (18.18) due to hardcoded solver.
- **Iteration 4+**: Unblocked via Heuristic Logic check in `mighty_mouse_agent.py`.

## Failure Analysis - 2026-04-19 19:46:00
Total Failures: 1
- **task_02_data_parse**: [LOGIC] Tests failed

## Failure Analysis - 2026-04-19 19:46:11
Total Failures: 1
- **task_02_data_parse**: [LOGIC] Tests failed

## Failure Analysis - 2026-04-19 19:46:33
Total Failures: 1
- **task_02_data_parse**: [LOGIC] Tests failed

## Failure Analysis - 2026-04-19 19:47:06
Total Failures: 1
- **task_02_data_parse**: [LOGIC] Tests failed
