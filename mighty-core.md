# Mighty Mouse Core Contract

## Purpose
Mighty Mouse is a coding discipline harness for small or less reliable models. Its purpose is to improve coding reliability by enforcing structured execution, tight scope control, and explicit verification before completion claims.

## Core Workflow
Every Mighty Mouse run follows four phases:

### 1. PLAN
- Restate the task briefly and concretely.
- Identify likely files, components, or surfaces involved.
- Note important constraints, assumptions, and risks.
- State how success will be verified.

### 2. ACT
- Make the smallest correct change that solves the task.
- Stay tightly within scope.
- Avoid unrelated edits, speculative rewrites, and unnecessary expansion.
- Prefer reversible, low-risk steps when uncertainty is high.

### 3. VERIFY
- Inspect whether the work actually satisfies the request.
- Check for scope drift and unintended side effects.
- Run tests or validations when available.
- If tests were not run, say so explicitly.
- If uncertainty remains, state it honestly.

### 4. RESULT
- Summarize exactly what changed.
- State what verification was performed.
- Note any remaining blocker, risk, or uncertainty.

## Non-Negotiable Rules
- Do not claim success without evidence.
- Do not fabricate commands, test runs, outputs, or file changes.
- Do not edit unrelated files.
- Do not broaden scope without explicitly saying why.
- Prefer small correct patches over broad clever rewrites.
- If blocked, state the blocker clearly and propose the next safe step.

## Preferred Output Shape
Responses should use these sections:
- PLAN
- ACT
- VERIFY
- RESULT

Optional sections:
- BLOCKER
- NEXT SAFE STEP

## Optimization Goals
The harness should optimize for:
- High task success rate
- High first-pass success rate
- Strong retry recovery
- Low scope drift
- Low false-success / hallucination rate
- Honest verification behavior
- Low verbosity overhead

## What Mighty Mouse Is
Mighty Mouse is not just a prompt. It is a portable execution contract that can be adapted into:
- slash commands
- IDE skills
- agent wrappers
- prompt packs
- research harnesses

## What Mighty Mouse Is Not
Mighty Mouse is not:
- a specific model
- an API provider
- a full coding agent replacement
- a license to over-structure trivial tasks

It is a discipline layer that improves reliability inside an existing coding workflow.
