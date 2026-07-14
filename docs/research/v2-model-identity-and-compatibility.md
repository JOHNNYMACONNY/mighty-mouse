# v2 Model Identity and Champion Compatibility — Research Note

Scope: decision input for ["Define model identity and champion compatibility"](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/17). This defines planning constraints, not an implementation.

## Decision

Mighty Mouse v2 must make every Candidate, Champion, Experiment, Evidence Bundle, Pin, Preview, and future improvement bundle reference an immutable **Model Identity**. A requested model name or tag is human-readable discovery metadata, never sufficient identity for reproducible evaluation or automatic Champion selection. The model digest is the primary exact-artifact key: content-addressable digests let a consumer independently verify the bytes it received ([OCI descriptor specification](https://specs.opencontainers.org/image-spec/descriptor/?v=v1.1.0)).

Model Identity is separate from an **Execution Profile** (runtime/provider version, effective context limit, tool contract version, system/prompt template digests, sampling settings, and resource limits). A Champion is selected only when both its Model Identity compatibility rule and its Execution Profile compatibility rule pass.

## Required Model Identity record

| Field | Rule |
| --- | --- |
| `provider_kind` and `runtime_version` | Record the normalized local runtime and its version; a host URL is diagnostic metadata, not a portable identity key. |
| `requested_ref` | Preserve the configured name/tag for operator visibility, but never use it for equality. |
| `artifact_digest` | Required exact content digest, algorithm included. The digest identifies the concrete local artifact; changing it creates a new Model Identity. |
| `format`, `family`, `families`, `parameter_size`, `quantization_level` | Record the runtime-reported descriptive fields for discovery and compatibility classes, not as substitutes for the digest. Ollama exposes these alongside a model digest through its model-list API ([Ollama](https://docs.ollama.com/api/tags)). |
| `architecture_fingerprint` | Canonicalized non-secret architecture/tokenizer/template facts needed to prevent false matches, plus a hash of the full runtime-reported model metadata. |
| `capability_vector` | A versioned, observed capability contract: completion/chat, tool-call protocol, vision or other modalities, effective context ceiling, and any required structured-output support. It is measured with a small capability probe; provider claims alone do not pass it. |
| `resolved_at` and `resolution_status` | Record whether identity is `complete`, `partial`, or `unresolved`, plus the probe evidence and errors. |

Ollama's detailed model API also exposes capabilities and context-length-related metadata, so v2 should resolve identity before a run and persist the raw redacted response hash as evidence ([Ollama](https://docs.ollama.com/api-reference/show-model-details)).

## Compatibility levels

1. **Exact compatibility** — same artifact digest, required capability vector, and compatible Execution Profile. This is the only level that may automatically select an existing Champion, reuse an Experiment result, resume a run, or satisfy a Pin.
2. **Class compatibility** — two complete identities belong to a named, versioned Model Class (normally family + architecture/tokenizer/template contract + capability vector), but their artifact digests differ. Class membership supports discovery and future opt-in bundle targeting only; it never transfers a Champion or claims an evaluation result.
3. **Provisional compatibility** — a human has chosen a candidate/model pair for a Preview after capability probes pass. The result is explicitly a Preview and cannot promote or update a class rule.
4. **Incompatible** — missing required capability, incompatible prompt/tool contract, different effective context bound, failed probe, or an identity that is partial/unresolved. No automatic selection, promotion, comparison, resume, or import occurs.

A Model Class may be promoted to a **validated transfer class** only after a frozen, versioned cross-member protocol shows the Candidate against the relevant baseline on each enrolled exact identity. The evidence must be retained per identity. Adding, removing, or changing a member invalidates the class-level transfer assertion until rerun; it does not alter prior exact results.

## Selection and change behavior

- On every interactive run, AFK run, resume, evaluation, Preview, and promotion, resolve the current identity before work and record it again at completion. A mismatch invalidates the run rather than attributing one result to two artifacts.
- If a tag resolves to a new digest, create a new identity automatically. Do not overwrite the prior identity, re-label its Champion, or treat the change as an ordinary configuration edit.
- If identity is partial or unresolved, Mighty Mouse may perform a manually confirmed diagnostic Preview using the safe base Policy, but must not create a promotable Candidate, write a reusable Experiment result, select a Champion automatically, or accept an imported bundle.
- If a previously compatible Champion no longer matches the current identity or Execution Profile, leave its history intact and mark it **not applicable** to the current selection. This is not a security restriction or rollback; the prior Champion remains valid for the identity on which it was proven.
- If no exact compatible Champion exists, select the repository-shipped baseline Policy for the chosen Mode and clearly report that no learned Champion applies. Never infer compatibility from a friendly model name, parameter count, or family alone.

## Future improvement bundles

Future opt-in bundles must declare the exact source Model Identities, the Model Class schema version, required capability vector, Execution Profile constraints, evaluator/corpus versions, and Evidence Bundle digests. Import validation verifies those claims and treats a bundle as a new local Candidate. A bundle cannot activate a Champion, widen model classes, or introduce a compatibility fallback without local capability probes and evaluation.

## Existing-code implication

The existing pilot already captures a selected Ollama digest and freezes it in its study manifest, while the older orchestration client retains only a configured model name. v2 should unify those paths around Model Identity rather than treating the configured name as evidence. The repository's existing study rule—resume only when frozen model digests and protocol inputs match—becomes the exact-compatibility rule for v2.
