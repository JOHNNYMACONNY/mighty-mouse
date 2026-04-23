# Milestone Requirements: Autoresearch Loop Expansion

## Goal
To aggressively expand the capabilities of smaller models (specifically targeting Gemini 3 Flash) by running an autonomous optimization loop that mutates the cognitive IDE-native prompt (the "harness") and autonomously scales the difficulty of benchmarks when success is reached.

## 1. Portable IDE-Native Harness Optimization
- [ ] **Prompt-Driven Architecture**: The autoresearch loop must focus on mutating a portable prompt block (like `/mighty`) that can be pasted into any IDE's custom instruction or slash command configuration.
- [ ] **No External Orchestrators**: The strategies implemented must rely entirely on the LLM's built-in agent capabilities driven by the prompt, avoiding complex external Python API scripts.
- [ ] **Advanced Reasoning Strategies**: The loop should test advanced in-prompt techniques such as chain-of-thought scratchpads, self-reflection loops, and explicit state tracking to boost small model reliability.

## 2. Autonomous Benchmark Escalation (Pass -> Expand)
- [ ] **Dynamic Difficulty Scaling**: When the autoresearch loop verifies a 100% pass rate on a benchmark pack, it must autonomously generate the next, harder benchmark pack (Pack N+1) rather than over-optimizing the prompt.
- [ ] **Rigorous Verification**: No fake confirmations. Verification must be mechanically reproducible (e.g., test scripts passing cleanly) before a benchmark expansion is triggered.
- [ ] **Challenging Domains**: New benchmarks must test complex agentic abilities, such as multi-file refactoring, debugging subtle logical errors, and open-ended system design.

## 3. Targeted Baseline Model
- [ ] **Gemini 3 Flash Focus**: The primary target for optimization remains Gemini 3 Flash. Improvements here will act as a rising tide for all small models.

## Constraints & Rules
- Do not introduce Python dependencies or API keys; the output must be a portable Markdown prompt.
- Verification must remain strict and deterministic.
