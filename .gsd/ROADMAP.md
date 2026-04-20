# Roadmap: Project Mighty Mouse

## Milestone 1: Baseline & Orchestration Foundation [x]
**Goal**: Establish a measurable baseline for Gemini 3 Flash and build the Plan-Act-Verify orchestrator.

### Phase 1: Iteration #0 Baseline Evaluation [x]
- [x] Task: Implement a benchmark runner and record the raw performance of Gemini 3 Flash.
- [x] UAT: `autoresearch-results.tsv` contains a valid baseline (Iteration #0).

### Phase 2: Plan-Act-Verify Orchestration [x]
- [x] Task: Implement the `src/orchestrator/` logic to enforce structured reasoning.
- [x] UAT: Orchestrator rejects a mock "phase-skipping" output.

### Phase 3: Benchmark Task Set v1 [x]
- [x] Task: Populate `tasks/benchmark/` with 5-10 deterministic coding challenges.
- [x] UAT: All benchmark tasks have automated test scripts.

## Milestone 2: Autoresearch Optimization [x]
**Goal**: Use the `/autoresearch` loop to improve reliability metrics.

### Phase 4: Prompt Engineering Iterations [x]
- [x] Task: Run 10+ autoresearch iterations focused on system prompt refinement.
- [x] UAT: Success rate increases by 10%+ over baseline (Final: 90.91%).

### Phase 5: Skill & Tool Refinement [x]
- [x] Task: Optimize tool definitions and error-handling prompts.
- [x] UAT: Retry count reduces; stability gate passed at 90.91%.

## Milestone 3: Efficiency & Guardrail Tuning [/]
**Goal**: Token optimization and safety guardrails.

### Phase 6: Token Efficiency [ ]
- [Task]: Refine prompts to reduce verbosity in reasoning phase without lowering reliability.
- [UAT]: Average input tokens per task reduced by 15%.

### Phase 7: Robustness & Failure Post-Mortems [ ]
- [Task]: Implement automated failure-mode analysis tools for Batch 2.
- [UAT]: `mighty_mouse_agent` automatically logs "Lessons Learned" on unit test failure.

## Future Milestones
- **Milestone 4**: Multi-task Scaling (Complex multi-file tasks).
- **Milestone 5**: Full LLM Integration (Live Gemini 3 Flash).
