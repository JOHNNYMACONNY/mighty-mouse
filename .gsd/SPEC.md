# Project Specification: Mighty Mouse

## Vision
**Mighty Mouse** is a lightweight, highly reliable coding-agent workflow designed to make Gemini 3 Flash more dependable for coding through enforced execution structure and autonomous evaluation loops. The goal is to transform fast, inexpensive models into disciplined engineering assistants that prioritize reliability over impulsive completion.

## v1 North Star
Make Gemini 3 Flash reliably complete coding tasks with fewer careless mistakes by forcing structured reasoning (**Plan -> Act -> Verify**) and measurable validation before final output.

## Requirements (Active)
- **Structured Reasoning**: Mandatory phase gates (Planning before implementation, Verification after implementation).
- **Enforcement Logic**: Orchestrator must reject phase-skipping, structural violations, or unverifiable results.
- **Autoresearch Integration**: Core optimization using the existing `/autoresearch` workflow for prompt and skill refinement.
- **Deterministic Evaluation**: Benchmark-driven scoring with fixed pass/fail thresholds.
- **Modular Stack**: Python-based orchestration with simple, inspectable file-based configs (YAML/Markdown/JSON).

## Out of Scope
- Full autonomous repo-wide refactors without guardrails.
- Production deployment orchestration.
- Broad multi-model routing platform.
- Deep IDE/editor integrations beyond what is needed for testing the loop.
- Non-coding agent use cases (general life automation, writing, etc.).
- Complicated memory systems or large knowledge graphs.

## Constraints
- **Model Target**: Specifically optimized for Gemini 3 Flash.
- **Resource Efficiency**: Optimized for low token usage while maintaining high reasoning depth.
- **Persistence**: Minimal infrastructure (SQLite or flat files).
- **Logging**: High reproducibility through detailed performance and iteration logs.
