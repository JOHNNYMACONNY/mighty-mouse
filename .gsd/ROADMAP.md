# Roadmap: Project Mighty Mouse

## Milestone 1: Baseline & Orchestration Foundation
**Goal**: Establish a measurable baseline for Gemini 3 Flash and build the Plan-Act-Verify orchestrator.

### Phase 1: Iteration #0 Baseline Evaluation
- **Task**: Implement a benchmark runner and record the raw performance of Gemini 3 Flash.
- **UAT**: `autoresearch-results.tsv` contains a valid baseline (Iteration #0).

### Phase 2: Plan-Act-Verify Orchestration
- **Task**: Implement the `src/orchestrator/` logic to enforce structured reasoning.
- **UAT**: Orchestrator rejects a mock "phase-skipping" output.

### Phase 3: Benchmark Task Set v1
- **Task**: Populate `tasks/benchmark/` with 5-10 deterministic coding challenges.
- **UAT**: All benchmark tasks have automated test scripts.

## Milestone 2: Autoresearch Optimization
**Goal**: Use the `/autoresearch` loop to improve reliability metrics.

### Phase 4: Prompt Engineering Iterations
- **Task**: Run 10+ autoresearch iterations focused on system prompt refinement.
- **UAT**: Success rate increases by 10%+ over baseline.

### Phase 5: Skill & Tool Refinement
- **Task**: Optimize tool definitions and error-handling prompts.
- **UAT**: Retry count reduces to < 1.3 per task.

## Future Milestones
- **Milestone 3**: Efficiency & Guardrail Tuning (Token optimization).
- **Milestone 4**: Multi-task Scaling (Complex multi-file tasks).
