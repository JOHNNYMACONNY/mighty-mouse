# v2 Self-Improvement Threat Model — Research Note

Scope: decision input for ["Define the self-improvement threat model and trust boundaries"](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/16). This is an implementation-ready policy decision, not an implementation.

## Security posture

Treat every item that can influence a run as untrusted until a machine-verifiable boundary says otherwise: task text and repository content, model output, generated code and configuration, evaluator output, tool output, and imported improvement bundles. A prompt, model self-assessment, or a passing candidate-owned test is never an authorization decision. This follows OWASP's treatment of prompt injection as a primary LLM-application risk and OpenAI's guidance to minimize an agent's data access and tool authority ([OWASP](https://owasp.org/www-project-top-10-for-large-language-model-applications/), [OpenAI](https://openai.com/safety/prompt-injections/)).

The local controller, policy store, approved evaluator image, cryptographic keys, secret store, and promotion ledger are trusted computing-base components. The controller is the only principal permitted to create Candidates, run evaluations, write the ledger, activate a Champion, import an artifact, or restrict a Champion. A Candidate never receives ambient credentials or authority over those components.

## Required v2 boundaries and gates

| Surface | Required boundary | Machine-verifiable gate |
| --- | --- | --- |
| Candidate code/configuration | A Candidate is an immutable, content-addressed patch plus a declarative manifest. It may modify only the allowlisted harness mutation surface; it cannot modify the controller, evaluator image, gate definitions, secret provider, ledger, or its own declared baseline. | Schema validation; path allowlist; clean-tree and diff checks; artifact and manifest hashes recorded before execution. |
| Task and prompt content | Task repositories, issue text, fetched documentation, model/tool output, and evaluation fixtures are data, not instructions to the controller. Untrusted text cannot add tools, widen paths, change the policy, request credentials, or authorize promotion. | Typed task manifest; fixed tool catalog; explicit trust labels; policy evaluation outside the model context; reject any undeclared capability request. |
| Execution | Each evaluation runs in a disposable, per-condition workspace and a hardened sandbox. Deny network egress by default at the OS/container boundary; mount only the task workspace and read-only approved dependencies; deny host sockets, process inspection, device access, and parent workspace access; impose CPU, memory, process, disk, and wall-time quotas. | Sandbox attestation records image digest, mount list, network policy, limits, exit reason, and detected policy violations. Failure to attest invalidates the run. |
| Secrets and source | Evaluation workers receive no user, provider, Git, package-registry, or signing credentials. Sensitive local source never enters routine Signals; diagnostics belong only in a local Evidence Bundle with restrictive permissions and retention. | Empty environment allowlist except approved non-secret values; secret scan on outputs; content-free Signal schema; evidence-bundle access audit. |
| Evaluator integrity | Candidate code must not run evaluator-owned acceptance code, write results, or choose the comparison. Acceptance executes from a separately hashed evaluator image after the candidate sandbox ends, on a fresh workspace. | Signed/hashed evaluator and corpus manifests; independent rerun; typed outcomes including `invalid` and `security_failure`; mismatch or verifier modification invalidates the pair. |
| Promotion and rollback | Promotion consumes only immutable Candidate, evaluator, and Evidence Bundle records. A Champion activates atomically only after every required gate passes; the previous Champion remains runnable and pinned history is immutable. | Verified provenance graph, fresh-holdout result, comparison threshold, policy compatibility, no security findings, atomic activation record, and post-promotion guard. |
| Imported bundles | v2 imports no executable code by default. A future opt-in bundle is data-only unless its publisher identity, signature, model compatibility, schema, provenance, and declared capability set verify. Imported material always enters as an untrusted Candidate and must pass the same local evaluation. | Signature and key-policy verification; content hash; schema and compatibility validation; quarantine on failure; no direct activation path. |
| Operations | A local kill switch stops scheduling, blocks promotion/import, and restores the last eligible Champion without deleting provenance. It is available outside the model/tool path. | Controller-enforced state transition; durable audit event; recovery test at startup; no Candidate-controlled override. |

The existing Python wrapper’s network monkey-patching and `open()` interception are useful defense in depth, but are insufficient as the v2 isolation boundary: candidate code can use other OS interfaces or escape the process assumptions. The v2 specification must therefore require isolation enforced below the evaluated process.

## Restriction rule

A previously promoted Champion becomes **restricted** immediately when any of the following is observed: failed post-promotion guard; verified sandbox-escape or policy-violation attempt; provenance, signature, or ledger-integrity mismatch; secret exposure; unauthorized network or filesystem access; evaluator/corpus tampering; materially incompatible model or runtime identity; or a reproducible security regression against the frozen adversarial suite.

Restriction stops new use and AFK scheduling, preserves the immutable record, rolls back automatically to the immediately preceding eligible Champion when one exists, and requires a fresh Candidate plus a clean evaluation to re-enter eligibility. Ordinary quality regressions remain normal rollback/failed-promotion outcomes; they are not security restrictions.

## Evidence and review requirements

Every experiment and promotion must retain a local, immutable Evidence Bundle containing the signed candidate/manifest, base Champion, evaluator and sandbox image digests, task/corpus identifiers, model identity, policy and compatibility decisions, commands, typed outcomes, gate decisions, and rollback/restriction events. This gives the traceability expected of artifact provenance ([SLSA provenance](https://slsa.dev/spec/v1.2/provenance)) and supports NIST's guidance to assess threats such as compromised dependencies, data breaches, and autonomous agents ([NIST AI 600-1](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)).

Before the roadmap moves to implementation, add adversarial acceptance tests for prompt injection, escaped-path writes, network access, secret discovery, evaluator modification, malformed bundle import, unsigned bundle import, replayed provenance, and harmful-promotion rollback. The test corpus and evaluator remain outside the Candidate's write authority.

## Decision

Mighty Mouse v2 should use a **least-privilege, immutable-artifact control plane**: Candidates are untrusted and isolated; evaluator, provenance, promotion, and recovery are independently verified controller functions; no content or model output can widen authority; and a verified security breach automatically restricts the Champion and invokes rollback.
