# Held-out Corpus Authoring Register

This register is the public inventory for the first scored local-model capability study. It deliberately omits task prompts, starting implementations, and acceptance commands; those remain in the private corpus bundle until the study is complete.

## Source boundary

Tasks are small, disposable fixtures derived from recurring implementation patterns in these repositories. They are not claims that an agent changed the production repositories.

| Source | Language | Included patterns | Excluded |
| --- | --- | --- | --- |
| Mighty Mouse | Python | configuration, filesystems, queues, subprocess boundaries, evaluation reporting | live model calls and production evidence |
| AudioServiceApp | JavaScript/TypeScript | portfolio data, content routing, form validation, static rendering, event payloads | Supabase, Stripe, browser automation, deployment |
| LA Studio Finder | JavaScript/TypeScript | directory records, search/filter behavior, URL state, result normalization | external directory crawling, maps, live APIs |

All fixtures must run with language-standard runtimes only (`python -m pytest` or `node --test`) and must not require network access, a browser, credentials, or installed project dependencies.

## Frozen roster

| ID | Source | Category | Complexity | Capability being measured |
| --- | --- | --- | --- | --- |
| MM-01 | Mighty Mouse | coding | low | inclusive numeric configuration bound |
| MM-02 | Mighty Mouse | coding | low | safe path normalization |
| MM-03 | Mighty Mouse | coding | medium | structured run-metadata merge |
| MM-04 | Mighty Mouse | coding | medium | timeout-result normalization |
| MM-05 | Mighty Mouse | coding | high | idempotent queue delivery |
| MM-06 | Mighty Mouse | agentic | low | interpret a failing validation report |
| MM-07 | Mighty Mouse | agentic | medium | trace a model-output schema mismatch |
| MM-08 | Mighty Mouse | agentic | high | diagnose and repair a resumability incident |
| MM-09 | Mighty Mouse | agentic | high | preserve evidence while correcting a manifest |
| MM-10 | Mighty Mouse | agentic | medium | reconcile conflicting configuration sources |
| ASA-01 | AudioServiceApp | coding | low | normalize a portfolio slug |
| ASA-02 | AudioServiceApp | coding | low | validate a contact payload |
| ASA-03 | AudioServiceApp | coding | medium | merge case-study media metadata |
| ASA-04 | AudioServiceApp | coding | high | deterministic work-card ordering |
| ASA-05 | AudioServiceApp | agentic | low | locate a rendered-card regression |
| ASA-06 | AudioServiceApp | agentic | medium | repair analytics event compatibility |
| ASA-07 | AudioServiceApp | agentic | high | diagnose stale static-content selection |
| ASA-08 | AudioServiceApp | agentic | high | reconcile route data with content inventory |
| ASA-09 | AudioServiceApp | agentic | medium | fix structured-data serialization evidence |
| ASA-10 | AudioServiceApp | coding | medium | enforce an image-alt fallback contract |
| LSF-01 | LA Studio Finder | coding | low | canonicalize directory areas |
| LSF-02 | LA Studio Finder | coding | low | normalize studio price fields |
| LSF-03 | LA Studio Finder | coding | medium | compose safe directory filters |
| LSF-04 | LA Studio Finder | coding | high | stable ranked search results |
| LSF-05 | LA Studio Finder | agentic | low | resolve malformed directory records |
| LSF-06 | LA Studio Finder | agentic | medium | trace URL-query filter loss |
| LSF-07 | LA Studio Finder | agentic | high | repair pagination state after filtering |
| LSF-08 | LA Studio Finder | agentic | high | diagnose duplicate results across pages |
| LSF-09 | LA Studio Finder | coding | medium | preserve filter state during sort changes |
| LSF-10 | LA Studio Finder | agentic | medium | reconcile imported listing fields |

The roster contains 15 coding tasks, 15 agentic tasks, and ten tasks per complexity tier. Replacements are allowed only before scored execution starts, with the invalidation reason retained in the private corpus change log.

## Per-task acceptance gate

Before a task enters the private `corpus.json`, its author must record:

1. The task prompt and explicit writable-path allowlist.
2. A deliberately broken baseline whose hidden acceptance check fails.
3. At least one likely-but-incorrect implementation that the hidden check rejects.
4. A clean, deterministic command that completes within 30 seconds.
5. A source snapshot digest and a task definition digest.
6. A human review confirming the task does not need an external service or a secret.

The corpus runner rejects the corpus unless these balance constraints are met, then records its exact manifest and model digests before the first condition starts.
