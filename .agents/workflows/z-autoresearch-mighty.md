---
name: autoresearch-mighty
description: >
  Mighty Mouse autoresearch workflow. Mutate the v9.1 protocols when the
  local model pilot corpus exposes failures. When the current pack passes
  cleanly, stop prompt polishing and generate the next harder benchmark pack
  instead. Freeze after 3 clean packs unless explicitly expanding the eval
  suite.
---

# /autoresearch:mighty

Use this workflow to improve the Mighty Mouse protocols themselves — not to run a normal coding task.

## Goal
Improve the Mighty Mouse coding protocols for small-model reliability, but only mutate the prompt when the current pilot tasks expose real failures. If the current pack passes cleanly, stop prompt optimization and generate/expand to harder tasks.

## Scope
Only modify files inside these surfaces:
- `src/mighty_mouse/protocols/v9.1/low.md`
- `src/mighty_mouse/protocols/v9.1/medium.md`
- `src/mighty_mouse/protocols/v9.1/high.md`

Do not modify unrelated repo files.

## Metric Priority
Optimize for task success rate.
Priority order:
1. `pass_rate` (higher is better)
2. lower prompt bloat if the pass rate is unchanged

## Verify Command
```bash
PYTHONPATH=.:src .venv/bin/python eval/autoresearch_harness.py --tasks-dir eval/local_model_pilot --model gemma4:e4b
```

## Guard Command
```bash
PYTHONPATH=.:src .venv/bin/python -m pytest -q
```

## Cycle Ladder
- **Fail** -> mutate protocols
- **Pass cleanly** -> expand tasks (or generate more complex test scenarios)
- **3 Clean Packs** -> freeze

## Mutation Axes
Grounded in the actual protocol structure:
- `<context_audit>` step count and verbosity
- `<scope_definition>` instruction clarity
- `<adversarial_red_team>` checklist
- `<plan>` vs `<adversarial_plan>` structure
- `<verify>` instruction specificity
- Output format instructions (fenced code with paths)
- Overall prompt length and density
