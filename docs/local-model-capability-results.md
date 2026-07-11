# Local-Model Capability Study — v1 Results

Status: **scored run complete; exploratory evidence**

This report covers the frozen 30-task corpus at private corpus commit `3fc24eb` and the three-condition run stored in the private evidence bundle. The tasks are source-derived, disposable fixtures; they are not claims that an agent changed the production repositories.

## Conditions

| Condition | Model | Completion | Median duration | Median tokens |
| --- | --- | ---: | ---: | ---: |
| `gemma_raw` | `gemma4:e4b` | 6/30 (20.0%) | 116.8 s | 10,604 |
| `gemma_mighty_mouse` | `gemma4:e4b` | 8/30 (26.7%) | 99.5 s | 10,206 |
| `reference_raw` | `gpt-oss:20b` | 13/30 (43.3%) | 157.9 s | 70,541 |

## Paired result

Against raw Gemma, Mighty Mouse produced:

- 2 Mighty-Mouse-only wins
- 0 raw-only wins
- 6 tasks where both passed
- 22 tasks where both failed
- +6.7 percentage points completion lift
- exact McNemar p = 0.50

The result is directionally positive, but the sample has only two discordant wins and does not support a superiority claim. It is evidence that this protocol can produce a measurable lift, not proof that Mighty Mouse generally makes small local models viable.

## Reference gap

The raw-Gemma-to-reference gap was 23.3 percentage points. Gemma + Mighty Mouse closed 6.7 points of that gap, or **28.6%**. This is a scoped result for `gemma4:e4b`, `gpt-oss:20b`, this frozen corpus, and this tool protocol. It must not be generalized to all small models, repositories, production safety, or cost savings.

The lower median token and duration figures for Gemma + Mighty Mouse are secondary efficiency observations, not a substitute for completion quality.

## Claim decision

Portfolio-safe wording:

> On a frozen 30-task coding and agentic fixture corpus, Mighty Mouse increased Gemma 4 e4b completion from 20.0% to 26.7% (+6.7 percentage points), with 2 paired wins and no raw-only wins. The result is exploratory and scoped; it does not establish broad superiority or universal gap closure.

Do not use “Mighty Mouse closes the small-model gap” as an unqualified headline from this run.
