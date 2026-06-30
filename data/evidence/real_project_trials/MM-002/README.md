# MM-002 — Stable JSON output and protocol CLI

Both conditions started at `d1f7858`, used dependency-identical Python 3.13.11
environments and the same Codex/model settings, and received the same task and
acceptance gates. Mighty Mouse medium protocol activation was the sole intended
condition difference.

Both conditions passed all 81 tests and installed-wheel human/JSON smoke checks
on the first evaluator acceptance, with no scope violations. Harness completed
in 191.571 seconds versus 225.503 seconds for control and won the blind review.

Raw sessions remain local because they contain machine paths and session
instructions. Hashes are published in the result files; source-only patches are
published for direct inspection.
