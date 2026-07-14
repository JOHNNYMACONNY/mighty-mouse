# v2 Local Improvement Bundles for Future Federation — Research Note

Scope: decision input for ["Define local improvement bundles for future federation"](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/14). This specifies an import/export trust contract, not an implementation or a federation service.

## Decision

Mighty Mouse v2 should support a **local-first, data-only Improvement Bundle**: a portable, immutable claim about one local Candidate and its already-recorded evidence. Export is explicit. Import is offline-capable, quarantined, and creates only a new *untrusted local Candidate*; it never imports authority, executable code, a Champion, a Model Class rule, a Policy, a key, or a promotion decision.

The design deliberately separates portable proof from local trust. A digest is a content-addressed assertion, not approval: OCI likewise requires consumers of untrusted descriptor content to verify its digest ([OCI Descriptor](https://specs.opencontainers.org/image-spec/descriptor/?v=v1.1.0)). A publisher signature identifies the signer, while the receiving installation's local trust policy decides whether that signer is eligible for this bundle type.

## Bundle layout and canonical digest

Use a deterministic archive containing only these entries; reject duplicate paths, symlinks, absolute or traversal paths, special files, and undeclared entries.

```text
manifest.json                 # unsigned, JCS-canonical bundle manifest
signatures/<key-id>.json      # detached signature envelope(s)
blobs/sha256/<hex>            # optional data payloads, never executable
```

`manifest.json` must list every included blob as `{ media_type, digest, size }`, and may reference rather than copy retained local Evidence Bundles. Its **canonical bundle digest** is `sha256` over the [RFC 8785 JCS](https://www.rfc-editor.org/rfc/rfc8785.html) serialization of the unsigned manifest. JCS gives a repeatable representation for hashing/signing; each blob digest and size is verified before any parser consumes it. The detached signature signs a domain-separated string containing `mighty-mouse/improvement-bundle/v1`, the canonical bundle digest, and the manifest `schema_id`/`schema_version`. This makes repackaging harmless while making manifest or payload substitution detectable.

The manifest must contain: bundle format/schema versions; creation time; publisher identifier; Candidate immutable artifact/manifest digest; declared capability set; exact source Model Identities; Model Class schema/version; Execution Profile constraints; evaluator/protocol/corpus digests and versions; Evidence Bundle references; all blob descriptors; and provenance fields sufficient to link the claim to its source artifacts. SLSA's verification guidance similarly checks that an attestation subject matches the artifact digest ([SLSA verification](https://slsa.dev/spec/v1.2/verifying-artifacts)).

## Signature and local key trust

- Support a narrowly specified, versioned signature envelope and algorithm suite; require key ID, algorithm, signature, signing time, and the signed canonical digest. Do not accept an algorithm merely because the bundle requests it.
- Verify only against a local, operator-managed keyring mapping publisher IDs and key IDs to allowed bundle purposes, algorithms, validity windows, and signature thresholds. Never import keys, trust roots, revocations, or threshold policy from a bundle.
- Require fresh, non-revoked keys and the locally configured threshold; record the key-policy version and verification result in quarantine. This follows the useful separation in [TUF](https://theupdateframework.io/papers/survivable-key-compromise-ccs2010.pdf) between trusted key IDs, thresholds, versions, and expiration.
- An unsigned, unknown-key, expired, revoked, or threshold-failing bundle is rejected (with only a local security receipt), not "best effort" imported.

## Compatibility is exact by default

The importer requires every source Model Identity to be complete and to include the exact `artifact_digest`, normalized provider/runtime metadata, architecture fingerprint, observed versioned capability vector, and resolution evidence. It separately checks the complete Execution Profile: runtime/provider version, effective context bound, tool contract and prompt-template digests, sampling, and resource limits.

Only **exact compatibility** (same artifact digest, required capabilities, and compatible Execution Profile) makes an imported result comparable or reusable after local verification. A requested tag, family, parameter count, or quantization label is descriptive metadata only. A **Model Class** is named and versioned (family plus architecture/tokenizer/template and capability contract), but differing digests are class-compatible only for discovery and opt-in targeting. Class membership never transfers a Champion or result. A transfer-class claim is usable only after the receiver locally validates the frozen cross-member protocol on every enrolled exact identity; changing membership or class rules invalidates that claim until rerun.

An incomplete/unresolved identity, missing capability, incompatible context/tool contract, unknown class schema, or failed local capability probe is incompatible: no import into the candidate store, comparison, resume, promotion, or fallback.

## Evidence references and retention

Bundles carry Evidence Bundle **references** (canonical evidence digest, required record types, storage scope, and optional redacted/exportable blob descriptors), not an entitlement to source transcripts, private corpora, secrets, or local source. Required evidence covers the candidate/base artifacts, model and execution identities, evaluator/corpus/sandbox digests, typed outcomes, gate decisions, and rollback/restriction history. Keep detailed evidence local, immutable, access-controlled, and subject to the receiver's retention policy; routine content-free Signals remain separate and retain for 30 days before aggregation. If required evidence is absent, redacted beyond the declared verification scope, or fails its digest, the bundle cannot support eligibility.

## Quarantine, validation, and promotion boundary

Import writes bytes only to a non-executable quarantine outside the controller, evaluator, Policy store, keyring, ledger, and normal candidate paths. With no network and no ambient credentials, the controller performs this fail-closed sequence:

1. Archive safety and resource limits; entry allowlist; canonicalization and schema validation.
2. Blob size/digest and canonical bundle-digest verification; signature and *local* key-policy verification.
3. Manifest/provenance consistency, Evidence Bundle reference checks, schema compatibility, and exact Model Identity, Model Class, capability, and Execution Profile checks.
4. Secret/malware policy scan and declared-data-only validation. No payload is executed, installed, unpacked into a workspace, or allowed to alter evaluator/controller inputs.
5. On success, atomically create a quarantined, untrusted local Candidate with an immutable import receipt. On any failure, retain only bounded diagnostic metadata and reject/delete quarantine material under local policy.

There is **no direct promotion path**. The local controller must run its own capability probes and the same isolated local evaluation, independent fresh-holdout gates, provenance checks, and promotion/rollback rules as for a locally generated Candidate. Imported evaluation results are claims that can inform scheduling or comparison planning; they cannot activate a Champion, satisfy a Pin, widen a Model Class, modify a baseline, or lower a threshold.

## Future federation boundary

v2 exports/imports files only: no registry discovery, peer synchronization, telemetry upload, automatic key enrollment, remote policy, remote execution, or cross-user ranking. A future opt-in federation may add transport, publisher discovery, key distribution, revocation, and reputation only as separately versioned protocols above this stable bundle contract. It must preserve local verification and local promotion as the final authority; federation may distribute signed claims, never control a receiver's controller, evaluator, keyring, retention policy, Model Class definition, or Champion selection.

## Decision rationale

This contract preserves v2's existing least-privilege control plane and immutable Evidence Bundles while giving users a useful portable artifact now. It reuses established patterns—canonical signed data ([RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html)), content-addressed descriptors ([OCI](https://specs.opencontainers.org/image-spec/descriptor/?v=v1.1.0)), and subject-digest provenance checks ([SLSA](https://slsa.dev/spec/v1.2/verifying-artifacts))—without mistaking provenance or publisher identity for local authorization.
