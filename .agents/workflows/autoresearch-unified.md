---
name: autoresearch-unified
description: >
  Mighty Mouse autoresearch workflow for the Unified (XML + Reasoning) harness.
  Follows the Fail->Mutate, Pass->Expand logic natively in the IDE.
---

# /autoresearch:unified

Use this workflow to optimize the Unified Mighty Mouse harness.

## Goal
Improve the `mighty-antigravity-unified.md` prompt for small-model reliability.
Mutate the prompt when failures occur.
Expand the benchmark when the current pack passes cleanly.

## Scope
- Prompt: `/Volumes/YBF_Storage/Projects/mighty_mouse/mighty-antigravity-unified.md`
- Log: `/Volumes/YBF_Storage/Projects/mighty_mouse/flashpoint-autoresearch-results.tsv`
- Benchmarks: `/Volumes/YBF_Storage/Projects/mighty_mouse/benchmark/`

## Logic
1. **Reset**: Reset Tier N fixtures to buggy state.
2. **Execute**: Run the Unified harness natively against the task.
3. **Verify**: Run the task's test script.
4. **Mutate (Fail)**: If test fails, mutate `mighty-antigravity-unified.md` and rerun Tier N.
5. **Expand (Pass)**: If all Tier N tasks pass, generate Tier N+1 benchmarks.

## Guard Rules
- Strictly Native: No external APIs.
- One mutation per iteration.
- Freeze after 3 clean frontier packs.
