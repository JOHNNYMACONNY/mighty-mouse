# MM-004 — Mixed Python and Node verification

Both conditions started at `8b54f8e` with identical agent/model/dependency
configuration. The harness alone received the Mighty Mouse medium protocol.

Both passed first evaluator acceptance across real mixed Python/Node pass and
failure fixtures, missing npm, malformed package metadata, missing scripts, and
Python syntax fallback. Neither violated scope. Control was faster (160.265s vs
242.429s). Both score 4 on the integer quality rubric, while the blind review
selected harness 4.4 vs 4.0 for stronger invalid-script handling and API
compatibility.

Raw sessions remain local; hashes and source-only patches are published here.
